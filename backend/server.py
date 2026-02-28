import asyncio
import json
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from chatgpt import generate_task_steps
from camera import get_camo_feed, set_current_step, results_queue, audio_running
from context_help import get_step_details, get_step_image

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class FoodRequest(BaseModel):
    food: str

class StepRequest(BaseModel):
    step: str

class StartRequest(BaseModel):
    system_prompt: str | None = None

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_camera_thread: threading.Thread | None = None

SYSTEM_PROMPT_DEFAULT = (
    "You are a precise real-time recipe vision assistant. "
    "When checking recipe steps, you analyze a previous frame and a current frame from a live camera feed. "
    "Always return structured JSON with completed, state, and action fields as instructed. "
    "When the user speaks, respond briefly and helpfully. "
    "Be consistent and strict — only mark a step complete when it is clearly visible."
)

# ---------------------------------------------------------------------------
# Recipe
# ---------------------------------------------------------------------------

@app.post("/recipe/generate")
def generate(req: FoodRequest):
    """Generate ordered recipe steps for a given food."""
    steps = generate_task_steps(req.food)
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

    if _camera_thread and _camera_thread.is_alive():
        return {"ok": False, "message": "Camera already running"}

    prompt = req.system_prompt or SYSTEM_PROMPT_DEFAULT
    _camera_thread = threading.Thread(
        target=get_camo_feed,
        kwargs={"system_prompt": prompt},
        daemon=True,
    )
    _camera_thread.start()
    return {"ok": True}


@app.post("/camera/stop")
def stop_camera():
    """Stop the camera feed and AI pipeline."""
    audio_running.clear()
    return {"ok": True}

# ---------------------------------------------------------------------------
# Step context
# ---------------------------------------------------------------------------

@app.get("/step/details")
def step_details(step: str):
    """Return a one-sentence how-to explanation for a recipe step."""
    return get_step_details(step)


@app.get("/step/image")
def step_image(step: str):
    """Return an image URL showing the completed state of a recipe step."""
    return get_step_image(step)

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

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
