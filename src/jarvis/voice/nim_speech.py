import io
import logging
import os
import re
import subprocess
import tempfile
import wave
from typing import List, Optional, Set

from jarvis.config.voice import (
    ASR_SAMPLE_RATE_HZ,
    BUTLER_LANGUAGE,
    BUTLER_VOICE,
    BUTLER_VOICE_FALLBACKS,
    FEMALE_SPEAKERS,
    MAX_TTS_CHARS,
    MALE_SPEAKERS,
    NIM_ASR_FUNCTION_ID,
    NIM_SPEECH_GRPC_URI,
    NIM_TTS_FUNCTION_ID,
    TTS_SAMPLE_RATE_HZ,
)

logger = logging.getLogger("jarvis.voice")

_speech_client: Optional["NIMSpeechClient"] = None
_resolved_voice: Optional[str] = None


def clean_text_for_speech(text: str) -> str:
    """Strip thinking blocks, markdown, and Rich markup before TTS."""
    if not text:
        return ""

    cleaned = text
    cleaned = re.sub(
        r"<think>.*?</think>",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(r"\[/?(?:bold|dim|italic|underline|strike)[^\]]*\]", "", cleaned)
    cleaned = re.sub(r"\[/?[^\]]+\]", "", cleaned)
    cleaned = re.sub(r"```[\s\S]*?```", " code block omitted. ", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"#{1,6}\s+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) > MAX_TTS_CHARS:
        cleaned = cleaned[: MAX_TTS_CHARS - 1].rstrip() + "…"
    return cleaned


def _speaker_from_voice(voice: str) -> str:
    parts = voice.split(".")
    if len(parts) >= 3:
        return parts[2]
    return ""


def _is_male_voice(voice: str) -> bool:
    return _speaker_from_voice(voice) in MALE_SPEAKERS


def _is_female_voice(voice: str) -> bool:
    return _speaker_from_voice(voice) in FEMALE_SPEAKERS


def resolve_butler_voice(
    available_voices: Optional[Set[str]] = None,
    explicit_voice: Optional[str] = None,
) -> str:
    """Pick a male butler voice, preferring Calm emotion when available."""
    global _resolved_voice
    if _resolved_voice and not explicit_voice and available_voices is None:
        return _resolved_voice

    voice_override = explicit_voice or os.environ.get("JARVIS_BUTLER_VOICE") or BUTLER_VOICE
    candidates: List[str] = []
    if voice_override:
        candidates.append(voice_override)
    for fallback in BUTLER_VOICE_FALLBACKS:
        if fallback not in candidates:
            candidates.append(fallback)

    if available_voices is None:
        chosen = candidates[0]
        if _is_female_voice(chosen) and not explicit_voice:
            for candidate in candidates:
                if _is_male_voice(candidate):
                    chosen = candidate
                    break
        _resolved_voice = chosen
        return chosen

    available = set(available_voices)
    for candidate in candidates:
        if candidate not in available:
            continue
        if _is_female_voice(candidate) and not explicit_voice:
            continue
        _resolved_voice = candidate
        return candidate

    male_available = sorted(
        v for v in available if _is_male_voice(v) and BUTLER_LANGUAGE.lower() in v.lower()
    )
    calm_male = [v for v in male_available if v.endswith(".Calm")]
    if calm_male:
        _resolved_voice = calm_male[0]
        return calm_male[0]
    if male_available:
        _resolved_voice = male_available[0]
        return male_available[0]

    chosen = candidates[0]
    _resolved_voice = chosen
    return chosen


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


def convert_audio_to_wav(audio_bytes: bytes, mime: Optional[str] = None) -> bytes:
    mime = (mime or "").lower()
    if mime in ("audio/wav", "audio/x-wav", "audio/wave", "audio/wav; codecs=1"):
        return audio_bytes

    suffix = ".webm"
    if "ogg" in mime:
        suffix = ".ogg"
    elif "opus" in mime:
        suffix = ".opus"
    elif "mp4" in mime or "m4a" in mime:
        suffix = ".m4a"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as inp:
        inp.write(audio_bytes)
        inp_path = inp.name

    out_path = inp_path + ".wav"
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                inp_path,
                "-ar",
                str(ASR_SAMPLE_RATE_HZ),
                "-ac",
                "1",
                "-f",
                "wav",
                out_path,
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Audio conversion failed: {stderr[:500]}")
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for path in (inp_path, out_path):
            try:
                os.unlink(path)
            except OSError:
                pass


class NIMSpeechClient:
    """NVIDIA NIM hosted speech client (Magpie TTS + Nemotron ASR via Riva gRPC)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY", "")
        self._tts_service = None
        self._asr_service = None
        self._available_voices: Optional[Set[str]] = None
        self.resolved_voice: Optional[str] = None
        self._init_error: Optional[str] = None

        if not self.api_key:
            self._init_error = "NVIDIA_API_KEY is not configured"
            return

        try:
            import riva.client
            from riva.client.proto.riva_audio_pb2 import AudioEncoding

            self._riva = riva.client
            self._AudioEncoding = AudioEncoding
            tts_auth = riva.client.Auth(
                uri=NIM_SPEECH_GRPC_URI,
                use_ssl=True,
                metadata_args=[
                    ["function-id", NIM_TTS_FUNCTION_ID],
                    ["authorization", f"Bearer {self.api_key}"],
                ],
            )
            asr_auth = riva.client.Auth(
                uri=NIM_SPEECH_GRPC_URI,
                use_ssl=True,
                metadata_args=[
                    ["function-id", NIM_ASR_FUNCTION_ID],
                    ["authorization", f"Bearer {self.api_key}"],
                ],
            )
            self._tts_service = riva.client.SpeechSynthesisService(tts_auth)
            self._asr_service = riva.client.ASRService(asr_auth)
        except Exception as exc:
            self._init_error = str(exc)
            logger.warning("Failed to initialize NIM speech client: %s", exc)

    @property
    def is_available(self) -> bool:
        return self._tts_service is not None and self._asr_service is not None

    @property
    def tts_available(self) -> bool:
        return self._tts_service is not None

    @property
    def stt_available(self) -> bool:
        return self._asr_service is not None

    @property
    def init_error(self) -> Optional[str]:
        return self._init_error

    def list_voices(self) -> List[str]:
        if not self._tts_service:
            return []
        if self._available_voices is not None:
            return sorted(self._available_voices)

        try:
            config_response = self._tts_service.stub.GetRivaSynthesisConfig(
                self._riva.client.proto.riva_tts_pb2.RivaSynthesisConfigRequest()
            )
            voices = set()
            for model_config in config_response.model_config:
                for voice in model_config.voices:
                    voices.add(voice)
            self._available_voices = voices
            return sorted(voices)
        except Exception as exc:
            logger.warning("Could not list TTS voices: %s", exc)
            self._available_voices = set()
            return []

    def ensure_voice(self) -> str:
        if self.resolved_voice:
            return self.resolved_voice
        available = set(self.list_voices()) if self._tts_service else set()
        self.resolved_voice = resolve_butler_voice(
            available_voices=available or None,
        )
        if available and self.resolved_voice not in available:
            self.resolved_voice = resolve_butler_voice(available_voices=available)
        logger.info("Resolved butler voice: %s", self.resolved_voice)
        return self.resolved_voice

    def synthesize(self, text: str) -> bytes:
        if not self._tts_service:
            raise RuntimeError(self._init_error or "TTS service unavailable")

        cleaned = clean_text_for_speech(text)
        if not cleaned:
            raise ValueError("No speakable text after cleaning")

        voice = self.ensure_voice()
        response = self._tts_service.synthesize(
            cleaned,
            voice,
            BUTLER_LANGUAGE,
            sample_rate_hz=TTS_SAMPLE_RATE_HZ,
            encoding=self._AudioEncoding.LINEAR_PCM,
        )
        if not response.audio:
            raise RuntimeError("TTS returned empty audio")
        return _pcm_to_wav(response.audio, TTS_SAMPLE_RATE_HZ)

    def transcribe(self, audio_bytes: bytes, mime: Optional[str] = None) -> str:
        if not self._asr_service:
            raise RuntimeError(self._init_error or "STT service unavailable")

        wav_bytes = convert_audio_to_wav(audio_bytes, mime)
        config = self._riva.client.RecognitionConfig(
            language_code="en-US",
            max_alternatives=1,
            enable_automatic_punctuation=True,
        )
        response = self._asr_service.offline_recognize(wav_bytes, config)
        if not response.results:
            return ""
        return response.results[0].alternatives[0].transcript.strip()

    def voice_gender(self) -> str:
        voice = self.ensure_voice()
        if _is_female_voice(voice):
            return "female"
        if _is_male_voice(voice):
            return "male"
        return "unknown"

    def persona_mismatch_warning(self) -> Optional[str]:
        voice = self.ensure_voice()
        if _is_female_voice(voice):
            return (
                "Configured voice is female; Edwin butler persona expects a male voice. "
                "Set JARVIS_BUTLER_VOICE to a male Magpie speaker."
            )
        return None


def get_speech_client() -> NIMSpeechClient:
    global _speech_client
    if _speech_client is None:
        _speech_client = NIMSpeechClient()
    return _speech_client
