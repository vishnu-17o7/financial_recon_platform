# GenAI Financial Reconciliation Platform

Production-oriented reference implementation of a modular reconciliation platform using:

- FastAPI for APIs
- PostgreSQL + pgvector for storage and vector search
- Rule-based + embedding-based + LLM-assisted matching

## Prerequisites

1. Docker Desktop (with Docker Compose V2) installed and running.
2. Optional: Python 3.11 if you want to run outside Docker.
3. Bun 1.2+ (for the React frontend).
4. Run all commands from the project root directory.

## Environment setup

Create a `.env` file in the project root with values like this:

```dotenv
APP_NAME=genai-recon
ENV=dev
LOG_LEVEL=INFO

DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/recon_db
VECTOR_DIM=1536

LLM_PROVIDER=mock
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
LLM_API_KEY=replace_me
```

Notes:

1. The default Docker database URL uses host `db` (the Compose service name).
1. If you run the app locally (not in container), use `localhost` instead of `db`:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/recon_db
```

1. If you use a cloud database, keep SQLAlchemy+psycopg URL format:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME?sslmode=require
```

## Run the app with Docker (recommended)

1. Build and start services:

```powershell
docker compose up -d --build
```

1. Confirm services are up:

```powershell
docker compose ps
```

1. Check API health:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected response:

```json
{"status":"ok","app":"genai-recon"}
```

1. Open web dashboard:

```text
http://localhost:8000
```

The dashboard at `http://localhost:8000` serves the built React app from `app/ui`.

1. Open API docs:

```text
http://localhost:8000/docs
```

1. Run tests inside the app container:

```powershell
docker compose exec app python -m pytest -q
```

1. Run demo reconciliation inside the app container:

```powershell
docker compose exec app python -m scripts.demo_reconcile_bank_gl
```

1. View live app logs:

```powershell
docker compose logs -f app
```

1. Stop services:

```powershell
docker compose down
```

1. Reset DB volume completely (only when needed):

```powershell
docker compose down -v
docker compose up -d --build
```

## Run the React UI with Bun (development)

1. Start backend API (Docker or local Python):

```powershell
docker compose up -d --build
```

1. In a new terminal, run frontend with Bun:

```powershell
cd frontend
bun install
bun run dev
```

1. Open the React dev UI:

```text
http://localhost:5173
```

The Vite dev server proxies API requests to `http://localhost:8000`.

## Build React UI for FastAPI serving

1. Build frontend assets into `app/ui`:

```powershell
cd frontend
bun run build
```

1. Start backend and open:

```text
http://localhost:8000
```

## One-command startup script (PowerShell)

Use the helper script to start Docker backend and Bun frontend together:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1
```

Common options:

```powershell
# Skip backend image rebuild
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1 -SkipBackendBuild

# Stop backend containers automatically when frontend exits
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1 -StopBackendOnExit
```

## Run locally without Docker (optional)

1. Create and activate virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

1. Install dependencies:

```powershell
pip install -r requirements.txt
```

1. Start only Postgres via Docker:

```powershell
docker compose up -d db
```

1. Ensure `.env` uses local DB host:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/recon_db
```

1. Set Python path for absolute imports:

```powershell
$env:PYTHONPATH = "."
```

1. Run API:

```powershell
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

1. Run tests:

```powershell
python -m pytest -q
```

1. Run demo script:

```powershell
python scripts/demo_reconcile_bank_gl.py
```

## Common issues

1. `pytest` not recognized on Windows.
Use `python -m pytest -q` or run tests inside Docker with `docker compose exec app python -m pytest -q`.

2. `ModuleNotFoundError: No module named 'app'`.
Run commands from project root and set `PYTHONPATH=.` for local execution, or run scripts inside the app container.

3. `type "vector" does not exist` during startup.
The app now enables the extension at startup; if this came from an old DB state, reset with `docker compose down -v` and start again.

## Implemented scenarios

- Bank statement <-> GL cash accounts (detailed strategy)
- Customer payments <-> AR invoices (detailed strategy)
- Other scenarios wired via extensible strategy interface and constraints hooks

## Notes

- `LLMClient` and `EmbeddingClient` are provider-agnostic interfaces.
- This repo includes deterministic fallbacks and mock clients for local development/testing.
- React UI source is in `frontend/src` and is organized using reusable components under `frontend/src/components`.
