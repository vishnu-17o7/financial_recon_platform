import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ScenarioType
from app.services.mapped_reconciliation_service import MappedReconciliationService
from app.services.ingestion_service import IngestionService
from app.services.pipeline_service import NormalizationPipelineService, ParserRegistry, save_upload

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
mapped_recon_service = MappedReconciliationService()


async def _save_temp_upload(upload: UploadFile) -> str:
    upload_dir = Path("tmp_uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "upload.csv").suffix or ".csv"
    temp_path = upload_dir / f"mapped_{uuid4().hex}{suffix}"
    temp_path.write_bytes(await upload.read())
    return str(temp_path)


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


@router.post("/mapping/suggest")
async def suggest_mapping(
    scenario_type: ScenarioType = Form(...),
    left_file: UploadFile = File(...),
    right_file: UploadFile = File(...),
):
    left_path = await _save_temp_upload(left_file)
    right_path = await _save_temp_upload(right_file)

    try:
        return mapped_recon_service.suggest_for_files(
            scenario_type=scenario_type,
            left_file_path=left_path,
            right_file_path=right_path,
            left_file_name=left_file.filename or "left.csv",
            right_file_name=right_file.filename or "right.csv",
        )
    finally:
        Path(left_path).unlink(missing_ok=True)
        Path(right_path).unlink(missing_ok=True)


@router.post("/mapping/reconcile")
async def reconcile_with_mapping(
    scenario_type: ScenarioType = Form(...),
    mapping_json: str = Form(...),
    created_by: str = Form("ui-analyst"),
    left_label: str = Form("Left Source"),
    right_label: str = Form("Right Source"),
    left_file: UploadFile = File(...),
    right_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        mapping_payload = json.loads(mapping_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="mapping_json must be valid JSON") from exc

    left_path = await _save_temp_upload(left_file)
    right_path = await _save_temp_upload(right_file)

    try:
        return mapped_recon_service.reconcile_with_mapping(
            db=db,
            scenario_type=scenario_type,
            created_by=created_by,
            left_label=left_label,
            right_label=right_label,
            left_file_path=left_path,
            right_file_path=right_path,
            mapping_payload=mapping_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        Path(left_path).unlink(missing_ok=True)
        Path(right_path).unlink(missing_ok=True)
