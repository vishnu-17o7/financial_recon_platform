# GenAI Financial Reconciliation Platform

Production-oriented reference implementation of a modular reconciliation platform using:

- FastAPI for APIs
- PostgreSQL + pgvector for storage and vector search
- Rule-based + embedding-based + LLM-assisted matching

## Reconciliation process (brief)

At a high level, the platform runs as a staged pipeline:

1. Ingest source files using known parsers or LLM-assisted column mapping.
2. Normalize rows into a canonical transaction model (`TransactionNormalized`) with side `A`/`B` assignment.
3. Create and run a reconciliation job for a scenario and date range.
4. Match side `A` to side `B` using deterministic filters, embedding similarity, and optional LLM tie-break.
5. Persist matched pairs, unmatched exceptions, metrics, and audit logs for analyst review.

Typical analyst loop:

1. Upload files and run reconciliation.
2. Review matches, exceptions, and metrics in the dashboard.
3. Request LLM explanations and manually override matches when needed.
4. Re-run after mapping/rule adjustments.

## Diagrams

### End-to-end flowchart

```mermaid
flowchart TD
	A[Source files] --> B{Ingestion path}
	B -->|Known parser| C[/POST /ingestion/upload/]
	B -->|LLM-assisted mapping| D[/POST /ingestion/mapping/reconcile/]

	C --> E[TransactionRaw records]
	D --> E
	E --> F[NormalizationPipelineService]
	F --> G[TransactionNormalized records side A and side B]

	G --> H[/POST /reconciliation/jobs/]
	H --> I[/POST /reconciliation/jobs/job_id/run/]
	I --> J[Scenario strategy plus HybridMatchingEngine]

	J --> K[Matched pairs]
	J --> L[Unmatched side A transactions]

	K --> M[Persist Match records]
	M --> N{score >= 0.85}
	N -->|Yes| O[auto_accepted true]
	N -->|No| P[auto_accepted false and manual review]

	L --> Q[Persist ReconciliationException records]
	O --> R[Job metrics and audit log]
	P --> R
	Q --> R

	R --> S[/GET /reconciliation/jobs/job_id/results/]
	S --> T[Dashboard metrics matches exceptions]
	T --> U[/POST explain and override endpoints/]
```

### System architecture

```mermaid
flowchart LR
	A[User Browser] --> B[React UI frontend]
	B --> C[FastAPI routers ingestion and reconciliation]
	A --> D[FastAPI static UI mount at root]

	C --> E[IngestionService and MappedReconciliationService]
	E --> F[NormalizationPipelineService]

	C --> G[ReconciliationService]
	G --> H[Scenario strategies]
	H --> I[HybridMatchingEngine]

	I --> J[EmbeddingClient]
	I --> K[LLMClient tie-break]
	G --> L[LLMClient explain]

	F --> M[(PostgreSQL)]
	G --> M
	I --> M
	M --> N[(pgvector embeddings)]
```

### Reconciliation job lifecycle

```mermaid
stateDiagram-v2
	[*] --> CREATED
	CREATED --> RUNNING: run_job
	RUNNING --> COMPLETED: matches and exceptions saved
	RUNNING --> FAILED: unhandled error
	COMPLETED --> [*]
	FAILED --> [*]
```

### Matching decision flow

```mermaid
flowchart TD
	A[Pick one side A transaction] --> B[Build candidate pool]
	B --> C{Pass currency amount date constraints}
	C -->|No candidates| D[Create NO_MATCH exception]
	C -->|Has candidates| E[Score by rules plus embeddings]

	E --> F{Close top scores}
	F -->|Yes| G[LLM tie-break]
	F -->|No| H[Select best score]

	G --> I[Create Match]
	H --> I
	I --> J[Set auto_accepted if score >= 0.85]
```

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

Use one script for both development modes (backend + frontend):

```powershell
# Mode 1 (default): Docker backend + Bun frontend
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1 -Mode docker

# Mode 2: Local uvicorn backend + Bun frontend
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1 -Mode local
```

Common options:

```powershell
# Docker mode: skip backend image rebuild
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1 -Mode docker -SkipBackendBuild

# Stop backend automatically when frontend exits (works for both modes)
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1 -Mode local -StopBackendOnExit

# Local mode: customize DATABASE_URL override used for uvicorn process
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1 -Mode local -LocalDatabaseUrl "postgresql+psycopg://postgres:postgres@localhost:5432/recon_db"

# Local mode: use DATABASE_URL from .env as-is (no override)
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1 -Mode local -UseEnvDatabaseUrl
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

Note:
Use `app.api.main:app` as the uvicorn target module. `server:app` is not the backend entrypoint in this repository.

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
