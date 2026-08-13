from jarvis.config.nvidia import (
    format_missing_basket_warning,
    format_nvidia_speech_error,
    missing_basket_model_ids,
    nvidia_api_key_problem,
)
from jarvis.core.agent import (
    FALLBACK_ATTEMPT_TIMEOUT_S,
    PRIMARY_ATTEMPT_TIMEOUT_S,
    _attempt_timeout,
    _is_hard_model_error,
    _ordered_failover_models,
)
import pytest


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

    def test_replace_me_requires_exact_match(self):
        assert nvidia_api_key_problem("replace-me") is not None
        assert nvidia_api_key_problem("nvapi-replaceme-but-real-looking-key") is None


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


class TestHardModelErrorDetection:
    def test_detects_eol_410(self):
        err = Exception(
            "Error code: 410 - detail: The model 'x' has reached its end of life "
            "and is no longer available."
        )
        assert _is_hard_model_error(err)

    def test_detects_404_not_found(self):
        assert _is_hard_model_error(Exception("Error code: 404 - model_not_found"))

    def test_ignores_timeout_and_rate_limit(self):
        assert not _is_hard_model_error(TimeoutError())
        assert not _is_hard_model_error(Exception("429 Too Many Requests"))


class TestFailoverOrderingAndTimeouts:
    def test_house_party_keeps_declared_order(self):
        basket = ["a", "b", "c"]
        assert _ordered_failover_models("house-party", basket) == basket

    def test_fallback_timeout_shorter_than_primary(self):
        assert _attempt_timeout(0) == PRIMARY_ATTEMPT_TIMEOUT_S
        assert _attempt_timeout(1) == FALLBACK_ATTEMPT_TIMEOUT_S
        assert FALLBACK_ATTEMPT_TIMEOUT_S < PRIMARY_ATTEMPT_TIMEOUT_S


@pytest.mark.anyio
async def test_missing_basket_model_ids(monkeypatch):
    async def fake_fetch(api_key=None, *, base_url=None, timeout=10.0):
        return ["z-ai/glm-5.2", "minimaxai/minimax-m3"]

    monkeypatch.setattr(
        "jarvis.config.nvidia.fetch_nim_model_ids",
        fake_fetch,
    )
    missing = await missing_basket_model_ids(
        ["z-ai/glm-5.2", "deepseek-ai/deepseek-v4-flash-0731"]
    )
    assert missing == ["deepseek-ai/deepseek-v4-flash-0731"]
    assert "deepseek" in format_missing_basket_warning(missing)
