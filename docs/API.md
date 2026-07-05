# API Reference

The Jarvis backend is a FastAPI server (`src/jarvis/server/app.py`) that exposes REST endpoints and Server-Sent Events (SSE). Default port is **8008** (auto-increments if occupied).

Production Web HUD static assets are served from `web/dist` at `/`.

## Health

### `GET /health`

```json
{"status": "healthy", "service": "jarvis"}
```

## Sessions

### `GET /v1/sessions`

List sessions with messages. Empty sessions older than one hour are purged.

**Response:** array of:

```json
{
  "session_id": "session_123456_7890",
  "started_at": 1717654321.0,
  "model": "house-party",
  "title": "Session title or id",
  "agent_id": "jarvis"
}
```

### `POST /v1/sessions`

Create a new session. Optionally finalize the previous session's memory.

**Request body:**

```json
{
  "finalize_session_id": "session_previous_id"
}
```

**Response:**

```json
{"session_id": "session_123456_7890"}
```

### `GET /v1/sessions/{session_id}`

Session detail: `session_id`, `model`, `started_at`, `title`, `agent_id`.

### `GET /v1/sessions/{session_id}/history`

Message history for the session. Assistant messages may include a separate `reasoning` field parsed from thinking blocks.

**Response:** array of:

```json
{
  "role": "user",
  "content": "Hello",
  "reasoning": "",
  "timestamp": 1717654321000
}
```

### `POST /v1/sessions/{session_id}/finalize`

Trigger background session memory extraction (summary + durable facts). Returns immediately.

### `POST /v1/sessions/{session_id}/chat`

Submit a user prompt. Runs the agent turn in the background; results stream via SSE.

**Request body:**

```json
{
  "message": "User prompt text",
  "client_id": "web",
  "files": [{"id": "file_abc", "filename": "doc.txt", "bytes": 1024}]
}
```

**Response:**

```json
{"status": "submitted"}
```

### `GET /v1/sessions/{session_id}/stream`

SSE stream for real-time updates.

**Query params:**

| Param | Description |
|-------|-------------|
| `client_id` | `tui` or `web` — used to exclude echo on reciprocal mirroring |

**SSE events:** see [SSE events](#sse-events) below. Connection sends `connection_confirmed` on connect and `ping` every 10 seconds.

### `POST /v1/sessions/{session_id}/switch-agent`

**Request body:**

```json
{"agent_id": "homer"}
```

Valid values: `jarvis`, `homer`, `friday`, `plato`.

### `POST /v1/sessions/{session_id}/approve`

Approve or deny a Friday kinetic tool action.

**Request body:**

```json
{
  "request_id": "approval-uuid",
  "approved": true
}
```

## Files

### `POST /v1/sessions/{session_id}/files`

Multipart upload. Stores under `data/sessions/{session_id}/files/{file_id}/{filename}`.

**Response:**

```json
{"id": "file_abc123", "filename": "doc.txt", "bytes": 1024}
```

### `GET /v1/sessions/{session_id}/files/{file_id}/content`

Download uploaded file content.

## Captures

### `GET /v1/captures/{filename}`

Serve a screenshot from the `webvision/` directory (Friday HUD or Playwright captures). Filename must not contain path separators.

## Models

### `GET /v1/models`

```json
{
  "models": [
    "house-party",
    "deepseek-ai/deepseek-v4-pro",
    "deepseek-ai/deepseek-v4-flash",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "moonshotai/kimi-k2.6",
    "stepfun-ai/step-3.7-flash"
  ]
}
```

### `POST /v1/sessions/{session_id}/model`

**Request body:**

```json
{"model": "house-party"}
```

## Subagents

### `GET /v1/subagents/{name}`

Load subagent profile. Valid names: `homer`, `friday`, `plato`.

**Response:**

```json
{
  "name": "HOMER",
  "model": "house-party",
  "instructions": "...",
  "tools": [{"name": "web_search", "description": "..."}],
  "meta": {
    "role": "...",
    "version": "1.0",
    "output_contract": "...",
    "owns": [],
    "forbidden": []
  }
}
```

## Voice

### `GET /v1/voice/status`

```json
{
  "enabled": false,
  "voice": "Magpie-Multilingual.EN-US.Ray.Calm",
  "language": "en-US",
  "gender": "male",
  "persona_warning": null,
  "tts_available": true,
  "stt_available": true,
  "error": null
}
```

### `POST /v1/voice/mode`

**Request body:**

```json
{"enabled": true}
```

Returns `503` if speech services are unavailable when enabling.

### `POST /v1/voice/tts`

**Request body:**

```json
{"text": "Good evening, Sir."}
```

**Response:** `audio/wav` blob.

### `POST /v1/voice/stt`

Multipart form with `audio` field (WAV, WebM, or OGG).

**Response:**

```json
{
  "text": "transcribed speech",
  "error": null,
  "duration_s": 2.5,
  "rms": 1234.5
}
```

## SSE events

Clients subscribe via `GET /v1/sessions/{id}/stream?client_id=...`. Event payloads are JSON in the `data` field.

| Event | Payload (typical) | Description |
|-------|-------------------|-------------|
| `connection_confirmed` | `{}` | Stream connected |
| `ping` | `{}` | Keepalive |
| `user_message` | `{text, timestamp}` | Remote client prompt (mirrored) |
| `text_chunk` | `{text}` | Assistant text delta |
| `reasoning_chunk` | `{text}` | Reasoning/thinking delta |
| `tool_call_start` | `{name, arguments}` | Tool invocation started |
| `tool_call_complete` | `{name, result}` | Tool finished |
| `capture_ready` | `{url, filename}` | Screenshot available |
| `handoff_initiated` | `{target}` | Agent handoff started |
| `handoff` | `{source, target, ...}` | Handoff workflow event |
| `agent_changed` | `{agent_id}` | Active agent switched |
| `title_changed` | `{title}` | Session title updated |
| `approval_required` | `{request_id, function_name, arguments}` | Friday kinetic approval needed |
| `approval_resolved` | `{request_id, approved}` | Approval submitted |
| `subagent_text_chunk` | `{subagent, text}` | Subagent streaming text |
| `voice_ready` | `{...}` | Voice synthesis ready |
| `turn_complete` | `{session_id}` | Agent turn finished |

## Reciprocal mirroring

Multiple clients (TUI + Web HUD) can attach to the same session:

1. Each client registers with `client_id` (`tui` or `web`) on stream and chat requests.
2. On chat submit, the server broadcasts `user_message` to all SSE subscribers **except** the sender.
3. The receiving client displays the remote prompt without re-submitting it.

This prevents prompt echo loops while keeping both interfaces in sync.

## Client reference

The Web HUD client implementation is in `web/src/lib/api.ts`.
