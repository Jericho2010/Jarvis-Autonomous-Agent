# Web HUD

The Jarvis Web HUD is a React + TypeScript + Vite application in `web/`. Production assets build to `web/dist/` and are served by the FastAPI backend at **http://127.0.0.1:8008**.

## Build

`run.sh` rebuilds the Web HUD automatically. Manual build:

```bash
cd web
npm install
npm run build
```

Development with hot reload (API still on :8008):

```bash
cd web
npm run dev    # Vite dev server on :5173, probes Jarvis API
```

## Interface tabs

| Tab | Component | Purpose |
|-----|-----------|---------|
| **CHAT** | `ChatStream.tsx` | Message stream, file attachments, voice controls |
| **GRAPH** | `FlowHUD.tsx` | Agent handoff graph via `@xyflow/react` |
| **RETINAL** | `RetinalHUD.tsx` | Live screenshot display from `/v1/captures/` |
| **LOG** | `ConsoleHUD.tsx` | Terminal-style event log via `xterm.js` |

Additional UI:

- **ReactorHUD** — system status and model indicator
- **SubagentsRoster** — active agent switcher and subagent inspection

## Session management

- Sidebar lists sessions from `GET /v1/sessions`
- **+** creates a new session (optionally finalizes the previous)
- Session titles auto-generate from the first message
- Agent switcher calls `POST /v1/sessions/{id}/switch-agent`

## Real-time sync

The HUD connects to `GET /v1/sessions/{id}/stream?client_id=web` and handles SSE events documented in [API.md](API.md).

When the TUI submits a prompt, the Web HUD receives a `user_message` event and displays it without re-submitting.

Port discovery: if the API is not on the page origin, the client scans ports 8008–8015 via `GET /health`. Override with `?port=8009` in the URL.

## File attachments

Paperclip upload widget → `POST /v1/sessions/{id}/files`. Attached files appear as chips in the chat input and are included in chat payloads.

## Friday approval modal

When Friday kinetic tools require approval, SSE `approval_required` triggers a modal with tool name and arguments. Approve/deny posts to `POST /v1/sessions/{id}/approve`.

## Voice mode

Implemented in `web/src/hooks/useVoiceMode.ts`:

- Toggle via voice button in the chat header
- **TTS:** assistant replies synthesized via `POST /v1/voice/tts`, played in browser
- **STT:** push-to-talk records microphone audio, resamples to 16 kHz PCM, posts to `POST /v1/voice/stt`
- Voice preference stored server-side (`voice_mode_enabled` in SQLite preferences)
- Mic device selection persisted in `localStorage` (`jarvis.voice.inputDeviceId`)

Voice requires `NVIDIA_API_KEY` and `nvidia-riva-client`. See [CONFIGURATION.md](CONFIGURATION.md).

## Captures

Screenshots from Friday (`scrot`) or Playwright MCP land in `webvision/`. The Retinal HUD resolves URLs via `web/src/lib/captures.ts` and displays them when `capture_ready` SSE events arrive.

## Tech stack

| Layer | Technology |
|-------|------------|
| Framework | React 19, TypeScript |
| Build | Vite |
| Styling | Tailwind CSS v4 |
| Graph | `@xyflow/react` |
| Terminal | `xterm.js` |
| Icons | `lucide-react` |

## Source layout

```
web/src/
├── App.tsx                 # Main layout, SSE handler, tab routing
├── lib/
│   ├── api.ts              # REST + SSE client
│   ├── captures.ts         # Capture URL resolution
│   └── graphEvents.ts      # Handoff graph event mapping
├── components/
│   ├── ChatStream.tsx
│   ├── ConsoleHUD.tsx
│   ├── FlowHUD.tsx
│   ├── RetinalHUD.tsx
│   ├── ReactorHUD.tsx
│   └── SubagentsRoster.tsx
└── hooks/
    └── useVoiceMode.ts
```
