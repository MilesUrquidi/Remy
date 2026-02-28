import cv2
import sounddevice as sd
import numpy as np
import threading
import queue
import io
import time
import wave
from chatgpt import ai_vision_audio_query, transcribe_audio


# --- Device discovery ---

def list_cameras(max_index=5):
    """List available camera devices."""
    available = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available.append(i)
            cap.release()
    return available


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

def set_current_step(step: str):
    """Update the VIDEO_PROMPT to check for the current recipe step using two-frame comparison."""
    global VIDEO_PROMPT, CURRENT_STEP_LABEL
    CURRENT_STEP_LABEL = step
    VIDEO_PROMPT = (
        f'You are a precise recipe vision assistant analyzing two frames from a live camera feed.\n'
        f'The current recipe step to verify is: "{step}"\n\n'
        f'Examine both the previous frame and the current frame carefully, then return ONLY a raw JSON object '
        f'with exactly this structure (no markdown, no explanation outside the JSON):\n'
        f'{{\n'
        f'  "completed": <true if state.completed OR action.completed is true, otherwise false>,\n'
        f'  "state": {{"completed": <true if the result of the step is clearly visible in the current frame>, "explanation": "<one sentence describing what you see in the current frame>"}},\n'
        f'  "action": {{"completed": <true if a visible change occurred between the two frames that completes this step>, "explanation": "<one sentence describing what changed between the frames>"}}\n'
        f'}}\n\n'
        f'Rules:\n'
        f'- completed is true if state.completed OR action.completed is true\n'
        f'- Be strict: only mark completed true if you are clearly sure\n'
        f'- Keep explanations to one short sentence each\n'
        f'- Return raw JSON only, no markdown code blocks'
    )


audio_queue        = queue.Queue()
transcription_queue = queue.Queue()  # raw audio buffers ready to transcribe
gpt_input_queue    = queue.Queue()   # (text, frame) pairs ready for GPT
audio_running      = threading.Event()

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
                gpt_input_queue.put((text, frame_copy, True))  # remember=True
        except Exception as e:
            print(f"[Transcript] Whisper error: {e}")


# --- Periodic video worker ---

def video_worker():
    """Send the latest frame to GPT every VIDEO_INTERVAL seconds for passive form analysis."""
    while audio_running.is_set():
        time.sleep(VIDEO_INTERVAL)
        with latest_frame_lock:
            frame_copy = latest_frame.copy() if latest_frame is not None else None
        if frame_copy is not None:
            gpt_input_queue.put((VIDEO_PROMPT, frame_copy, False))  # remember=False


# --- GPT worker ---

def gpt_worker(system_prompt=None):
    """Pull (text, frame, remember) tuples from gpt_input_queue and send to GPT-4o."""
    while audio_running.is_set() or not gpt_input_queue.empty():
        try:
            text, frame, remember = gpt_input_queue.get(timeout=1)
        except queue.Empty:
            continue

        # Print a clean label so it's easy to read during testing
        if not remember:
            label = CURRENT_STEP_LABEL or "general observation"
            print(f"\n[Step Check] '{label}'")
            print(f"[AI] ", end="", flush=True)
        else:
            print(f"\n[You said] '{text}'")
            print(f"[AI] ", end="", flush=True)

        try:
            for chunk in ai_vision_audio_query(
                text, frame=frame, system_prompt=system_prompt, stream=True, remember=remember
            ):
                print(chunk, end="", flush=True)
            print()
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
        cameras = list_cameras()
        print(f"[Video] Available cameras: {cameras}")
        if not cameras:
            print("[Video] No cameras found.")
            return
        camera_index = cameras[-1]
        print(f"[Video] Using camera index: {camera_index}")

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
    if audio_device_index is not None:
        audio_running.set()

        audio_thread = threading.Thread(
            target=start_audio_stream,
            args=(audio_device_index,),
            daemon=True,
        )
        transcribe_thread = threading.Thread(
            target=transcribe_worker,
            daemon=True,
        )
        gpt_thread = threading.Thread(
            target=gpt_worker,
            kwargs={"system_prompt": system_prompt},
            daemon=True,
        )
        video_thread = threading.Thread(
            target=video_worker,
            daemon=True,
        )
        audio_thread.start()
        transcribe_thread.start()
        gpt_thread.start()
        video_thread.start()

    print(f"[Feed] Started — VAD active, video snapshot every {VIDEO_INTERVAL}s. Press 'q' to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Video] Failed to read frame.")
            break

        # Keep latest frame available for GPT worker
        with latest_frame_lock:
            global latest_frame
            latest_frame = frame.copy()

        # VU meter: read level published by the audio thread
        with vu_level_lock:
            level = int(vu_level * 2000)

        level = min(level, frame.shape[1] - 20)
        cv2.rectangle(frame, (10, frame.shape[0] - 20), (10 + level, frame.shape[0] - 10),
                      (0, 255, 100), -1)
        cv2.putText(frame, "MIC", (10, frame.shape[0] - 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 100), 1)

        cv2.imshow("Camo Feed", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # Cleanup
    audio_running.clear()
    cap.release()
    cv2.destroyAllWindows()


