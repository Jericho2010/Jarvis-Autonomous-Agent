#!/usr/bin/env python3
"""Live validation harness for Jarvis digital-hands handoffs."""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from http.client import HTTPConnection, HTTPResponse
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8008"
LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "server.log"
TURN_TIMEOUT = 180.0
IDLE_TIMEOUT = 45.0
READ_TIMEOUT = 5.0


@dataclass
class TurnResult:
    name: str
    session_id: str
    messages: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    response_text: str = ""
    error: str | None = None

    def handoff_targets(self) -> list[str]:
        targets: list[str] = []
        for e in self.events:
            t = e.get("type")
            data = e.get("data") or {}
            if t == "handoff_initiated":
                targets.append(str(data.get("target", "")).lower())
            elif t == "handoff":
                targets.append(str(data.get("agent", "")).lower())
        return [t for t in targets if t]

    def tool_starts(self) -> list[str]:
        return [
            str((e.get("data") or {}).get("name", ""))
            for e in self.events
            if e.get("type") == "tool_call_start"
        ]

    def tool_errors(self) -> list[str]:
        errors: list[str] = []
        for e in self.events:
            if e.get("type") != "tool_call_complete":
                continue
            err = (e.get("data") or {}).get("error")
            if err:
                errors.append(str(err))
        return errors


def log(msg: str) -> None:
    print(msg, flush=True)


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 30) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def create_session() -> str:
    out = _http_json("POST", f"{BASE}/v1/sessions", {})
    sid = out.get("session_id") or out.get("id")
    if not sid:
        raise RuntimeError(f"No session_id in response: {out}")
    return sid


def post_chat(session_id: str, message: str) -> None:
    # Do not set client_id here — server excludes that client from all SSE broadcasts.
    _http_json(
        "POST",
        f"{BASE}/v1/sessions/{session_id}/chat",
        {"message": message},
    )


def fetch_history(session_id: str) -> str:
    try:
        out = _http_json("GET", f"{BASE}/v1/sessions/{session_id}/history", timeout=15)
        msgs = out if isinstance(out, list) else out.get("messages", [])
        parts = []
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "assistant":
                parts.append(str(m.get("content") or ""))
        return "\n".join(parts).strip()
    except Exception as exc:
        log(f"  [warn] history fetch failed: {exc}")
        return ""


def collect_sse(session_id: str, stop: threading.Event, bucket: list[dict[str, Any]]) -> None:
    host = "127.0.0.1"
    port = 8008
    path = f"/v1/sessions/{session_id}/stream?client_id=validate_handoffs"
    conn = HTTPConnection(host, port, timeout=READ_TIMEOUT)
    try:
        conn.request("GET", path, headers={"Accept": "text/event-stream"})
        resp: HTTPResponse = conn.getresponse()
        if resp.status != 200:
            bucket.append({"type": "_sse_error", "data": {"error": f"HTTP {resp.status}"}})
            return
        sock = conn.sock
        if sock:
            sock.settimeout(READ_TIMEOUT)
        event_type = "message"
        data_lines: list[str] = []
        while not stop.is_set():
            try:
                raw = resp.readline()
            except socket.timeout:
                continue
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if line.startswith("event:"):
                event_type = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
            elif line == "" and data_lines:
                payload_raw = "\n".join(data_lines)
                data_lines = []
                try:
                    data = json.loads(payload_raw) if payload_raw else {}
                except json.JSONDecodeError:
                    data = {"raw": payload_raw}
                bucket.append({"type": event_type, "data": data, "ts": time.time()})
                log(f"  [sse] {event_type}")
                if event_type == "turn_complete":
                    stop.set()
                    break
    except Exception as exc:
        bucket.append({"type": "_sse_error", "data": {"error": str(exc)}})
    finally:
        conn.close()


def count_log_turn_completions(session_id: str) -> int:
    """Count completed turns for a session in server.log."""
    if not LOG_PATH.exists():
        return 0
    needle = f"Session {session_id} turn completed successfully"
    return LOG_PATH.read_text(encoding="utf-8", errors="replace").count(needle)


def turn_completion_recorded(session_id: str, baseline_count: int) -> bool:
    """True when server.log has a new turn completion since baseline_count."""
    return count_log_turn_completions(session_id) > baseline_count


