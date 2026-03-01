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
import re as _re
import json

from chatgpt import vision_step_check, speech_response, transcribe_audio


# ---------------------------------------------------------------------------
# macOS: expose DAL-plugin virtual cameras (Camo, OBS, etc.) to OpenCV
# Must run before any cv2.VideoCapture()
# ---------------------------------------------------------------------------

def _enable_virtual_cameras():
    if platform.system() != "Darwin":
        return
    try:
        CoreMediaIO = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreMediaIO.framework/CoreMediaIO"
        )

        class CMIOObjectPropertyAddress(ctypes.Structure):
            _fields_ = [
                ("mSelector", ctypes.c_uint32),
                ("mScope",    ctypes.c_uint32),
                ("mElement",  ctypes.c_uint32),
            ]

        prop = CMIOObjectPropertyAddress(
            0x61617363,  # 'aasc' kCMIOHardwarePropertyAllowScreenCaptureDevices
            0x676C6F62,  # 'glob' kCMIOObjectPropertyScopeGlobal
            0x6D61696E,  # 'main' kCMIOObjectPropertyElementMain
        )
        allow = ctypes.c_uint32(1)
        CoreMediaIO.CMIOObjectSetPropertyData(
            ctypes.c_uint32(1),  # kCMIOObjectSystemObject
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


# ---------------------------------------------------------------------------
# Device discovery
# ---------------------------------------------------------------------------

def list_cameras(max_index=10):
    """List available camera device indices."""
    available = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available.append(i)
            cap.release()
    return available


def _get_avfoundation_names():
    """
    Return an ordered list of AVFoundation video device names using Swift.
    The list order matches the AVFoundation index (0, 1, 2, ...).
    Returns [] on failure.
    """
    import subprocess

    # Enable DAL plugins in the Swift process too so Camo appears
    swift_code = r"""
import CoreMediaIO
import AVFoundation

var prop = CMIOObjectPropertyAddress(
    mSelector: CMIOObjectPropertySelector(kCMIOHardwarePropertyAllowScreenCaptureDevices),
    mScope: CMIOObjectPropertyScope(kCMIOObjectPropertyScopeGlobal),
    mElement: CMIOObjectPropertyElement(kCMIOObjectPropertyElementMain)
)
var allow: UInt32 = 1
CMIOObjectSetPropertyData(CMIOObjectID(kCMIOObjectSystemObject), &prop, 0, nil,
    UInt32(MemoryLayout<UInt32>.size), &allow)

let devices = AVCaptureDevice.DiscoverySession(
    deviceTypes: [.builtInWideAngleCamera, .external],
    mediaType: .video,
    position: .unspecified
).devices
for device in devices { print(device.localizedName) }
"""
    try:
        proc = subprocess.run(
            ["swift", "/dev/stdin"],
            input=swift_code, capture_output=True, text=True, timeout=15,
        )
        names = [n.strip() for n in proc.stdout.strip().splitlines() if n.strip()]
        print(f"[Video] AVFoundation devices: {names}")
        return names
    except Exception as e:
        print(f"[Video] Swift scan failed: {e}")
        return []


def find_camo_camera():
    """
    Auto-detect the Camo virtual camera and return its OpenCV index.

    The key problem: AVFoundation indices ≠ OpenCV indices.
    Swift tells us the *name* order; OpenCV assigns indices by probe order.
    On macOS, OpenCV probes in the same order as AVFoundation, so the
    AVFoundation position maps directly to the OpenCV index — BUT only
    after _enable_virtual_cameras() has already been called (done at import).

    Strategy:
      1. Get ordered AVFoundation names via Swift.
      2. Find "camo" in that list → that position is the OpenCV index.
      3. Verify by opening that OpenCV index and confirming it works.
      4. Fallback: if Swift fails, try ffmpeg for the index directly.

    Returns (opencv_index, name) or None.
    """
    import subprocess

    # --- Method 1: Swift name list → position = OpenCV index ---
    names = _get_avfoundation_names()
    for av_index, name in enumerate(names):
        if "camo" in name.lower():
            # Verify this index actually opens in OpenCV
            cap = cv2.VideoCapture(av_index)
            if cap.isOpened():
                cap.release()
                print(f"[Video] Camo confirmed at OpenCV index {av_index} ('{name}')")
                return av_index, name
            else:
                # Index mismatch — scan all OpenCV indices and return the
                # first non-zero one that opens (Camo is never index 0)
                print(f"[Video] AVFoundation index {av_index} didn't open in OpenCV, scanning...")
                for cv_index in range(1, 10):
                    cap = cv2.VideoCapture(cv_index)
                    if cap.isOpened():
                        cap.release()
                        print(f"[Video] Using OpenCV index {cv_index} for Camo '{name}'")
                        return cv_index, name
                cap.release()

    # --- Method 2: ffmpeg (gives AVFoundation indices directly) ---
    try:
        proc = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True, text=True, timeout=5,
        )
        in_video = False
        for line in proc.stderr.splitlines():
            if "AVFoundation video devices" in line:
                in_video = True
                continue
            if "AVFoundation audio devices" in line:
                break
            if in_video:
                m = _re.search(r'\[(\d+)\]\s+(.+)', line)
                if m and "camo" in m.group(2).lower():
                    idx, name = int(m.group(1)), m.group(2).strip()
                    print(f"[Video] ffmpeg found Camo: '{name}' at index {idx}")
                    return idx, name
    except Exception as e:
        print(f"[Video] ffmpeg scan failed: {e}")

    return None


