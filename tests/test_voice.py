import io
import os
import wave
from unittest.mock import MagicMock, patch

import httpx
import pytest

from jarvis.server.app import app
from jarvis.voice.nim_speech import (
    NIMSpeechClient,
    clean_text_for_speech,
    resolve_butler_voice,
)


class TestCleanTextForSpeech:
    def test_strips_thinking_tags(self):
        text = "Hello Sir.\n<think>\ninternal\n</think>\nGood day."
        assert clean_text_for_speech(text) == "Hello Sir. Good day."

    def test_strips_markdown(self):
        text = "**Bold** and `code` and # heading"
        cleaned = clean_text_for_speech(text)
        assert "**" not in cleaned
        assert "`" not in cleaned
        assert "Bold" in cleaned

    def test_strips_tokenizer_sensitive_chars(self):
        text = "See [broken markup and {json: value} plus |pipes|"
        cleaned = clean_text_for_speech(text)
        assert "[" not in cleaned
        assert "{" not in cleaned
        assert "|" not in cleaned
        assert "broken markup" in cleaned


class TestResolveButlerVoice:
    def test_prefers_male_calm_voice(self):
        available = {
            "Magpie-Multilingual.EN-US.Sofia",
            "Magpie-Multilingual.EN-US.Jason.Calm",
            "Magpie-Multilingual.EN-US.Aria",
        }
        voice = resolve_butler_voice(available_voices=available)
        assert voice == "Magpie-Multilingual.EN-US.Jason.Calm"

    def test_excludes_female_when_not_explicit(self):
        available = {
            "Magpie-Multilingual.EN-US.Sofia",
            "Magpie-Multilingual.EN-US.Aria",
            "Magpie-Multilingual.EN-US.Leo",
        }
        voice = resolve_butler_voice(available_voices=available)
        assert "Sofia" not in voice
        assert "Aria" not in voice
        assert voice == "Magpie-Multilingual.EN-US.Leo"

    def test_allows_explicit_female_override(self):
        voice = resolve_butler_voice(
            available_voices={"Magpie-Multilingual.EN-US.Sofia"},
            explicit_voice="Magpie-Multilingual.EN-US.Sofia",
        )
        assert voice == "Magpie-Multilingual.EN-US.Sofia"

    def test_fallback_chain_without_catalog(self):
        voice = resolve_butler_voice(available_voices=set())
        assert any(speaker in voice for speaker in ("Ray", "Jason", "Leo", "John Van Stan"))


@pytest.fixture(autouse=True)
def mock_env_and_db(tmp_path):
    test_db = tmp_path / "test_jarvis.db"
    with patch.dict(os.environ, {
        "JARVIS_DB_PATH": str(test_db),
        "NVIDIA_API_KEY": "test-key",
    }):
        yield


@pytest.mark.anyio
async def test_voice_status_without_client():
    mock_client = MagicMock()
    mock_client.tts_available = False
    mock_client.stt_available = False
    mock_client.init_error = "NVIDIA_API_KEY is not configured"
    mock_client.ensure_voice.side_effect = RuntimeError("unavailable")

    with patch("jarvis.server.app.get_speech_client", return_value=mock_client):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/v1/voice/status")
            assert response.status_code == 200
            data = response.json()
            assert data["tts_available"] is False
            assert data["stt_available"] is False


@pytest.mark.anyio
async def test_voice_mode_toggle_persistence():
    mock_client = MagicMock()
    mock_client.is_available = True
    mock_client.tts_available = True
    mock_client.stt_available = True
    mock_client.init_error = None
    mock_client.ensure_voice.return_value = "Magpie-Multilingual.EN-US.Jason.Calm"
    mock_client.voice_gender.return_value = "male"
    mock_client.persona_mismatch_warning.return_value = None

    with patch("jarvis.server.app.get_speech_client", return_value=mock_client):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            enable_res = await client.post("/v1/voice/mode", json={"enabled": True})
            assert enable_res.status_code == 200
            assert enable_res.json()["enabled"] is True

            status_res = await client.get("/v1/voice/status")
            assert status_res.status_code == 200
            assert status_res.json()["enabled"] is True

            disable_res = await client.post("/v1/voice/mode", json={"enabled": False})
            assert disable_res.status_code == 200
            assert disable_res.json()["enabled"] is False


@pytest.mark.anyio
async def test_voice_tts_endpoint():
    pcm = b"\x00\x00" * 100
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(pcm)
    wav_bytes = buffer.getvalue()

    mock_client = MagicMock()
    mock_client.tts_available = True
    mock_client.stt_available = True
    mock_client.init_error = None
    mock_client.synthesize.return_value = wav_bytes

    with patch("jarvis.server.app.get_speech_client", return_value=mock_client):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/v1/voice/tts", json={"text": "Good evening, Sir."})
            assert response.status_code == 200
            assert response.headers["content-type"] == "audio/wav"
            assert response.content.startswith(b"RIFF")


@pytest.mark.anyio
async def test_voice_stt_endpoint():
    mock_client = MagicMock()
    mock_client.tts_available = True
    mock_client.stt_available = True
    mock_client.init_error = None
    mock_client.transcribe.return_value = {
        "text": "Good evening, Sir.",
        "error": None,
        "duration_s": 2.5,
        "rms": 500.0,
    }

    with patch("jarvis.server.app.get_speech_client", return_value=mock_client):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            files = {"audio": ("recording.webm", b"fake-audio", "audio/webm")}
            response = await client.post("/v1/voice/stt", files=files)
            assert response.status_code == 200
            assert response.json()["text"] == "Good evening, Sir."


@pytest.mark.anyio
async def test_voice_tts_unavailable_returns_503():
    mock_client = MagicMock()
    mock_client.tts_available = False
    mock_client.init_error = "missing key"

    with patch("jarvis.server.app.get_speech_client", return_value=mock_client):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/v1/voice/tts", json={"text": "Hello"})
            assert response.status_code == 503


def test_nim_speech_client_missing_api_key():
    with patch.dict(os.environ, {"NVIDIA_API_KEY": ""}, clear=False):
        client = NIMSpeechClient(api_key="")
        assert client.is_available is False
        assert client.init_error == "NVIDIA_API_KEY is not configured"
