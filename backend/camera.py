import cv2
import sounddevice as sd
import numpy as np
import threading
import queue
import io
import time
import wave
import ctypes
import platform
from chatgpt import ai_vision_audio_query, transcribe_audio


# --- Enable virtual cameras on macOS (Camo, OBS, etc.) ---
# On macOS 12.3+, DAL plugin virtual cameras are hidden from AVFoundation
# unless kCMIOHardwarePropertyAllowScreenCaptureDevices is set.
# This MUST be called before any cv2.VideoCapture() to see Camo.

def _enable_virtual_cameras():
    """Allow macOS to expose DAL-plugin virtual cameras (Camo, OBS, etc.) to OpenCV."""
    if platform.system() != "Darwin":
        return
    try:
        CoreMediaIO = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreMediaIO.framework/CoreMediaIO"
        )

        kCMIOObjectSystemObject = 1

        class CMIOObjectPropertyAddress(ctypes.Structure):
            _fields_ = [
                ("mSelector", ctypes.c_uint32),
                ("mScope", ctypes.c_uint32),
                ("mElement", ctypes.c_uint32),
            ]

        # kCMIOHardwarePropertyAllowScreenCaptureDevices = 'aasc'
        prop = CMIOObjectPropertyAddress(
            0x61617363,  # 'aasc'
            0x676C6F62,  # 'glob' (kCMIOObjectPropertyScopeGlobal)
            0x6D61696E,  # 'main' (kCMIOObjectPropertyElementMain)
        )
        allow = ctypes.c_uint32(1)
        CoreMediaIO.CMIOObjectSetPropertyData(
            ctypes.c_uint32(kCMIOObjectSystemObject),
            ctypes.byref(prop),
            ctypes.c_uint32(0),
            None,
            ctypes.c_uint32(ctypes.sizeof(allow)),
            ctypes.byref(allow),
        )
        print("[Video] Enabled macOS virtual camera support (DAL plugins)")
    except Exception as e:
        print(f"[Video] Could not enable virtual cameras: {e}")

_enable_virtual_cameras()


# --- Device discovery ---

def list_cameras(max_index=10):
    """List available camera device indices (brute-force probe)."""
    available = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available.append(i)
            cap.release()
    return available


def find_camo_camera():
    """
    Auto-detect the Camo virtual camera index by querying AVFoundation device names.
    Returns (index, name) or None if not found.

    Tries multiple methods:
      1. Swift subprocess (macOS built-in, no extra deps)
      2. ffmpeg AVFoundation enumeration (if ffmpeg is installed)

    OpenCV has no device-name API, so we ask the OS directly.
    """
    import subprocess, re

    # --- Method 1: Swift (always available on macOS) ---
    swift_code = r"""
import CoreMediaIO
import AVFoundation

// Enable virtual cameras (DAL plugins like Camo)
var prop = CMIOObjectPropertyAddress(
    mSelector: CMIOObjectPropertySelector(kCMIOHardwarePropertyAllowScreenCaptureDevices),
    mScope: CMIOObjectPropertyScope(kCMIOObjectPropertyScopeGlobal),
    mElement: CMIOObjectPropertyElement(kCMIOObjectPropertyElementMain)
)
var allow: UInt32 = 1
CMIOObjectSetPropertyData(
    CMIOObjectID(kCMIOObjectSystemObject),
    &prop, 0, nil,
    UInt32(MemoryLayout<UInt32>.size), &allow
)

let devices = AVCaptureDevice.DiscoverySession(
    deviceTypes: [.builtInWideAngleCamera, .external],
    mediaType: .video,
    position: .unspecified
).devices
for device in devices {
    print(device.localizedName)
}
"""
    try:
        proc = subprocess.run(
            ["swift", "/dev/stdin"],
            input=swift_code, capture_output=True, text=True, timeout=15,
        )
        names = [n.strip() for n in proc.stdout.strip().splitlines() if n.strip()]
        for i, name in enumerate(names):
            if "camo" in name.lower():
                print(f"[Video] Swift found Camo camera: '{name}' (AVFoundation index {i})")
                return i, name
        if names:
            print(f"[Video] Swift found cameras: {names} (no Camo)")
    except Exception as e:
        print(f"[Video] Swift device scan failed: {e}")

    # --- Method 2: ffmpeg (if installed) ---
    try:
        proc = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True, text=True, timeout=5,
        )
        in_video_section = False
        for line in proc.stderr.splitlines():
            if "AVFoundation video devices" in line:
                in_video_section = True
                continue
            if "AVFoundation audio devices" in line:
                break
            if in_video_section:
                m = re.search(r'\[(\d+)\]\s+(.+)', line)
                if m and "camo" in m.group(2).lower():
                    return int(m.group(1)), m.group(2).strip()
    except Exception as e:
        print(f"[Video] ffmpeg device scan failed: {e}")

    return None


