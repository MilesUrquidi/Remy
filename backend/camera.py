import cv2
import sounddevice as sd
import numpy as np
import threading
import queue
import io
import wave
import speech_recognition as sr


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

SAMPLE_RATE = 16000   # 16kHz is ideal for speech recognition
CHANNELS = 1
AUDIO_CHUNK = 1024
TRANSCRIBE_SECONDS = 3  # Transcribe every N seconds of audio

audio_queue = queue.Queue()
transcription_queue = queue.Queue()  # Holds raw audio buffers ready to transcribe
audio_running = threading.Event()


def audio_callback(indata, frames, time, status):
    """Called by sounddevice for each audio chunk."""
    if status:
        print(f"[Audio] {status}")
    audio_queue.put(indata.copy())


def start_audio_stream(device_index):
    """Capture audio and batch it into TRANSCRIBE_SECONDS chunks."""
    audio_running.set()
    print(f"[Audio] Streaming from device index {device_index}")

    buffer = []
    samples_needed = SAMPLE_RATE * TRANSCRIBE_SECONDS

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
                buffer.append(chunk)
                total_samples = sum(c.shape[0] for c in buffer)
                if total_samples >= samples_needed:
                    audio_data = np.concatenate(buffer, axis=0)
                    transcription_queue.put(audio_data.copy())
                    buffer = []
            except queue.Empty:
                continue

    print("[Audio] Stream stopped.")


def transcribe_worker():
    """Continuously pull audio buffers and transcribe them to text."""
    recognizer = sr.Recognizer()

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
        wav_buffer.seek(0)

        audio_source = sr.AudioFile(wav_buffer)
        with audio_source as source:
            audio = recognizer.record(source)

        try:
            text = recognizer.recognize_google(audio)
            if text.strip():
                print(f"[Transcript] {text}")
        except sr.UnknownValueError:
            pass  # Silence or unintelligible audio — skip
        except sr.RequestError as e:
            print(f"[Transcript] Google API error: {e}")


# --- Main feed ---

def get_camo_feed(camera_index=None, audio_device_index=None):
    """
    Capture video + audio from Camo (phone streamed to Mac).
    Transcribes speech to text and prints it to the console.

    Args:
        camera_index:       Video device index. Auto-detected if None.
        audio_device_index: Audio device index. Auto-detected if None.

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

    # Start audio + transcription threads
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
        audio_thread.start()
        transcribe_thread.start()

    print(f"[Feed] Started — transcribing every {TRANSCRIBE_SECONDS}s. Press 'q' to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Video] Failed to read frame.")
            break

        # VU meter: drain audio_queue for level display
        level = 0
        while not audio_queue.empty():
            chunk = audio_queue.get_nowait()
            level = int(np.abs(chunk).mean() * 2000)

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


if __name__ == "__main__":
    get_camo_feed()
