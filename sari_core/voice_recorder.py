"""
Voice Recording & Transcription Engine untuk Harmoni Agent.
Merekam audio langsung dari input audio Windows (Sound Mapper / Mikrofon Studio)
dan mentranskripsikannya ke teks bahasa Indonesia secara presisi via Gemini 2.5 Flash.
"""

import os
import wave
import time
import threading
from pathlib import Path
import sounddevice as sd
import numpy as np
from dotenv import dotenv_values

from sari_core.paths import PROJECT_ROOT

class VoiceRecorder:
    _instance = None

    def __init__(self):
        self.is_recording = False
        self.stream = None
        self.frames = []
        self.start_time = 0
        self.lock = threading.Lock()
        self.sample_rate = 16000

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = VoiceRecorder()
        return cls._instance

    def _callback(self, indata, frames_count, time_info, status):
        if self.is_recording:
            self.frames.append(indata.copy())

    def start_recording(self) -> dict:
        with self.lock:
            if self.is_recording:
                return {"status": "already_recording"}
            self.frames = []
            self.is_recording = True
            self.start_time = time.time()
            try:
                self.stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype='int16',
                    callback=self._callback
                )
                self.stream.start()
                return {"status": "recording_started", "sample_rate": self.sample_rate}
            except Exception as e:
                self.is_recording = False
                self.stream = None
                return {"status": "error", "message": str(e)}

    def stop_recording(self) -> dict:
        with self.lock:
            if not self.is_recording:
                return {"status": "not_recording", "text": ""}
            self.is_recording = False
            if self.stream:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None

            if not self.frames:
                return {"status": "empty", "text": ""}

            audio_data = np.concatenate(self.frames, axis=0)
            max_amp = int(np.max(np.abs(audio_data)))
            duration_sec = len(audio_data) / self.sample_rate

            # Jika terlalu hening (kurang dari batas noise)
            if max_amp < 350:
                return {"status": "silent", "text": "", "amplitude": max_amp, "duration": duration_sec}

            out_dir = PROJECT_ROOT / "File" / "Temp"
            out_dir.mkdir(parents=True, exist_ok=True)
            wav_path = out_dir / "voice_input.wav"

            with wave.open(str(wav_path), 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_data.tobytes())

        # Transkripsi audio
        text = self._transcribe(wav_path)
        return {"status": "ok", "text": text, "amplitude": max_amp, "duration": duration_sec}

    def _transcribe(self, wav_path: Path) -> str:
        try:
            from google import genai
            env_path = PROJECT_ROOT / ".env"
            d = dotenv_values(str(env_path))
            api_key = d.get("GEMINI_API_KEY", "").strip()
            if not api_key:
                return ""
            client = genai.Client(api_key=api_key)
            with open(str(wav_path), "rb") as f:
                audio_bytes = f.read()

            prompt = (
                "Transkripsikan rekaman suara percakapan bahasa Indonesia ini secara akurat kata demi kata. "
                "HANYA berikan teks transkripsinya saja tanpa tanda petik, tanpa salam, tanpa kalimat 'berikut adalah', "
                "dan jika suara tidak jelas atau hanya hening/desis, balas dengan string kosong."
            )

            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    genai.types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                    prompt
                ]
            )
            raw = resp.text.strip() if resp and resp.text else ""
            # Bersihkan jika LLM membalas kalimat pengantar
            lowered = raw.lower()
            if any(lowered.startswith(x) for x in ["saya akan", "berikut transkripsi", "tidak ada suara", "audio hening", "tidak ada kata"]):
                return ""
            return raw.strip('"\'')
        except Exception as e:
            print(f"[VoiceRecorder] Gagal mentranskripsi: {e}")
            return ""

voice_recorder = VoiceRecorder.get_instance()
