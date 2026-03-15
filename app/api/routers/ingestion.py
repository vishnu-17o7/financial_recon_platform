from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ScenarioType
from app.services.ingestion_service import IngestionService
from app.services.pipeline_service import NormalizationPipelineService, ParserRegistry, save_upload

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/upload")
async def upload_and_ingest(
    parser_key: str = Form(...),
    scenario_type: ScenarioType = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    file_path = save_upload(file.filename, content)
    parser = ParserRegistry().get(parser_key)
    ingestion_service = IngestionService()
    batch_id = ingestion_service.ingest_file(db, parser, file_path, scenario_type)
    normalized_count = NormalizationPipelineService().normalize_batch(db, batch_id)
    return {
        "ingestion_batch_id": batch_id,
        "normalized_count": normalized_count,
        "source_metadata": parser.source_metadata,
    }