def run_turn(name: str, message: str, session_id: str | None = None) -> TurnResult:
    sid = session_id or create_session()
    result = TurnResult(name=name, session_id=sid, messages=[message])
    log(f"\n>> {name}: session={sid}")
    log(f"   prompt: {message[:80]}...")
    completions_before = count_log_turn_completions(sid)
    log(f"   [log] completions before chat: {completions_before}")
    events: list[dict[str, Any]] = []
    stop = threading.Event()
    thread = threading.Thread(target=collect_sse, args=(sid, stop, events), daemon=True)
    thread.start()
    time.sleep(0.4)
    post_chat(sid, message)
    deadline = time.time() + TURN_TIMEOUT
    completed = False
    while time.time() < deadline and not stop.is_set():
        thread.join(timeout=3.0)
        if turn_completion_recorded(sid, completions_before):
            completed = True
            log(
                f"   [log] turn completed "
                f"(#{count_log_turn_completions(sid)} for session)"
            )
            time.sleep(1.0)
            break
        time.sleep(0.5)
    if not completed and count_log_turn_completions(sid) > completions_before:
        completed = True
        log(
            f"   [log] turn completed after loop "
            f"(#{count_log_turn_completions(sid)} for session)"
        )
    stop.set()
    thread.join(timeout=3.0)
    result.events = events
    chunks = [
        str((e.get("data") or {}).get("text", ""))
        for e in events
        if e.get("type") == "text_chunk"
    ]
    result.response_text = "".join(chunks).strip()
    if not result.response_text:
        result.response_text = fetch_history(sid)
    if not any(e.get("type") == "turn_complete" for e in events):
        if completed:
            result.error = "turn_complete SSE missed (log/history fallback used)"
        else:
            result.error = "timeout before turn completed"
    return result


def grep_log_tools(session_id: str) -> list[str]:
    if not LOG_PATH.exists():
        return []
    text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    tools: list[str] = []
    in_session = False
    for line in text.splitlines():
        if session_id in line:
            in_session = True
        elif in_session and line.startswith("2026-") and session_id not in line:
            in_session = False
        if in_session and "Function name:" in line:
            m = re.search(r"Function name: (\S+)", line)
            if m:
                tools.append(m.group(1))
    return tools


def grep_log_snippet(session_id: str, limit: int = 1200) -> str:
    if not LOG_PATH.exists():
        return ""
    lines = [ln for ln in LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines() if session_id in ln]
    return "\n".join(lines)[-limit:]


def score_homer(r: TurnResult) -> tuple[str, list[str]]:
    reasons: list[str] = []
    targets = r.handoff_targets()
    log_tools = grep_log_tools(r.session_id)
    has_handoff = any(t == "homer" for t in targets) or "handoff_to_homer" in " ".join(r.tool_starts())
    has_web = "web_search" in log_tools or "web_extract" in log_tools
    has_url = bool(re.search(r"https?://", r.response_text))
    middleware_fail = any("Middleware terminated" in e for e in r.tool_errors())
    if has_handoff or has_web:
        reasons.append("homer handoff or web tools in log")
    else:
        reasons.append("no homer activity")
    if has_web:
        reasons.append("web_search/web_extract executed")
    if has_url:
        reasons.append("response contains URL")
    if middleware_fail:
        reasons.append("Middleware terminated error in SSE")
    if (has_handoff or has_web) and has_web and not middleware_fail:
        return ("PASS" if has_url else "PARTIAL"), reasons
    return "FAIL", reasons


def score_friday(r: TurnResult) -> tuple[str, list[str]]:
    reasons: list[str] = []
    targets = r.handoff_targets()
    log_tools = grep_log_tools(r.session_id)
    has_handoff = any(t == "friday" for t in targets)
    has_hud = "stark_os_retinal_hud" in log_tools or "/v1/captures/" in r.response_text or "webvision/" in r.response_text
    env_block = any(k in r.response_text.lower() for k in ("x11", "scrot failed", "display", "wayland"))
    if has_handoff:
        reasons.append("friday handoff")
    if has_hud:
        reasons.append("retinal HUD captured")
    if env_block and not has_hud:
        reasons.append("environment may block capture")
    if has_handoff and has_hud:
        return "PASS", reasons
    if has_handoff and env_block:
        return "ENV_BLOCKED", reasons
    if has_hud:
        return "PARTIAL", reasons
    return "FAIL", reasons


