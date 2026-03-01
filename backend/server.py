import asyncio
import json
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from chatgpt import generate_task_steps
from camera import get_camo_feed, set_current_step, set_current_recipe, results_queue, audio_running, get_latest_frame_jpeg, stop_pipeline
from context_help import get_step_details, get_step_image
from caution import get_safety_caution, get_allergens, get_recipe_allergens
from onlinerecipe import steps_from_url, fetch_recipe
from openai import OpenAI as _OpenAI
from dotenv import load_dotenv as _load_dotenv

_load_dotenv()
_openai_client = _OpenAI()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class FoodRequest(BaseModel):
    food: str

class StepRequest(BaseModel):
    step: str

class StartRequest(BaseModel):
    camera_index: int | None = None
    recipe: str | None = None       # e.g. "spaghetti carbonara"
    steps: list[str] = []           # full ordered step list for context

class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"  # alloy | echo | fable | onyx | nova | shimmer

class SafeRecipeRequest(BaseModel):
    food: str
    avoid: list[str] = []

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_camera_thread: threading.Thread | None = None

# ---------------------------------------------------------------------------
# Recipe
# ---------------------------------------------------------------------------

@app.post("/recipe/generate")
def generate(req: FoodRequest):
    """Generate ordered recipe steps for a given food or recipe URL."""
    if _is_url(req.food):
        steps = steps_from_url(req.food)
    else:
        steps = generate_task_steps(req.food)
    return {"steps": steps}


@app.post("/recipe/allergens")
def recipe_allergens(req: FoodRequest):
    """Scan the whole recipe for all potentially allergenic ingredients."""
    if _is_url(req.food):
        # Fetch the real ingredient list from the page for accurate allergen scanning
        recipe_text = fetch_recipe(req.food)
        allergens = get_recipe_allergens(recipe_text)
    else:
        allergens = get_recipe_allergens(req.food)
    return {"allergens": allergens}


@app.post("/recipe/generate-safe")
def generate_safe(req: SafeRecipeRequest):
    """Generate recipe steps with allergen substitutions."""
    if _is_url(req.food):
        steps = steps_from_url(req.food, avoid=req.avoid or None)
    else:
        steps = generate_task_steps(req.food, avoid=req.avoid or None)
    return {"steps": steps}


@app.post("/recipe/set-step")
def update_step(req: StepRequest):
    """Tell the camera which step to actively check for."""
    set_current_step(req.step)
    return {"ok": True, "step": req.step}

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

@app.post("/camera/start")
def start_camera(req: StartRequest):
    """Start the camera feed + AI pipeline in a background thread."""
    global _camera_thread

    # If a previous run is still winding down, stop it and wait up to 3 s
    if _camera_thread and _camera_thread.is_alive():
        stop_pipeline()
        _camera_thread.join(timeout=3.0)
        if _camera_thread.is_alive():
            return {"ok": False, "message": "Camera still shutting down — try again in a moment"}

    # Store recipe context so Remy knows what's being cooked
    if req.recipe:
        set_current_recipe(req.recipe, req.steps)

    # Set audio_running BEFORE returning so the /camera/feed generator
    # is already live when the frontend renders the <img> tag.
    audio_running.set()

    _camera_thread = threading.Thread(
        target=get_camo_feed,
        kwargs={"camera_index": req.camera_index},
        daemon=True,
    )
    _camera_thread.start()
    return {"ok": True}


@app.post("/camera/stop")
def stop_camera():
    """Stop the camera feed and AI pipeline, flushing all queues immediately."""
    stop_pipeline()
    return {"ok": True}


@app.get("/camera/feed")
async def camera_feed():
    """
    MJPEG stream of the live camera frames.
    Connect with:  <img src="http://localhost:8000/camera/feed" />
    """
    async def generate():
        # Loop only while the camera pipeline is active.
        # When stop_pipeline() clears audio_running this generator exits cleanly,
        # preventing zombie async tasks from accumulating across recipe runs.
        while audio_running.is_set():
            jpeg = get_latest_frame_jpeg(quality=70)
            if jpeg is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            await asyncio.sleep(0.04)  # ~25 fps cap

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache"},
    )

# ---------------------------------------------------------------------------
# Step context
# ---------------------------------------------------------------------------

@app.get("/step/details")
def step_details(step: str):
    """Return a one-sentence how-to explanation for a recipe step."""
    return get_step_details(step)


@app.get("/step/image")
def step_image(step: str, recipe: str | None = None):
    """Return an image URL showing the completed state of a recipe step."""
    return get_step_image(step, recipe=recipe)


@app.get("/step/safety")
def step_safety(step: str):
    """Return a safety caution + tip for a recipe step, or null values if none."""
    data = get_safety_caution(step)
    if data is None:
        return {"caution": None, "tip": None}
    return {"caution": data.get("caution"), "tip": data.get("tip")}


@app.get("/step/allergens")
def step_allergens(step: str):
    """Return a list of allergens detected in a recipe step, or null if none."""
    allergens = get_allergens(step)
    return {"allergens": allergens}

# ---------------------------------------------------------------------------
# SSE stream  —  frontend subscribes here to get live AI results
# ---------------------------------------------------------------------------

@app.get("/stream")
async def stream():
    """
    Server-Sent Events stream.
    Each event is a JSON object:

    Step check (every VIDEO_INTERVAL seconds):
    {
        "type": "step_check",
        "step": "<current step label>",
        "data": {
            "completed": bool,
            "state":  { "completed": bool, "explanation": str },
            "action": { "completed": bool, "explanation": str }
        }
    }

    Speech response (when user speaks):
    {
        "type": "speech",
        "step": "<current step label>",
        "data": "<AI response string>"
    }
    """
    async def event_generator():
        while True:
            try:
                result = results_queue.get_nowait()
                yield f"data: {json.dumps(result)}\n\n"
            except Exception:
                await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "Connection":        "keep-alive",
            "X-Accel-Buffering": "no",   # disable nginx buffering if behind a proxy
        },
    )


# ---------------------------------------------------------------------------
# TTS  —  async so it never blocks the server
# ---------------------------------------------------------------------------

@app.post("/tts")
async def tts(req: TTSRequest):
    """
    Generate speech audio from text using OpenAI TTS.
    Returns MP3 audio as a streaming response.
    Frontend should stop any playing audio and replace it when a new response arrives.
    """
    import queue as _queue
    chunk_queue: _queue.Queue = _queue.Queue()

    def _generate_audio():
        try:
            with _openai_client.audio.speech.with_streaming_response.create(
                model="tts-1",
                voice=req.voice,
                input=req.text,
                response_format="mp3",
            ) as response:
                for chunk in response.iter_bytes(chunk_size=4096):
                    chunk_queue.put(chunk)
        finally:
            chunk_queue.put(None)  # sentinel

    threading.Thread(target=_generate_audio, daemon=True).start()

    async def _stream():
        loop = asyncio.get_event_loop()
        while True:
            chunk = await loop.run_in_executor(None, chunk_queue.get)
            if chunk is None:
                break
            yield chunk

    return StreamingResponse(
        _stream(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-cache"},
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
