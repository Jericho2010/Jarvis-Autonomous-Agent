import os
import re
from typing import Iterable, List, Optional, Sequence

import httpx

_PLACEHOLDER_PATTERNS = (
    re.compile(r"^nvapi-your-key-here$", re.I),
    re.compile(r"^your-.*-here$", re.I),
    re.compile(r"^changeme$", re.I),
    re.compile(r"^xxx+$", re.I),
    re.compile(r"^replace[-_]?me$", re.I),
)

NIM_API_BASE_URL = "https://integrate.api.nvidia.com/v1"


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


async def fetch_nim_model_ids(
    api_key: Optional[str] = None,
    *,
    base_url: str = NIM_API_BASE_URL,
    timeout: float = 10.0,
) -> List[str]:
    """Return model IDs from NIM GET /v1/models. Empty list if probe fails."""
    key = (api_key if api_key is not None else get_nvidia_api_key()).strip()
    if nvidia_api_key_problem(key):
        return []
    url = f"{base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {key}"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []

    data = payload.get("data", payload if isinstance(payload, list) else [])
    ids: List[str] = []
    for item in data:
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
        elif isinstance(item, str):
            ids.append(item)
    return ids


async def missing_basket_model_ids(
    basket: Sequence[str],
    api_key: Optional[str] = None,
    *,
    base_url: str = NIM_API_BASE_URL,
) -> List[str]:
    """Return basket entries absent from the live NIM catalog."""
    live = set(await fetch_nim_model_ids(api_key, base_url=base_url))
    if not live:
        return []
    return [model for model in basket if model not in live]


def format_missing_basket_warning(missing: Iterable[str]) -> str:
    models = ", ".join(missing)
    return (
        f"NIM basket IDs missing from integrate.api.nvidia.com/v1/models: {models}. "
        "Update NIM_MODEL_BASKET before these rotate to 410 Gone."
    )