def score_plato(r: TurnResult) -> tuple[str, list[str]]:
    reasons: list[str] = []
    targets = r.handoff_targets()
    log_tools = grep_log_tools(r.session_id)
    has_handoff = any(t == "plato" for t in targets)
    repo = [t for t in log_tools if "read" in t or "analyze" in t or "repo" in t]
    concrete = any(kw in r.response_text.lower() for kw in ("autonomous", "drain", "handoff", "terminate", "workflow"))
    if has_handoff:
        reasons.append("plato handoff")
    if repo:
        reasons.append(f"repo tools: {repo}")
    if concrete:
        reasons.append("concrete code reference in response")
    if has_handoff and (repo or concrete):
        return "PASS", reasons
    if concrete:
        return "PARTIAL", reasons
    return "FAIL", reasons


def score_youtube(r1: TurnResult, r2: TurnResult) -> tuple[str, list[str]]:
    reasons: list[str] = []
    t1 = r1.response_text.lower()
    turn1_ok = any(k in t1 for k in ("youtube", "firefox", "mozilla", "video", "watching"))
    log2 = grep_log_tools(r2.session_id)
    has_homer = any(t == "homer" for t in r2.handoff_targets()) or "web_search" in log2
    has_web = "web_search" in log2 or "web_extract" in log2
    bad = any(k in r2.response_text.lower() for k in ("jsonlz4", "lz4", "sessionstore", "pip install"))
    reasons.append("turn1 ok" if turn1_ok else "turn1 weak")
    reasons.append("turn2 homer/web" if has_web else "turn2 no web tools")
    if bad:
        reasons.append("turn2 bash detour")
    if turn1_ok and has_web and not bad:
        return "PASS", reasons
    if turn1_ok and has_homer:
        return "PARTIAL", reasons
    return "FAIL", reasons


def print_result(r: TurnResult, verdict: str, reasons: list[str]) -> None:
    log(f"\n{'='*60}")
    log(f"TEST: {r.name} -> {verdict}")
    log(f"Session: {r.session_id}")
    for reason in reasons:
        log(f"  - {reason}")
    log(f"Handoffs: {r.handoff_targets()} | Tools SSE: {r.tool_starts()} | Log tools: {grep_log_tools(r.session_id)}")
    if r.error:
        log(f"Harness: {r.error}")
    log(f"Response: {r.response_text[:400].replace(chr(10), ' ')}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", choices=["all", "homer", "friday", "plato", "youtube"], default="all")
    args = parser.parse_args()

    try:
        with urlopen(f"{BASE}/health", timeout=5) as resp:
            if resp.status != 200:
                return 1
    except URLError as exc:
        log(f"Server not reachable: {exc}")
        return 1

    results: dict[str, str] = {}

    if args.test in ("all", "homer"):
        r = run_turn("Homer", "Search the web for one current AI news headline and cite the source URL.")
        v, reasons = score_homer(r)
        print_result(r, v, reasons)
        results["homer"] = v

    if args.test in ("all", "friday"):
        r = run_turn("Friday", "Take a Retinal HUD screenshot of my desktop and tell me the capture path.")
        v, reasons = score_friday(r)
        print_result(r, v, reasons)
        results["friday"] = v

    if args.test in ("all", "plato"):
        r = run_turn("Plato", "Review src/jarvis/core/handoff_workflow.py for one fragility or risk. Be specific.")
        v, reasons = score_plato(r)
        print_result(r, v, reasons)
        results["plato"] = v

    if args.test in ("all", "youtube"):
        sid = create_session()
        r1 = run_turn(
            "YouTube-T1",
            "Tell me what video am I currently watching and on what app or website",
            sid,
        )
        # Turn 2 must wait for a *second* completion line, not reuse turn 1's.
        r2 = run_turn("YouTube-T2", "Summarise that video. It is comedy.", sid)
        v, reasons = score_youtube(r1, r2)
        print_result(r1, v + " (t1)", reasons[:1])
        print_result(r2, v + " (t2)", reasons[1:])
        results["youtube"] = v

    log(f"\n{'='*60}\nSUMMARY")
    for k, v in results.items():
        log(f"  {k}: {v}")
    return 1 if any(v == "FAIL" for v in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
