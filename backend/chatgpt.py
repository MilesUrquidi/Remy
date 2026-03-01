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
        f'Compare the previous frame and the current frame, then return ONLY a raw JSON object '
        f'with exactly this structure (no markdown, no explanation outside the JSON):\n'
        f'{{\n'
        f'  "completed": <true if the step is clearly done, false otherwise>,\n'
        f'  "state": {{\n'
        f'    "completed": <true/false>,\n'
        f'    "explanation": "<brief description of the current scene>"\n'
        f'  }},\n'
        f'  "action": {{\n'
        f'    "completed": <true/false>,\n'
        f'    "explanation": "<subtle description of what is happening right now>"\n'
        f'  }},\n'
        f'  "hint": "<a tiny, unique nudge to help the user — 6 words max>"\n'
        f'}}\n\n'
        f'Rules:\n'
        f'- completed is true if state.completed OR action.completed is true\n'
        f'- Be strict: only mark completed true if you are clearly sure\n'
        f'- Keep explanations to one short sentence each\n'
        f'- Return raw JSON only, no markdown code blocks\n'
        f'- Accept functional equivalents for containers and tools: a mason jar, mug, bowl, or any similar vessel used in place of a cup or measuring cup is acceptable — judge by the visible end state, not the exact equipment\n'
        f'- Treat measurements as approximate: do not fail a step because an amount looks slightly more or less than specified — focus on whether the visible result is roughly correct\n'
        f'- If the step names a specific tool (e.g. "butter knife", "cup") but the user achieves the same visible outcome with a different one, still mark it completed\n\n'
        f'Rules for state.explanation:\n'
        f'- Describe what you SEE on the surface right now in one calm sentence\n'
        f'- e.g. "A bowl is sitting on the counter" or "Matcha powder is in the bowl"\n\n'
        f'Rules for action.explanation:\n'
        f'- ALWAYS describe a concrete physical thing you see — NEVER talk about "frames", "changes", or "visibility"\n'
        f'- If nothing moved: describe the still scene, e.g. "The bowl is still on the table" or "The counter sits empty"\n'
        f'- If something moved: describe the motion, e.g. "A hand is reaching for the whisk"\n'
        f'- Keep it to ONE short sentence (under 12 words)\n'
        f'- Be natural and observational, like a quiet narrator\n'
        f'- FORBIDDEN phrases: "no change", "no visible change", "between frames", "has occurred", "nothing detected"\n'
        f'- You MUST name a real object in the scene every time\n\n'
        f'Rules for hint:\n'
        f'- A tiny, friendly nudge to guide the user toward completing the step\n'
        f'- e.g. "try placing the bowl closer", "grab a whisk from the drawer", "a little more powder"\n'
        f'- Make each hint feel unique and specific to what you see — never repeat the same hint\n'
        f'- If the step is completed, the hint should be a small encouragement like "looking great" or "nicely done"\n'
        f'- Keep it casual, lowercase, 6 words max\n\n'
        f'General rules:\n'
        f'- Be strict: only mark completed true if the step is clearly and fully done\n'
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
- ONE INGREDIENT OR ONE ACTION PER STEP. Never combine multiple ingredients into a single step. "Add flour and sugar" must be two separate steps.
- Describes a single visible state of ingredients or tools (not an action in motion)
- Can be confirmed TRUE or FALSE from one video frame (e.g. "bread is on the plate", "ice is in the glass")
- Written as one short imperative sentence (max 10 words)
- No time-based instructions ("wait 2 minutes") — visible state only
- Cover the full recipe from start to finish
- If a step requires a specific kitchen tool (knife, peeler, grater, pan, etc.), name it explicitly in the step (e.g. "cut apple into slices using a knife")
- Include an approximate single-serving measurement for every ingredient the first time it appears in a step (e.g. "2 tbsp of peanut butter", "1 cup of milk", "3g of matcha powder"). Assume the recipe makes exactly one portion.
- Err on the side of MORE steps. It is much better to have too many small steps than too few big ones.

Return ONLY a raw JSON array of strings. No markdown, no explanation, no extra keys."""

_TASK_DECOMP_EXAMPLES = [
    {
        "role": "user",
        "content": "Task: Make a peanut butter and jelly sandwich"
    },
    {
        "role": "assistant",
        "content": '["Two slices of bread are laid flat on a surface", "A butter knife is placed next to the bread", "2 tbsp of peanut butter is scooped with the knife", "Peanut butter is spread across one slice", "1½ tbsp of jelly is scooped with the knife", "Jelly is spread across the other slice", "Both slices are pressed together face-down"]'
    },
    {
        "role": "user",
        "content": "Task: Make iced coffee"
    },
    {
        "role": "assistant",
        "content": '["A glass is placed on a flat surface", "½ cup of ice cubes is added to the glass", "180ml of brewed coffee is poured over the ice", "2 tbsp of milk or creamer is added to the glass", "Drink is stirred with a spoon"]'
    },
    {
        "role": "user",
        "content": "Task: Make a bowl of cereal"
    },
    {
        "role": "assistant",
        "content": '["A bowl is placed on a flat surface", "1 cup of cereal is poured into the bowl", "½ cup of milk is poured over the cereal"]'
    },
    {
        "role": "user",
        "content": "Task: Make avocado toast"
    },
    {
        "role": "assistant",
        "content": '["A slice of bread is placed on a flat surface", "Bread is placed in the toaster", "Toasted bread is placed back on the surface", "½ an avocado is halved using a knife", "Avocado pit is removed", "Avocado flesh is scooped onto the toast", "Avocado is spread across the toast using a butter knife", "A pinch of salt is sprinkled on top", "A pinch of pepper is sprinkled on top"]'
    },
]


def generate_task_steps(task: str, avoid: list[str] | None = None) -> list[str]:
    """
    Break a physical task into a list of frame-verifiable steps using GPT.

    Returns:
        List of step strings in order.
    """
    import json

    messages = [{"role": "system", "content": _TASK_DECOMP_SYSTEM}]
    messages.extend(_TASK_DECOMP_EXAMPLES)
    user_content = f"Task: {task}"
    if avoid:
        user_content += f"\nSubstitute these allergens with safe alternatives: {', '.join(avoid)}"
    messages.append({"role": "user", "content": user_content})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
    )

    raw = response.choices[0].message.content.strip()
    return json.loads(raw)
