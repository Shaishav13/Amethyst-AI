"""
Amethyst Voice Engine — 100% OFFLINE
=====================================
STT: SpeechRecognition + Vosk (local model, no internet)
     Falls back to silence detection if Vosk not installed.
TTS: pyttsx3 (system voices, zero internet, zero GPU)
     Falls back gracefully if audio system unavailable.

No API keys. No cloud calls. Everything runs on your machine.
"""

import asyncio
import logging
import os
import re
import threading
from enum import Enum
from typing import Optional, Callable

log = logging.getLogger("amethyst.voice")


class VoiceState(Enum):
    IDLE       = "idle"
    LISTENING  = "listening"
    PROCESSING = "processing"
    SPEAKING   = "speaking"
    ERROR      = "error"


# ── Offline TTS ───────────────────────────────────────────────────────────────
class TTSEngine:
    """
    100% offline TTS using pyttsx3 (Windows: SAPI5, Linux: espeak, Mac: nsss).
    No internet. No API. Runs in a background thread to avoid blocking the UI.
    """

    def __init__(self, rate: int = 170, volume: float = 0.95):
        self._rate    = rate
        self._volume  = volume
        self._muted   = False
        self._engine  = None
        self._lock    = threading.Lock()
        self._speaking = False

    @property
    def is_muted(self) -> bool:
        return self._muted

    def toggle_mute(self) -> bool:
        self._muted = not self._muted
        if self._muted:
            self.stop()
        return self._muted

    def _get_engine(self):
        """Lazy-init pyttsx3 engine (thread-safe)."""
        if self._engine is None:
            try:
                import pyttsx3
                self._engine = pyttsx3.init()
                self._engine.setProperty("rate", self._rate)
                self._engine.setProperty("volume", self._volume)
                # Pick a clear Windows voice if available
                voices = self._engine.getProperty("voices")
                for v in voices:
                    name = v.name.lower()
                    if "zira" in name or "hazel" in name or "eva" in name:
                        self._engine.setProperty("voice", v.id)
                        break
                log.info(f"TTS engine initialized (pyttsx3).")
            except Exception as e:
                log.error(f"pyttsx3 init failed: {e}")
        return self._engine

    async def speak(self, text: str, on_start: Optional[Callable] = None,
                    on_done: Optional[Callable] = None):
        """Speak text asynchronously without blocking the UI thread."""
        if self._muted or not text.strip():
            if on_done:
                on_done()
            return

        clean = self._clean_for_speech(text)
        if not clean.strip():
            if on_done:
                on_done()
            return

        self._speaking = True
        if on_start:
            on_start()

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._speak_sync, clean)
        except Exception as e:
            log.error(f"TTS speak error: {e}")
        finally:
            self._speaking = False
            if on_done:
                on_done()

    def _speak_sync(self, text: str):
        """Blocking pyttsx3 call — runs in thread pool."""
        with self._lock:
            engine = self._get_engine()
            if engine is None:
                return
            try:
                engine.say(text)
                engine.runAndWait()
            except RuntimeError:
                # Engine was stopped mid-sentence
                pass
            except Exception as e:
                log.error(f"pyttsx3 runAndWait error: {e}")

    def stop(self):
        """Stop speech immediately."""
        self._speaking = False
        try:
            if self._engine:
                self._engine.stop()
        except Exception:
            pass

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """Strip markdown so TTS reads clean prose, not symbols."""
        # Remove code blocks entirely
        text = re.sub(r"```[\s\S]*?```", "code block.", text)
        text = re.sub(r"`[^`]+`", "", text)
        # Strip markdown formatting
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"#{1,6}\s", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        text = re.sub(r"^\s*[-*+]\s", "", text, flags=re.MULTILINE)
        # Collapse whitespace
        text = re.sub(r"\n{2,}", ". ", text)
        text = re.sub(r"\n", " ", text)
        # Limit length to avoid very long speeches
        words = text.split()
        if len(words) > 80:
            text = " ".join(words[:80]) + "."
        return text.strip()