def list_audio_devices():
    """List available audio input devices."""
    devices = sd.query_devices()
    inputs = [
        (i, d["name"], int(d["max_input_channels"]))
        for i, d in enumerate(devices)
        if d["max_input_channels"] > 0
    ]
    return inputs


def find_camo_audio_device():
    """Auto-detect the Camo Microphone audio device."""
    for idx, name, channels in list_audio_devices():
        if "camo" in name.lower():
            return idx, name, channels
    return None


# --- Audio capture (runs in its own thread) ---

SAMPLE_RATE    = 16000  # 16kHz is ideal for speech recognition
CHANNELS       = 1
AUDIO_CHUNK    = 1024

# VAD settings
SILENCE_THRESHOLD  = 0.02  # RMS below this is silence (float32 audio, range 0-1)
SILENCE_DURATION   = 0.8   # seconds of silence that marks end of utterance
MIN_SPEECH_SECONDS = 0.5   # discard clips shorter than this (noise/clicks)

# Periodic video analysis
VIDEO_INTERVAL = 1  # seconds between video-only GPT snapshots


# Updated by set_current_step() as the user progresses through a recipe
VIDEO_PROMPT       = "You are seeing a previous frame and a current frame. In one sentence, describe what changed between the two frames in terms of food preparation."
CURRENT_STEP_LABEL = None  # human-readable label printed in terminal during testing
LAST_STEP_MESSAGE  = ""    # dedup: reset when step changes

def _word_set(text: str) -> set:
    """Normalise a string and return its word set for similarity comparison."""
    import re as _re
    return set(_re.sub(r"[^a-z0-9 ]", "", text.lower()).split())


def _states_similar(a: str, b: str, threshold: float = 0.4) -> bool:
    """Return True if two state explanations are semantically similar enough to skip."""
    if not a or not b:
        return False
    wa, wb = _word_set(a), _word_set(b)
    if not wa or not wb:
        return False
    intersection = wa & wb
    union = wa | wb
    return len(intersection) / len(union) >= threshold


def set_current_step(step: str):
    """Update the VIDEO_PROMPT to check for the current recipe step using two-frame comparison."""
    global VIDEO_PROMPT, CURRENT_STEP_LABEL, LAST_STEP_MESSAGE
    CURRENT_STEP_LABEL = step
    LAST_STEP_MESSAGE = ""  # reset dedup on step change
    VIDEO_PROMPT = (
        f'You are a precise recipe vision assistant analyzing two consecutive frames from a live camera feed.\n'
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


audio_queue         = queue.Queue()
transcription_queue = queue.Queue()   # raw audio buffers ready to transcribe

# Two separate input queues for gpt_worker:
#   video_check_queue  — holds AT MOST ONE item (latest frame wins, old one dropped)
#   speech_queue       — holds all speech utterances in order (never dropped)
# This prevents the video queue from growing when GPT is slower than VIDEO_INTERVAL.
video_check_queue   = queue.Queue(maxsize=1)
speech_queue        = queue.Queue()

results_queue       = queue.Queue()   # parsed AI results pushed to SSE stream
audio_running       = threading.Event()

# Shared latest video frame — updated every frame by the main loop
latest_frame      = None
latest_frame_lock = threading.Lock()

# VU meter level — updated by the audio thread, read by the main loop
vu_level      = 0.0
vu_level_lock = threading.Lock()


def audio_callback(indata, frames, time, status):
    """Called by sounddevice for each audio chunk."""
    if status:
        print(f"[Audio] {status}")
    audio_queue.put(indata.copy())


def start_audio_stream(device_index):
    """Capture audio with VAD — emit complete utterances when the user stops talking."""
    audio_running.set()
    print(f"[Audio] Streaming from device index {device_index}")

    speech_buffer  = []
    silence_count  = 0
    is_speaking    = False
    silence_limit      = int(SAMPLE_RATE * SILENCE_DURATION / AUDIO_CHUNK)
    min_speech_chunks  = int(SAMPLE_RATE * MIN_SPEECH_SECONDS / AUDIO_CHUNK)

    with sd.InputStream(
        device=device_index,
        channels=CHANNELS,
        samplerate=SAMPLE_RATE,
        blocksize=AUDIO_CHUNK,
        callback=audio_callback,
    ):
        while audio_running.is_set():
            try:
                chunk = audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            rms = float(np.sqrt(np.mean(chunk ** 2)))

            # Update VU meter for the main video loop
            with vu_level_lock:
                global vu_level
                vu_level = rms

            if rms > SILENCE_THRESHOLD:
                if not is_speaking:
                    print("[Audio] Speech detected...")
                is_speaking   = True
                silence_count = 0
                speech_buffer.append(chunk)
            else:
                if is_speaking:
                    speech_buffer.append(chunk)
                    silence_count += 1
                    if silence_count >= silence_limit:
                        # User stopped talking — ship the utterance
                        if len(speech_buffer) >= min_speech_chunks:
                            audio_data = np.concatenate(speech_buffer, axis=0)
                            transcription_queue.put(audio_data.copy())
                            print("[Audio] Utterance complete, queued for transcription.")
                        speech_buffer = []
                        silence_count = 0
                        is_speaking   = False

    print("[Audio] Stream stopped.")


def transcribe_worker():
    """Continuously pull audio buffers, transcribe via Whisper, then queue for GPT."""
    while audio_running.is_set() or not transcription_queue.empty():
        try:
            audio_data = transcription_queue.get(timeout=1)
        except queue.Empty:
            continue

        # Convert numpy float32 → 16-bit PCM WAV in memory
        pcm = (audio_data * 32767).astype(np.int16)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())

        try:
            text = transcribe_audio(wav_buffer)
            if text:
                print(f"[Transcript] {text}")
                with latest_frame_lock:
                    frame_copy = latest_frame.copy() if latest_frame is not None else None
                speech_queue.put((text, frame_copy, True, CURRENT_STEP_LABEL))
        except Exception as e:
            print(f"[Transcript] Whisper error: {e}")


