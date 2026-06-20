#!/usr/bin/env python3
"""Cloud voice smoke test for J.A.R.V.I.S.

Runs layered PASS/FAIL checks for NVIDIA secrets, speech deps, and live
/v1/voice/* endpoints. Does not claim success unless TTS returns real WAV bytes.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from typing import Callable, List, Tuple

DEFAULT_BASE_URL = os.environ.get("JARVIS_BASE_URL", "http://127.0.0.1:8008")
TTS_OUTPUT = os.environ.get("JARVIS_TTS_OUTPUT", "/tmp/jarvis_tts_smoke.wav")


def _result(label: str, ok: bool, detail: str = "") -> Tuple[bool, str]:
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line = f"{line} — {detail}"
    print(line)
    return ok, line


def _http_json(method: str, url: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, {}
            try:
                return resp.status, json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return resp.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload


def _http_bytes(method: str, url: str, body: dict) -> tuple[int, bytes]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status, resp.read()


def check_nvidia_api_key() -> bool:
    key = os.environ.get("NVIDIA_API_KEY", "")
    ok = bool(key) and key not in ("nvapi-your-key-here", "test-key")
    return _result(
        "NVIDIA_API_KEY present",
        ok,
        f"length={len(key)}, prefix={key[:6] + '...' if len(key) > 6 else 'empty'}",
    )[0]


def check_nim_llm_api() -> bool:
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        return _result("NIM LLM API reachable", False, "missing NVIDIA_API_KEY")[0]
    req = urllib.request.Request(
        "https://integrate.api.nvidia.com/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            ok = resp.status == 200
            return _result("NIM LLM API reachable", ok, f"HTTP {resp.status}")[0]
    except Exception as exc:
        return _result("NIM LLM API reachable", False, str(exc))[0]


def check_riva_client() -> bool:
    try:
        import riva.client  # noqa: F401

        return _result("riva.client importable", True)[0]
    except ImportError as exc:
        return _result("riva.client importable", False, str(exc))[0]


def check_ffmpeg() -> bool:
    path = shutil.which("ffmpeg")
    return _result("ffmpeg available", bool(path), path or "not found")[0]


def check_server_health(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            ok = resp.status == 200 and payload.get("service") == "jarvis"
            return _result("Jarvis server /health", ok, str(payload))[0]
    except Exception as exc:
        return _result("Jarvis server /health", False, str(exc))[0]


def check_voice_status(base_url: str) -> bool:
    status_code, payload = _http_json("GET", f"{base_url}/v1/voice/status")
    if status_code != 200 or not isinstance(payload, dict):
        return _result("Voice status endpoint", False, f"HTTP {status_code} {payload}")[0]

    tts_ok = bool(payload.get("tts_available"))
    stt_ok = bool(payload.get("stt_available"))
    error = payload.get("error")
    ok = tts_ok and stt_ok and not error
    detail = (
        f"tts={payload.get('tts_available')}, stt={payload.get('stt_available')}, "
        f"error={error!r}, voice={payload.get('voice')!r}"
    )
    return _result("Voice status endpoint", ok, detail)[0]


def check_voice_mode_enable(base_url: str) -> bool:
    status_code, payload = _http_json(
        "POST",
        f"{base_url}/v1/voice/mode",
        {"enabled": True},
    )
    ok = status_code == 200 and isinstance(payload, dict) and payload.get("enabled") is True
    return _result("Enable voice mode", ok, f"HTTP {status_code} {payload}")[0]


def check_voice_tts(base_url: str) -> bool:
    try:
        status_code, wav_bytes = _http_bytes(
            "POST",
            f"{base_url}/v1/voice/tts",
            {"text": "Good evening, Sir."},
        )
    except Exception as exc:
        return _result("Live TTS synthesis", False, str(exc))[0]

    ok = status_code == 200 and len(wav_bytes) > 44 and wav_bytes[:4] == b"RIFF"
    detail = f"HTTP {status_code}, bytes={len(wav_bytes)}"
    if ok:
        with open(TTS_OUTPUT, "wb") as handle:
            handle.write(wav_bytes)
        detail = f"{detail}, saved={TTS_OUTPUT}"
    return _result("Live TTS synthesis", ok, detail)[0]


def main() -> int:
    base_url = DEFAULT_BASE_URL.rstrip("/")
    print(f"JARVIS cloud voice smoke test — base URL: {base_url}\n")

    checks: List[Callable[[], bool]] = [
        check_nvidia_api_key,
        check_nim_llm_api,
        check_riva_client,
        check_ffmpeg,
        lambda: check_server_health(base_url),
        lambda: check_voice_status(base_url),
        lambda: check_voice_mode_enable(base_url),
        lambda: check_voice_tts(base_url),
    ]

    results = [check() for check in checks]
    passed = sum(results)
    total = len(results)
    print(f"\nSummary: {passed}/{total} checks passed")

    if passed == total:
        print("Voice backend verified — live NIM gRPC TTS returned WAV audio.")
        return 0

    print("Voice backend NOT fully verified — see FAIL lines above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