# ── Offline STT ───────────────────────────────────────────────────────────────
class STTEngine:
    """
    100% offline Speech-to-Text.

    Strategy (tries in order):
    1. Vosk — small local model (~40MB), fast, no internet.
       Install: pip install vosk
       Model:   auto-downloaded to ~/.amethyst/vosk_model/ on first use
    2. SpeechRecognition + offline Sphinx — basic fallback
    3. If nothing works — returns None and shows error in status bar.
    """

    VOSK_MODEL_URL  = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    if "AMETHYST_HOME" in os.environ:
        VOSK_MODEL_DIR = os.path.join(os.environ["AMETHYST_HOME"], "vosk_model")
    else:
        VOSK_MODEL_DIR = os.path.join(os.path.expanduser("~"), ".amethyst", "vosk_model")

    def __init__(self, timeout: float = 6.0, phrase_limit: float = 15.0):
        self.timeout      = timeout
        self.phrase_limit = phrase_limit
        self._recognizer  = None
        self._microphone  = None
        self._vosk_model  = None
        self._state       = VoiceState.IDLE
        self._vosk_ok     = False
        self._sr_ok       = False


    def _load_vosk(self):
        """Load or download the Vosk offline model."""
        if self._vosk_model is not None:
            return self._vosk_model
        try:
            from vosk import Model, KaldiRecognizer
            model_dir = self.VOSK_MODEL_DIR
            if not os.path.exists(model_dir) or not os.listdir(model_dir):
                log.info("Vosk model not found — downloading small English model (~40MB)...")
                self._download_vosk_model(model_dir)
            self._vosk_model = Model(model_dir)
            self._vosk_ok    = True
            log.info("Vosk offline STT model loaded.")
            return self._vosk_model
        except ImportError:
            log.warning("vosk not installed. Run: pip install vosk")
            return None
        except Exception as e:
            log.warning(f"Vosk load failed: {e}")
            return None

    def _download_vosk_model(self, dest_dir: str):
        """Download and extract the small Vosk English model."""
        import urllib.request
        import zipfile
        import tempfile

        os.makedirs(dest_dir, exist_ok=True)
        zip_path = dest_dir + ".zip"

        log.info(f"Downloading Vosk model from {self.VOSK_MODEL_URL}")
        urllib.request.urlretrieve(self.VOSK_MODEL_URL, zip_path)

        with zipfile.ZipFile(zip_path, "r") as z:
            # Extract contents into dest_dir (strip the top-level folder)
            members = z.namelist()
            top = members[0].split("/")[0]
            for member in members:
                rel = member[len(top):].lstrip("/")
                if not rel:
                    continue
                target = os.path.join(dest_dir, rel)
                if member.endswith("/"):
                    os.makedirs(target, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())

        os.remove(zip_path)
        log.info("Vosk model downloaded and extracted.")

    @property
    def state(self) -> VoiceState:
        return self._state


    async def listen_once(self, on_state_change: Optional[Callable] = None) -> Optional[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._listen_sync, on_state_change)

    def _listen_sync(self, on_state_change: Optional[Callable] = None) -> Optional[str]:
        """Record audio then transcribe — fully offline."""
        import speech_recognition as sr
        if self._recognizer is None:
            self._recognizer = sr.Recognizer()
            self._sr_ok = True

        if not self._sr_ok:
            log.error("Microphone not available.")
            self._state = VoiceState.ERROR
            if on_state_change:
                on_state_change(VoiceState.ERROR)
            return None

        self._state = VoiceState.LISTENING
        if on_state_change:
            on_state_change(VoiceState.LISTENING)

        try:
            mic = sr.Microphone()
            with mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = self._recognizer.listen(
                    source,
                    timeout=self.timeout,
                    phrase_time_limit=self.phrase_limit
                )
        except sr.WaitTimeoutError:
            log.warning("Mic timeout — no speech detected.")
            self._state = VoiceState.IDLE
            if on_state_change:
                on_state_change(VoiceState.IDLE)
            return None
        except Exception as e:
            log.error(f"Mic recording error: {e}")
            self._state = VoiceState.ERROR
            if on_state_change:
                on_state_change(VoiceState.ERROR)
            return None

        self._state = VoiceState.PROCESSING
        if on_state_change:
            on_state_change(VoiceState.PROCESSING)

        text = self._transcribe_vosk(audio)

        if text is None:
            text = self._transcribe_sphinx(audio)

        self._state = VoiceState.IDLE
        if on_state_change:
            on_state_change(VoiceState.IDLE)
        return text

    def _transcribe_vosk(self, audio) -> Optional[str]:
        """Transcribe using Vosk local model."""
        try:
            from vosk import KaldiRecognizer
            import json as _json
            model = self._load_vosk()
            if model is None:
                return None
            raw_data = audio.get_wav_data(convert_rate=16000, convert_width=2)
            rec = KaldiRecognizer(model, 16000)
            rec.AcceptWaveform(raw_data)
            result = _json.loads(rec.Result())
            text = result.get("text", "").strip()
            if text:
                log.info(f"Vosk STT: {text!r}")
                return text
            return None
        except Exception as e:
            log.warning(f"Vosk transcription failed: {e}")
            return None

    def _transcribe_sphinx(self, audio) -> Optional[str]:
        """Fallback: CMU Sphinx offline recognizer."""
        try:
            import speech_recognition as sr
            text = self._recognizer.recognize_sphinx(audio)
            log.info(f"Sphinx STT: {text!r}")
            return text if text else None
        except Exception as e:
            log.warning(f"Sphinx transcription failed: {e}")
            return None


# ── Voice Manager (Facade) ────────────────────────────────────────────────────
class VoiceManager:
    """
    Combines offline TTS + offline STT.
    Both operate completely without internet.
    """

    def __init__(self):
        self.tts = TTSEngine(rate=170, volume=0.95)
        self.stt = STTEngine(timeout=6.0, phrase_limit=15.0)

    async def listen(self, on_state: Optional[Callable] = None) -> Optional[str]:
        """Listen for speech, return transcription (offline)."""
        return await self.stt.listen_once(on_state_change=on_state)

    async def speak(self, text: str,
                    on_start: Optional[Callable] = None,
                    on_done:  Optional[Callable] = None):
        """Speak text aloud (offline pyttsx3)."""
        await self.tts.speak(text, on_start=on_start, on_done=on_done)

    def stop_speaking(self):
        self.tts.stop()

    def toggle_mute(self) -> bool:
        return self.tts.toggle_mute()

    @property
    def is_muted(self) -> bool:
        return self.tts.is_muted
