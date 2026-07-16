import os
import re
from typing import Optional

_PLACEHOLDER_PATTERNS = (
    re.compile(r"^nvapi-your-key-here$", re.I),
    re.compile(r"^your-.*-here$", re.I),
    re.compile(r"^changeme$", re.I),
    re.compile(r"^xxx+$", re.I),
    re.compile(r"^replace[-_]?me", re.I),
)


def get_nvidia_api_key() -> str:
    return os.environ.get("NVIDIA_API_KEY", "").strip()


def nvidia_api_key_problem(key: Optional[str] = None) -> Optional[str]:
    """Return a user-facing message when the API key is missing or invalid-looking."""
    value = (key if key is not None else get_nvidia_api_key()).strip()
    if not value:
        return "NVIDIA_API_KEY is not set. Add your key to .env in the repo root."
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.match(value):
            return (
                "NVIDIA_API_KEY is still the placeholder from .env.example. "
                "Replace it with a real key from https://build.nvidia.com/"
            )
    if len(value) < 20:
        return "NVIDIA_API_KEY looks too short to be valid."
    return None


def format_nvidia_speech_error(exc: Exception) -> str:
    """Turn gRPC failures into actionable messages for voice endpoints."""
    message = str(exc)
    upper = message.upper()
    if "PERMISSION_DENIED" in upper or "AUTHORIZATION FAILED" in upper:
        problem = nvidia_api_key_problem()
        if problem:
            return problem
        return "NVIDIA API key was rejected. Check NVIDIA_API_KEY in .env."
    if "UNAUTHENTICATED" in upper:
        return nvidia_api_key_problem() or "NVIDIA API authentication failed."
    if len(message) > 400:
        return message[:400] + "…"
    return message
