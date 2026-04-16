from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ExplainRequest, JobCreateRequest, MatchOverrideRequest
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])
service = ReconciliationService()


@router.post("/jobs")
def create_job(payload: JobCreateRequest, db: Session = Depends(get_db)):
    job = service.create_job(db, payload)
    return {
        "id": job.id,
        "status": job.status.value,
        "scenario_type": job.scenario_type.value,
        "created_at": job.created_at,
    }


@router.post("/jobs/{job_id}/run")
def run_job(job_id: str, db: Session = Depends(get_db)):
    try:
        job = service.run_job(db, job_id)
        return {
            "id": job.id,
            "status": job.status.value,
            "metrics": job.metrics_json,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/run_second_pass")
def run_second_pass(job_id: str, db: Session = Depends(get_db)):
    try:
        run_info = service.run_second_pass_on_exceptions(db, job_id)
        return {
            "job_id": job_id,
            "second_pass_stats": run_info.get("second_pass_stats", {}),
            "results": service.job_results(db, job_id),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/results")
def job_results(job_id: str, db: Session = Depends(get_db)):
    try:
        return service.job_results(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/explain_match")
def explain_match(payload: ExplainRequest, db: Session = Depends(get_db)):
    if not payload.match_id:
        raise HTTPException(status_code=400, detail="match_id is required")
    try:
        return service.explain_match(db, payload.match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/explain_exception")
def explain_exception(payload: ExplainRequest, db: Session = Depends(get_db)):
    if not payload.exception_id:
        raise HTTPException(status_code=400, detail="exception_id is required")
    try:
        return service.explain_exception(db, payload.exception_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/matches/override")
def override_match(payload: MatchOverrideRequest, db: Session = Depends(get_db)):
    try:
        match = service.override_match(
            db,
            match_id=payload.match_id,
            auto_accepted=payload.auto_accepted,
            reason=payload.reason,
            actor=payload.actor,
        )
        return {"id": match.id, "auto_accepted": match.auto_accepted}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