def list_audio_devices():
    """List available audio input devices."""
    devices = sd.query_devices()
    return [
        (i, d["name"], int(d["max_input_channels"]))
        for i, d in enumerate(devices)
        if d["max_input_channels"] > 0
    ]


def find_camo_audio_device():
    """Auto-detect the Camo Microphone audio device."""
    for idx, name, channels in list_audio_devices():
        if "camo" in name.lower():
            return idx, name, channels
    return None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE   = 16000   # Hz — optimal for Whisper
CHANNELS      = 1
AUDIO_CHUNK   = 1024

# VAD
SILENCE_THRESHOLD  = 0.02   # RMS below this = silence
SILENCE_DURATION   = 0.4    # seconds of silence = end of utterance (snappy)
MIN_SPEECH_SECONDS = 0.3    # discard clips shorter than this

# Video analysis
VIDEO_INTERVAL = 1  # seconds between passive step checks


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------

# Set by set_current_step() / set_current_recipe() as the session progresses
CURRENT_STEP       = None   # step text passed to vision_step_check
CURRENT_STEP_LABEL = None   # same value, kept as alias for clarity
CURRENT_RECIPE     = None   # recipe name/description set at session start
ALL_STEPS          = []     # full ordered list of steps for context
LAST_STEP_MESSAGE  = ""     # dedup: reset when step changes

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
    global CURRENT_STEP, CURRENT_STEP_LABEL, LAST_STEP_MESSAGE
    CURRENT_STEP = step
    CURRENT_STEP_LABEL = step
    LAST_STEP_MESSAGE = ""  # reset dedup on step change

def set_current_recipe(recipe: str, steps: list[str] = []):
    global CURRENT_RECIPE, ALL_STEPS
    CURRENT_RECIPE = recipe
    ALL_STEPS = steps
    # Clear conversation history so each new recipe starts a fresh chat
    import chatgpt
    chatgpt.conversation_history.clear()

# Queues
audio_queue         = queue.Queue()
transcription_queue = queue.Queue()   # raw audio buffers → transcribe_worker
speech_queue        = queue.Queue()   # (text, frame, step_label) → gpt_worker (priority)
video_check_queue   = queue.Queue(maxsize=1)  # latest frame only, old dropped
results_queue       = queue.Queue()   # parsed AI results → SSE stream

audio_running       = threading.Event()

# Shared latest frame
latest_frame        = None
latest_frame_lock   = threading.Lock()

# Previous frame for two-frame step checks
_prev_frame_lock    = threading.Lock()
_prev_frame         = None

# VU meter
vu_level      = 0.0
vu_level_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Audio capture + VAD
# ---------------------------------------------------------------------------

def audio_callback(indata, frames, time, status):
    if status:
        print(f"[Audio] {status}")
    audio_queue.put(indata.copy())


