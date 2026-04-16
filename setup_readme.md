# Setup Readme

This file explains how to set up and run the Financial Reconciliation Platform on a new system.

## 1. Prerequisites

Install these first:

1. Git
2. Docker Desktop (with Docker Compose V2)
3. Python 3.11+ (needed for local backend mode and tests)
4. Bun 1.2+ (used by the frontend workflow and fullstack script)

Optional:

1. Node.js 18+ and npm (if you prefer npm over Bun for frontend commands)

## 2. Clone the repository

```powershell
git clone <your-repo-url>
cd financial_recon_platform
```

## 3. Create the environment file

Create a `.env` file at the project root with at least these values:

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

Important:

1. Use host `db` in `DATABASE_URL` when running backend inside Docker.
2. Use host `localhost` when running backend locally via Python.

## 4. Fastest way to run (Windows PowerShell)

From project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1
```

What it does:

1. Starts backend + database with Docker Compose
2. Starts frontend dev server with Bun

URLs:

1. Frontend: http://localhost:5173
2. Backend API: http://localhost:8000
3. API docs: http://localhost:8000/docs

Useful script options:

```powershell
# Skip backend image rebuild
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1 -SkipBackendBuild

# Stop backend containers when frontend exits
powershell -ExecutionPolicy Bypass -File .\scripts\run-fullstack.ps1 -StopBackendOnExit
```

## 5. Manual run (cross-platform)

### 5.1 Start backend with Docker

```powershell
docker compose up -d --build
```

Check health:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

### 5.2 Start frontend dev server

```powershell
cd frontend
bun install
bun run dev
```

If using npm instead of Bun:

```powershell
cd frontend
npm install
npm run dev
```

## 6. Run backend with built UI only (no Vite dev server)

Build frontend assets into `app/ui`:

```powershell
cd frontend
bun install
bun run build
cd ..
docker compose up -d --build
```

Then open:

1. App UI: http://localhost:8000
2. API docs: http://localhost:8000/docs

## 7. Optional local backend (Python on host)

If you want to run backend outside Docker:

```powershell
# from project root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# start only database container
docker compose up -d db

# use localhost DB for local backend run
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/recon_db"

# run backend
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

## 8. Run tests

Local Python environment:

```powershell
python -m pytest -q
```

Inside Docker app container:

```powershell
docker compose exec app python -m pytest -q
```

## 9. Stop and cleanup

Stop containers:

```powershell
docker compose down
```

Full reset (including DB volume):

```powershell
docker compose down -v
```

## 10. Sample files for first test run

Recommended upload pair (Bank vs GL, asymmetric amount vs debit/credit mapping test):

1. `sample_data/mapped_left_complex.csv`
2. `sample_data/mapped_right_complex.csv`

Simple baseline pair:

1. `sample_data/bank_sample.csv`
2. `sample_data/gl_sample.csv`