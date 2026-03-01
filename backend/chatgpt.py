from openai import OpenAI
from dotenv import load_dotenv
import base64
import cv2

load_dotenv()

client = OpenAI()

# ---------------------------------------------------------------------------
# Conversation history — speech only (step checks never go into history)
# ---------------------------------------------------------------------------

conversation_history = []
MAX_HISTORY = 20  # max messages kept (= 10 back-and-forth exchanges)

# The last frame sent — included as "previous frame" in every call with vision
_previous_frame = None


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

# Used by vision_step_check() — expects strict JSON back, no chat
_STEP_CHECK_SYSTEM = (
    "You are a precise recipe vision assistant. "
    "You analyze two camera frames and return ONLY a raw JSON object. "
    "No markdown, no explanation, no text outside the JSON. "
    "Be strict: only mark completed true when the step result is clearly visible."
)

# Used by speech_response() — friendly conversational assistant
_SPEECH_SYSTEM = (
    "You are Remy, an expert AI cooking assistant inspired by the rat from Ratatouille. "
    "You are watching the user cook via camera and coaching them through a recipe in real time.\n\n"
    "Rules:\n"
    "- Answer in 1-2 sentences. Be direct.\n"
    "- Never start with 'Great!', 'Sure!', 'Of course!', 'Absolutely!' or any filler affirmation.\n"
    "- If you can see the camera frame, use it — describe what you actually see and base your answer on it.\n"
    "- If they ask 'does this look right?', give a real honest answer based on the frame.\n"
    "- Match their energy: quick question = quick answer. Detailed question = more detail.\n"
    "- Occasional warmth and encouragement is fine, but never sycophantic.\n"
    "- Never respond with JSON — always respond in natural language."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_frame(frame) -> str:
    """Encode a cv2 BGR frame to a base64 JPEG string."""
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf).decode("utf-8")


def _append_history(user_text: str, assistant_text: str):
    """Append an exchange to conversation_history and trim to MAX_HISTORY."""
    conversation_history.append({"role": "user", "content": user_text})
    conversation_history.append({"role": "assistant", "content": assistant_text})
    if len(conversation_history) > MAX_HISTORY:
        del conversation_history[:2]


# ---------------------------------------------------------------------------
# Speech transcription
# ---------------------------------------------------------------------------

def transcribe_audio(wav_buffer) -> str:
    """
    Transcribe a WAV audio buffer using OpenAI Whisper API.

    Args:
        wav_buffer: BytesIO containing a valid WAV file.

    Returns:
        Transcribed text, or empty string if nothing detected.
    """
    wav_buffer.seek(0)
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.wav", wav_buffer, "audio/wav"),
    )
    return transcript.text.strip()


# ---------------------------------------------------------------------------
# Vision step check  —  JSON only, never enters conversation history
# ---------------------------------------------------------------------------

def vision_step_check(step: str, frame, previous_frame=None) -> str:
    """
    Analyze one or two camera frames and return a raw JSON step-check result.

    Args:
        step:           The current recipe step to verify.
        frame:          Current cv2 BGR frame.
        previous_frame: Previous cv2 BGR frame (or None for first check).

    Returns:
        Raw JSON string from GPT (caller is responsible for parsing).
    """
    prompt = (
        f'The current recipe step to verify is: "{step}"\n\n'
        f'Examine the frame(s) and return ONLY a raw JSON object with this structure:\n'
        f'{{\n'
        f'  "completed": <true if state.completed OR action.completed is true>,\n'
        f'  "state": {{"completed": <bool>, "explanation": "<one sentence>"}},\n'
        f'  "action": {{"completed": <bool>, "explanation": "<one sentence>"}}\n'
        f'}}\n\n'
        f'Rules:\n'
        f'- completed is true only if state.completed OR action.completed is true\n'
        f'- Be strict: only mark completed true if clearly visible\n'
        f'- Return raw JSON only, no markdown code blocks'
    )

    content = []
    if previous_frame is not None:
        content.append({"type": "text", "text": "Previous frame:"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{_encode_frame(previous_frame)}", "detail": "low"},
        })
    content.append({"type": "text", "text": "Current frame:"})
    content.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{_encode_frame(frame)}", "detail": "low"},
    })
    content.append({"type": "text", "text": prompt})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _STEP_CHECK_SYSTEM},
            {"role": "user", "content": content},
        ],
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Speech response  —  conversational, updates history, streams
# ---------------------------------------------------------------------------