def start_audio_stream(device_index):
    """Capture audio with VAD — emit complete utterances when the user stops talking."""
    print(f"[Audio] Streaming from device {device_index}")

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
                        if len(speech_buffer) >= min_speech_chunks:
                            audio_data = np.concatenate(speech_buffer, axis=0)
                            transcription_queue.put(audio_data.copy())
                            print("[Audio] Utterance queued for transcription.")
                        speech_buffer = []
                        silence_count = 0
                        is_speaking   = False

    print("[Audio] Stream stopped.")


# ---------------------------------------------------------------------------
# Transcription worker — Whisper + wake word filter
# ---------------------------------------------------------------------------

_WAKE_WORD = "remy"

def transcribe_worker():
    """Transcribe audio buffers via Whisper, then forward to gpt_worker only if wake word heard."""
    while audio_running.is_set() or not transcription_queue.empty():
        try:
            audio_data = transcription_queue.get(timeout=1)
        except queue.Empty:
            continue

        pcm = (audio_data * 32767).astype(np.int16)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())

        try:
            text = transcribe_audio(wav_buffer)
            if not text:
                continue

            print(f"[Transcript] {text}")

            # Wake word filter — only respond when user says "remy"
            if _WAKE_WORD not in text.lower():
                print("[Wake] No wake word — skipping.")
                continue

            with latest_frame_lock:
                frame_copy = latest_frame.copy() if latest_frame is not None else None

            speech_queue.put((text, frame_copy, CURRENT_STEP_LABEL))

        except Exception as e:
            print(f"[Transcript] Whisper error: {e}")


# ---------------------------------------------------------------------------
# Periodic video worker
# ---------------------------------------------------------------------------

def video_worker():
    """Push latest frame to video_check_queue every VIDEO_INTERVAL seconds."""
    while audio_running.is_set():
        time.sleep(VIDEO_INTERVAL)

        with latest_frame_lock:
            frame_copy = latest_frame.copy() if latest_frame is not None else None

        if frame_copy is not None and CURRENT_STEP:
            # Replace any stale pending check with the freshest frame
            try:
                video_check_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                video_check_queue.put_nowait((frame_copy, CURRENT_STEP_LABEL))
            except queue.Full:
                pass


# ---------------------------------------------------------------------------
# GPT worker
# ---------------------------------------------------------------------------

