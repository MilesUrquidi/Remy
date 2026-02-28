import os
import re
import subprocess
import sounddevice as sd
import numpy as np
import io
import wave
from openai import OpenAI
from dotenv import load_dotenv
from icrawler.builtin import BingImageCrawler

load_dotenv()
client = OpenAI()

SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 0.02
SILENCE_DURATION = 1.0


def show_help(term: str):
    """Get a simple description and show a real image of the term."""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Explain this in 2 simple sentences for a beginner. No jargon."},
            {"role": "user", "content": f"What is a {term}?"}
        ]
    )
    print(f"\n{response.choices[0].message.content.strip()}\n")

    save_dir = f"/tmp/{term.replace(' ', '_')}"
    os.makedirs(save_dir, exist_ok=True)
    BingImageCrawler(storage={"root_dir": save_dir}).crawl(keyword=term, max_num=1)

    for file in os.listdir(save_dir):
        subprocess.Popen(["open", os.path.join(save_dir, file)])
        return


def listen_and_detect():
    """Continuously listen for 'what is X' phrases and trigger show_help."""
    print("🎙️  Context help is listening... (say 'what is a [thing]' anytime)\n")

    while True:
        # Record until silence
        audio_chunks = []
        silence_count = 0
        speaking = False
        silence_limit = int(SAMPLE_RATE * SILENCE_DURATION / 1024)

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, blocksize=1024) as stream:
            while True:
                chunk, _ = stream.read(1024)
                rms = float(np.sqrt(np.mean(chunk ** 2)))

                if rms > SILENCE_THRESHOLD:
                    speaking = True
                    silence_count = 0
                    audio_chunks.append(chunk)
                elif speaking:
                    audio_chunks.append(chunk)
                    silence_count += 1
                    if silence_count >= silence_limit:
                        break

        if not audio_chunks:
            continue

        # Transcribe with Whisper
        audio_data = np.concatenate(audio_chunks)
        pcm = (audio_data * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())
        buf.seek(0)

        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.wav", buf, "audio/wav"),
        ).text.strip()

        if not transcript:
            continue

        print(f"[Heard] {transcript}")

        # Detect "what is a X" or "I don't know what X is"
        match = re.search(r"what(?:'s| is) (?:a |an )?([\w\s]+?)(?:\?|$)", transcript, re.IGNORECASE)
        if match:
            show_help(match.group(1).strip())


if __name__ == "__main__":
    listen_and_detect()
