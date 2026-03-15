from fastapi import FastAPI

from app.api.routers.ingestion import router as ingestion_router
from app.api.routers.reconciliation import router as reconciliation_router
from app.config.settings import get_settings
from app.core.logging import configure_logging
from app.db.init_db import create_tables

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="GenAI Financial Reconciliation Platform", version="1.0.0")


@app.on_event("startup")
def startup_event() -> None:
    create_tables()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


app.include_router(ingestion_router)
app.include_router(reconciliation_router)
