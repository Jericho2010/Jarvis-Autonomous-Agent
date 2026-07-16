from jarvis.config.nvidia import (
    format_nvidia_speech_error,
    nvidia_api_key_problem,
)


class TestNvidiaApiKeyProblem:
    def test_missing_key(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        assert nvidia_api_key_problem("") is not None
        assert nvidia_api_key_problem(None) is not None

    def test_placeholder_key(self):
        msg = nvidia_api_key_problem("nvapi-your-key-here")
        assert msg is not None
        assert "placeholder" in msg.lower()

    def test_valid_looking_key(self):
        assert nvidia_api_key_problem("nvapi-" + "a" * 40) is None


class TestFormatNvidiaSpeechError:
    def test_permission_denied_with_placeholder(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-your-key-here")
        msg = format_nvidia_speech_error(
            Exception("<StatusCode.PERMISSION_DENIED: 7>: Authorization failed")
        )
        assert "placeholder" in msg.lower() or "NVIDIA_API_KEY" in msg

    def test_truncates_long_messages(self):
        long_msg = "x" * 500
        assert len(format_nvidia_speech_error(Exception(long_msg))) <= 401