def gpt_worker():
    """
    Process speech (priority) and video check items through GPT.
    """
    import json
    global LAST_STEP_MESSAGE

    Speech items  → speech_response()   → conversational reply → SSE "speech" event
    Video items   → vision_step_check() → JSON step check      → SSE "step_check" event
    """
    while audio_running.is_set() or not speech_queue.empty():
        # Speech has priority
        item = None
        is_speech = False
        try:
            item = speech_queue.get_nowait()
            is_speech = True
        except queue.Empty:
            try:
                item = video_check_queue.get(timeout=0.5)
            except queue.Empty:
                continue

        if not audio_running.is_set():
            # Pipeline stopping — discard in-flight items
            continue

        if is_speech:
            text, frame, step_label = item
            print(f"\n[You said] '{text}'")
            print("[Remy] ", end="", flush=True)

            try:
                chunks = []
                for chunk in speech_response(
                    text,
                    frame=frame,
                    recipe=CURRENT_RECIPE,
                    current_step=CURRENT_STEP,
                    all_steps=ALL_STEPS,
                ):
                    print(chunk, end="", flush=True)
                    chunks.append(chunk)
                print()

                if not audio_running.is_set():
                    continue

                results_queue.put({
                    "type":  "speech",
                    "step":  step_label,
                    "data":  "".join(chunks),
                })
            except Exception as e:
                print(f"[GPT speech] Error: {e}")

        else:
            frame, step_label = item
            print(f"\n[Step Check] '{step_label or 'no step set'}'")

            if not CURRENT_STEP:
                continue

            with _prev_frame_lock:
                global _prev_frame
                prev = _prev_frame.copy() if _prev_frame is not None else None
                _prev_frame = frame.copy()

            try:
                raw = vision_step_check(CURRENT_STEP, frame, previous_frame=prev)
                print(f"[AI] {raw}")

                if not audio_running.is_set():
                    continue

                # Strip markdown fences if GPT wrapped the JSON anyway
                clean = _re.sub(r"^```(?:json)?\s*", "", raw, flags=_re.IGNORECASE)
                clean = _re.sub(r"\s*```$", "", clean.strip())

                try:
                    data = json.loads(clean)
                except json.JSONDecodeError:
                    # Non-JSON response — discard, don't bleed into speech channel
                    print("[Step Check] Non-JSON response discarded.")
                    continue

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
            except Exception as e:
                print(f"[GPT video] Error: {e}")


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def get_camo_feed(camera_index=None, audio_device_index=None):
    """
    Start video + audio pipeline.

    Args:
        camera_index:       Video device index. Auto-detected if None.
        audio_device_index: Audio device index. Auto-detected if None.
    """
    global latest_frame, _prev_frame

    # --- Video setup ---
    if camera_index is None:
        camo = find_camo_camera()
        if camo:
            camera_index, cam_name = camo
            print(f"[Video] Using Camo: '{cam_name}' (OpenCV index {camera_index})")
        else:
            # Camo not found — list what's available and pick the first non-builtin.
            # Never silently fall back to index 0 (FaceTime/built-in) if there's
            # another camera present, since that's almost certainly not what we want.
            cameras = list_cameras()
            print(f"[Video] Camo not found. Available OpenCV indices: {cameras}")
            if not cameras:
                print("[Video] No cameras found. Is Camo running on your phone?")
                return
            non_builtin = [i for i in cameras if i != 0]
            if non_builtin:
                camera_index = non_builtin[0]  # first non-FaceTime camera
                print(f"[Video] Using first non-builtin camera at index {camera_index}")
            else:
                # Only the built-in camera is available — use it with a warning
                camera_index = 0
                print("[Video] WARNING: Only built-in (FaceTime) camera found. Is Camo connected?")
    else:
        print(f"[Video] Using manually specified camera index: {camera_index}")

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[Video] Failed to open camera {camera_index}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # --- Audio setup ---
    if audio_device_index is None:
        result = find_camo_audio_device()
        if result:
            audio_device_index, name, _ = result
            print(f"[Audio] Found Camo Mic: '{name}' (index {audio_device_index})")
        else:
            print("[Audio] Camo Mic not found. Available inputs:")
            for idx, name, ch in list_audio_devices():
                print(f"  [{idx}] {name} ({ch} ch)")
            print("[Audio] Continuing without audio.")

    # --- Start workers ---
    audio_running.set()
    _prev_frame = None

    video_thread = threading.Thread(target=video_worker, daemon=True)
    gpt_thread   = threading.Thread(target=gpt_worker,   daemon=True)
    video_thread.start()
    gpt_thread.start()

    if audio_device_index is not None:
        audio_thread    = threading.Thread(target=start_audio_stream, args=(audio_device_index,), daemon=True)
        transcribe_thread = threading.Thread(target=transcribe_worker, daemon=True)
        audio_thread.start()
        transcribe_thread.start()

    print(f"[Feed] Started — wake word '{_WAKE_WORD}', VAD silence={SILENCE_DURATION}s, video every {VIDEO_INTERVAL}s.")

    while audio_running.is_set():
        ret, frame = cap.read()
        if not ret:
            print("[Video] Failed to read frame.")
            break
        with latest_frame_lock:
            latest_frame = frame.copy()

    audio_running.clear()
    cap.release()
    print("[Feed] Stopped.")


# ---------------------------------------------------------------------------
# MJPEG helper
# ---------------------------------------------------------------------------

def get_latest_frame_jpeg(quality: int = 70) -> bytes | None:
    with latest_frame_lock:
        frame = latest_frame.copy() if latest_frame is not None else None
    if frame is None:
        return None
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


# ---------------------------------------------------------------------------
# Pipeline shutdown
# ---------------------------------------------------------------------------

def _flush_queue(q: queue.Queue):
    while not q.empty():
        try:
            q.get_nowait()
        except queue.Empty:
            break


def stop_pipeline():
    """Stop all workers and flush all queues immediately."""
    audio_running.clear()
    _flush_queue(audio_queue)
    _flush_queue(transcription_queue)
    _flush_queue(video_check_queue)
    _flush_queue(speech_queue)
    _flush_queue(results_queue)
    print("[Pipeline] Stopped and queues flushed.")
