from openai import OpenAI
from dotenv import load_dotenv
import base64
import cv2

load_dotenv()

client = OpenAI()

# Rolling conversation history — text only (images are not stored to save tokens)
# Each entry is {"role": "user"|"assistant", "content": str}
conversation_history = []
MAX_HISTORY = 20  # max messages kept (= 10 back-and-forth exchanges)

# The last frame sent to GPT — included as "previous frame" in every subsequent call
_previous_frame = None


def ai_text_output(prompt):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    print(response.choices[0].message.content)


def transcribe_audio(wav_buffer):
    """
    Transcribe a WAV audio buffer using OpenAI Whisper API.

    Args:
        wav_buffer: BytesIO object containing a valid WAV file.

    Returns:
        str: Transcribed text, or empty string if nothing detected.
    """
    wav_buffer.seek(0)
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.wav", wav_buffer, "audio/wav"),
    )
    return transcript.text.strip()


def _encode_frame(frame):
    """Encode a cv2 BGR frame to a base64 JPEG string."""
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf).decode("utf-8")


def ai_vision_audio_query(text_prompt, frame=None, system_prompt=None, stream=False, remember=True):
    """
    Send transcribed speech + an optional video frame to GPT-4o,
    with rolling conversation history for context.

    Args:
        text_prompt:   Transcribed speech or any text query.
        frame:         Optional numpy BGR array (cv2 frame) to include as image context.
        system_prompt: Optional system message to set model behaviour.
        stream:        If True, yields response text chunks; otherwise returns full string.
        remember:      If True, appends this exchange to conversation history.
                       Set False for passive video-only snapshots so they don't
                       pollute the conversational context.

    Returns:
        str (stream=False) or generator of str chunks (stream=True).
    """
    messages = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Inject prior conversation (text-only — images not stored to save tokens)
    messages.extend(conversation_history)

    # Build the current user message
    if frame is not None:
        global _previous_frame
        content = []

        # Include previous frame first so GPT can see the transition
        if _previous_frame is not None:
            content.append({"type": "text", "text": "Previous frame:"})
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{_encode_frame(_previous_frame)}",
                    "detail": "low",
                },
            })

        content.append({"type": "text", "text": "Current frame:"})
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{_encode_frame(frame)}",
                "detail": "low",
            },
        })
        content.append({"type": "text", "text": text_prompt})

        _previous_frame = frame.copy()
    else:
        content = text_prompt

    messages.append({"role": "user", "content": content})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        stream=stream,
    )

    if stream:
        def _gen():
            full_response = []
            for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_response.append(delta)
                    yield delta
            if remember:
                _append_history(text_prompt, "".join(full_response))
        return _gen()
    else:
        result = response.choices[0].message.content
        if remember:
            _append_history(text_prompt, result)
        return result


def _append_history(user_text, assistant_text):
    """Append an exchange to conversation_history and trim to MAX_HISTORY."""
    conversation_history.append({"role": "user", "content": user_text})
    conversation_history.append({"role": "assistant", "content": assistant_text})
    if len(conversation_history) > MAX_HISTORY:
        # Drop oldest pair to stay within the window
        del conversation_history[:2]


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
- If a step requires a specific kitchen tool (knife, peeler, grater, pan, etc.), name it explicitly in the step (e.g. "cut apple into slices using a knife")

Return ONLY a raw JSON array of strings. No markdown, no explanation, no extra keys."""

_TASK_DECOMP_EXAMPLES = [
    {
        "role": "user",
        "content": "Task: Make a peanut butter and jelly sandwich"
    },
    {
        "role": "assistant",
        "content": '["Two slices of bread are laid flat on a surface", "Peanut butter is spread across one slice using a butter knife", "Jelly is spread across the other slice using a butter knife", "Both slices are pressed together face-down"]'
    },
    {
        "role": "user",
        "content": "Task: Make iced coffee"
    },
    {
        "role": "assistant",
        "content": '["A glass is placed on a flat surface", "Glass is filled with ice cubes", "Coffee is poured over the ice", "Milk or creamer is added to the glass", "Drink is stirred with a spoon"]'
    },
    {
        "role": "user",
        "content": "Task: Make a bowl of cereal"
    },
    {
        "role": "assistant",
        "content": '["A bowl is placed on a flat surface", "Cereal is poured into the bowl", "Milk is poured over the cereal"]'
    },
    {
        "role": "user",
        "content": "Task: Make avocado toast"
    },
    {
        "role": "assistant",
        "content": '["A slice of bread is placed on a flat surface", "Bread is toasted and placed back on the surface", "Avocado is halved using a knife", "Avocado is scooped and spread across the toast using a butter knife", "Salt and pepper are sprinkled on top"]'
    },
]


def generate_task_steps(task: str) -> list[str]:
    """
    Break a physical task into a list of frame-verifiable steps using GPT.

    Args:
        task: Natural language description of the task (e.g. "do a squat").

    Returns:
        List of step strings in order, e.g.:
        ["Stand with feet shoulder-width apart", "Lower hips to parallel", ...]
    """
    import json

    messages = [{"role": "system", "content": _TASK_DECOMP_SYSTEM}]
    messages.extend(_TASK_DECOMP_EXAMPLES)
    messages.append({"role": "user", "content": f"Task: {task}"})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,  # low temp = consistent, structured output
    )

    raw = response.choices[0].message.content.strip()
    return json.loads(raw)