# --- Periodic video worker ---

def video_worker():
    """Send the latest frame to GPT every VIDEO_INTERVAL seconds for passive step analysis."""
    while audio_running.is_set():
        time.sleep(VIDEO_INTERVAL)
        with latest_frame_lock:
            frame_copy = latest_frame.copy() if latest_frame is not None else None
        if frame_copy is not None:
            # Discard any stale pending video check and replace with the freshest frame.
            # This keeps the queue at most 1 item so GPT never falls behind.
            try:
                video_check_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                video_check_queue.put_nowait((VIDEO_PROMPT, frame_copy, False, CURRENT_STEP_LABEL))
            except queue.Full:
                pass  # shouldn't happen after the drain above


# --- GPT worker ---

def gpt_worker(system_prompt=None):
    """Pull items from speech_queue (priority) or video_check_queue and send to GPT-4o."""
    import json
    global LAST_STEP_MESSAGE

    while audio_running.is_set() or not speech_queue.empty():
        # Speech has priority — process immediately if anything is waiting
        item = None
        try:
            item = speech_queue.get_nowait()
        except queue.Empty:
            # Nothing spoken — try the latest video check (0.5 s wait max)
            try:
                item = video_check_queue.get(timeout=0.5)
            except queue.Empty:
                continue

        text, frame, remember, step_label = item

        # Print a clean label so it's easy to read during testing
        if not remember:
            print(f"\n[Step Check] '{step_label or 'general observation'}'")
            print(f"[AI] ", end="", flush=True)
        else:
            print(f"\n[You said] '{text}'")
            print(f"[AI] ", end="", flush=True)

        try:
            chunks = []
            for chunk in ai_vision_audio_query(
                text, frame=frame, system_prompt=system_prompt, stream=True, remember=remember
            ):
                print(chunk, end="", flush=True)
                chunks.append(chunk)
            print()

            full = "".join(chunks)

            # If the pipeline was stopped while this call was in-flight, discard the result
            # so stale data never reaches the frontend SSE stream.
            if not audio_running.is_set():
                print("\n[GPT] Pipeline stopped — discarding in-flight result.")
                continue

            # Push result to SSE queue for the frontend
            if not remember:
                # Step check — try to parse as JSON.
                # GPT sometimes wraps the response in ```json ... ``` markdown fences;
                # strip those before parsing so we always get a dict.
                import re as _re
                clean = _re.sub(r"^```(?:json)?\s*", "", full.strip(), flags=_re.IGNORECASE)
                clean = _re.sub(r"\s*```$", "", clean.strip())
                try:
                    data = json.loads(clean)
                except json.JSONDecodeError:
                    data = full

                # Dedup: only push to frontend if action meaningfully changed
                if isinstance(data, dict):
                    action = data.get("action", {})
                    new_action_msg = action.get("explanation", "") if isinstance(action, dict) else ""
                    is_completed = data.get("completed") is True

                    if not is_completed and _states_similar(new_action_msg, LAST_STEP_MESSAGE):
                        print("[GPT] Skipping — action hasn't meaningfully changed.")
                        continue

                    LAST_STEP_MESSAGE = new_action_msg

                results_queue.put({
                    "type": "step_check",
                    "step": step_label,
                    "data": data,
                })
            else:
                # Speech response
                results_queue.put({
                    "type": "speech",
                    "step": step_label,
                    "data": full,
                })

        except Exception as e:
            print(f"[GPT] Error: {e}")


