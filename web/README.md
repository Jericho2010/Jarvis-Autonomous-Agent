# Jarvis Web HUD

React + TypeScript + Vite frontend for the Jarvis cognitive interface. Production assets build to `web/dist/` and are served by the FastAPI backend at **http://127.0.0.1:8008**.

Full documentation: [docs/WEB_HUD.md](../docs/WEB_HUD.md)

## Quick commands

```bash
cd web
npm install
npm run build    # production → web/dist/ (run automatically by ../run.sh)
npm run dev      # Vite dev server on :5173, probes API on :8008
```

## Tabs

| Tab | Purpose |
|-----|---------|
| CHAT | Message stream, file attachments, voice controls |
| GRAPH | Agent handoff visualization (`@xyflow/react`) |
| RETINAL | Live screenshots from `/v1/captures/` |
| LOG | Terminal-style event log (`xterm.js`) |

## Tech stack

React 19, TypeScript, Vite, Tailwind CSS v4, `@xyflow/react`, `xterm.js`, `lucide-react`