def speech_response(user_text: str, frame=None, recipe: str = None, current_step: str = None, all_steps: list = None):
    """
    Respond to what the user said. Streams response chunks.
    Adds the exchange to conversation history.

    Args:
        user_text:    Transcribed speech from the user.
        frame:        Optional current cv2 BGR frame for visual context.
        recipe:       The recipe being made (e.g. "spaghetti carbonara").
        current_step: The step the user is currently on.
        all_steps:    Full ordered list of all recipe steps.

    Yields:
        str chunks of the assistant response.
    """
    # Build a context-aware system prompt
    system = _SPEECH_SYSTEM
    if recipe or current_step:
        context_lines = []
        if recipe:
            context_lines.append(f"The user is making: {recipe}")
        if all_steps and current_step:
            try:
                step_num = all_steps.index(current_step) + 1
                context_lines.append(f"They are on step {step_num} of {len(all_steps)}: \"{current_step}\"")
            except ValueError:
                context_lines.append(f"Current step: \"{current_step}\"")
        elif current_step:
            context_lines.append(f"Current step: \"{current_step}\"")
        system = _SPEECH_SYSTEM + "\n\nCurrent context:\n" + "\n".join(context_lines)

    messages = [{"role": "system", "content": system}]
    messages.extend(conversation_history)

    if frame is not None:
        content = [
            {"type": "text", "text": "Current frame:"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{_encode_frame(frame)}", "detail": "low"},
            },
            {"type": "text", "text": user_text},
        ]
    else:
        content = user_text

    messages.append({"role": "user", "content": content})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        stream=True,
    )

    full_response = []
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            full_response.append(delta)
            yield delta

    _append_history(user_text, "".join(full_response))


# ---------------------------------------------------------------------------
# Task decomposition
# ---------------------------------------------------------------------------

_TASK_DECOMP_SYSTEM = """You are a recipe decomposition engine for a real-time AI vision cooking assistant.
Given a food or drink to make, break it into ordered preparation steps that a camera can verify one frame at a time.

Rules for every step:
- Describes a single visible state of ingredients or tools (not an action in motion)
- Can be confirmed TRUE or FALSE from one video frame (e.g. "bread is on the plate", "ice is in the glass")
- Written as one short imperative sentence (max 10 words)
- No time-based instructions ("wait 2 minutes") — visible state only
- Cover the full recipe from start to finish

Return ONLY a raw JSON array of strings. No markdown, no explanation, no extra keys."""

_TASK_DECOMP_EXAMPLES = [
    {"role": "user", "content": "Task: Make a peanut butter and jelly sandwich"},
    {"role": "assistant", "content": '["Two slices of bread are laid flat on a surface", "Peanut butter is spread across one slice", "Jelly is spread across the other slice", "Both slices are pressed together face-down"]'},
    {"role": "user", "content": "Task: Make iced coffee"},
    {"role": "assistant", "content": '["A glass is placed on a flat surface", "Glass is filled with ice cubes", "Coffee is poured over the ice", "Milk or creamer is added to the glass", "Drink is stirred with a spoon"]'},
    {"role": "user", "content": "Task: Make a bowl of cereal"},
    {"role": "assistant", "content": '["A bowl is placed on a flat surface", "Cereal is poured into the bowl", "Milk is poured over the cereal"]'},
    {"role": "user", "content": "Task: Make avocado toast"},
    {"role": "assistant", "content": '["A slice of bread is placed on a flat surface", "Bread is toasted and placed back on the surface", "Avocado is scooped and spread across the toast", "Salt and pepper are sprinkled on top"]'},
]


def generate_task_steps(task: str) -> list[str]:
    """
    Break a physical task into a list of frame-verifiable steps using GPT.

    Returns:
        List of step strings in order.
    """
    import json

    messages = [{"role": "system", "content": _TASK_DECOMP_SYSTEM}]
    messages.extend(_TASK_DECOMP_EXAMPLES)
    messages.append({"role": "user", "content": f"Task: {task}"})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
    )

    raw = response.choices[0].message.content.strip()
    return json.loads(raw)
