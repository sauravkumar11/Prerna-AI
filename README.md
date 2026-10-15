# Prerna AI

Prerna is a Windows-focused AI desktop companion with a FastAPI backend, React frontend, and Electron shell.

## Current status

- **Version baseline:** Prerna Core **v1.2** (Event Bus foundation phase, active development)
- **Platform focus:** Windows 10/11 for full automation features
- **Linux/macOS:** useful for backend/frontend development and most unit tests, but not full desktop automation behavior

## Repository structure

```text
backend/
  agent/
  app/
  config/
  memory/
  tests/
  tools/
  voice/
frontend/react/
  electron/
  src/
docs/
  archive/
```

## Setup

### Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```dotenv
GEMINI_API_KEY=your_key_here
# Optional controlled failover only (off by default)
# ENABLE_GEMINI_KEY_FAILOVER=true
# GEMINI_API_KEY_2=your_failover_key_here
```

Run backend:

```bash
python main.py
```

### Frontend + Electron (development)

```bash
cd frontend/react
npm install
npm run start
```

This starts Vite (`http://localhost:5173`) and Electron in dev mode.

### Electron production-style local preview

```bash
cd frontend/react
npm install
npm run electron:prod
```

This builds the frontend and starts Electron loading `frontend/react/dist/index.html`.
It is **not** an installer/distributable packaging pipeline.

## Testing

From repository root:

```bash
python -m pytest -q
```

or from backend:

```bash
cd backend
python -m pytest -q
```

Notes:
- CI uses a dummy Gemini key for tests; no real API credentials are required.
- Some automation capabilities are Windows-only by design and should be validated on Windows.

## CI

`.github/workflows/ci.yml` runs:
- Linux backend collection/tests
- Windows-focused backend tests
- Frontend build check

## Security and data hygiene

- Runtime memory/log/screenshot artifacts are intentionally gitignored.
- Never commit real `.env` files or credentials.
- If sensitive files were ever pushed historically, see `docs/SECURITY_HISTORY_CLEANUP.md` for local history-rewrite procedure.

## License

This project is licensed under the MIT License. See `LICENSE`.
