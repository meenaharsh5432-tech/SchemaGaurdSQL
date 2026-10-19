# SchemaGuard SQL frontend

A React and TypeScript query studio for the existing FastAPI backend. Backend features and SQL guardrails are unchanged.

## Run locally

Start the backend from the repository root (with the existing database, Redis, Ollama and environment configuration):

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api/*` to the backend at `http://127.0.0.1:8000`, stripping `/api`. No backend CORS changes are needed.

## Features

- Run questions through `POST /query`, or generate validated SQL without execution through `POST /generate-sql`.
- Live API and database readiness checks through `/health` and `/ready`.
- Results with filtering, pagination, CSV export and backend explanations.
- SQL inspection and clipboard copy; execution, cache, repair, timing and audit metadata.
- Session history held only in browser memory (cleared on refresh).
- Responsive layout, keyboard focus styles, status announcements, and Ctrl/Cmd+Enter submission.

## Verify and deploy

```powershell
npm run build
npm run lint
npm run preview
```

The build is in `dist`. Preview uses the same API proxy. For production, serve `dist` with an HTTP server and reverse-proxy `/api/*` to FastAPI, stripping the `/api` prefix and preserving response headers. Allow sufficient proxy time for local model generation and repair attempts. Do not expose backend secrets in frontend configuration. Google Fonts are optional; the interface uses system sans-serif fallbacks when unavailable.