# --- Main feed ---

def get_camo_feed(camera_index=None, audio_device_index=None, system_prompt=None):
    """
    Capture video + audio from Camo (phone streamed to Mac).
    Transcribes speech, pairs it with the latest video frame, and sends
    both to GPT-4o for real-time analysis.

    Args:
        camera_index:       Video device index. Auto-detected if None.
        audio_device_index: Audio device index. Auto-detected if None.
        system_prompt:      Optional system message passed to GPT-4o on every call.

    Press 'q' to quit.
    """

    # --- Video setup ---
    if camera_index is None:
        camo = find_camo_camera()
        if camo:
            camera_index, cam_name = camo
            print(f"[Video] Found Camo camera: '{cam_name}' (index {camera_index})")
        else:
            cameras = list_cameras()
            print(f"[Video] Available camera indices: {cameras}")
            if not cameras:
                print("[Video] No cameras found. Is Camo connected?")
                return
            # Skip index 0 (built-in FaceTime) if there's another camera
            non_builtin = [i for i in cameras if i != 0]
            if non_builtin:
                camera_index = non_builtin[-1]
                print(f"[Video] Skipping built-in camera, using index: {camera_index}")
            else:
                camera_index = cameras[-1]
                print(f"[Video] Only built-in camera found, using index: {camera_index}")
    else:
        print(f"[Video] Using manually specified camera index: {camera_index}")

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[Video] Failed to open camera at index {camera_index}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # --- Audio setup ---
    if audio_device_index is None:
        result = find_camo_audio_device()
        if result:
            audio_device_index, name, _ = result
            print(f"[Audio] Found Camo Microphone: '{name}' (index {audio_device_index})")
        else:
            print("[Audio] Camo Microphone not found. Available input devices:")
            for idx, name, ch in list_audio_devices():
                print(f"  [{idx}] {name} ({ch} ch)")
            print("[Audio] Continuing without audio. Pass audio_device_index= to enable.")

    # Start audio + transcription + GPT threads
    audio_running.set()  # Always set so the video loop runs

    # Video analysis + GPT always run (they don't need audio)
    video_thread = threading.Thread(
        target=video_worker,
        daemon=True,
    )
    gpt_thread = threading.Thread(
        target=gpt_worker,
        kwargs={"system_prompt": system_prompt},
        daemon=True,
    )
    video_thread.start()
    gpt_thread.start()

    # Audio + transcription only if a microphone is available
    if audio_device_index is not None:
        audio_thread = threading.Thread(
            target=start_audio_stream,
            args=(audio_device_index,),
            daemon=True,
        )
        transcribe_thread = threading.Thread(
            target=transcribe_worker,
            daemon=True,
        )
        audio_thread.start()
        transcribe_thread.start()

    print(f"[Feed] Started — VAD active, video snapshot every {VIDEO_INTERVAL}s.\n")

    while audio_running.is_set():
        ret, frame = cap.read()
        if not ret:
            print("[Video] Failed to read frame.")
            break

        # Keep latest frame available for GPT worker and MJPEG stream
        with latest_frame_lock:
            global latest_frame
            latest_frame = frame.copy()

    # Cleanup
    audio_running.clear()
    cap.release()


# ---------------------------------------------------------------------------
# MJPEG helper — called by the FastAPI /camera/feed endpoint
# ---------------------------------------------------------------------------

def get_latest_frame_jpeg(quality: int = 70) -> bytes | None:
    """Return the latest camera frame encoded as JPEG bytes, or None if not ready."""
    with latest_frame_lock:
        frame = latest_frame.copy() if latest_frame is not None else None
    if frame is None:
        return None
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


def _flush_queue(q: queue.Queue):
    """Empty a queue without blocking."""
    while not q.empty():
        try:
            q.get_nowait()
        except queue.Empty:
            break


def stop_pipeline():
    """
    Immediately stop all pipeline workers and flush every queue.
    Call this instead of audio_running.clear() directly so that
    gpt_worker / transcribe_worker exit right away rather than
    draining stale items.
    """
    audio_running.clear()
    _flush_queue(audio_queue)
    _flush_queue(transcription_queue)
    _flush_queue(video_check_queue)
    _flush_queue(speech_queue)
    _flush_queue(results_queue)
    print("[Pipeline] Stopped and all queues flushed.")


