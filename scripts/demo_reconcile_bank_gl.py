from datetime import date

from app.db.init_db import create_tables
from app.db.session import SessionLocal
from app.ingestion.parsers.bank_csv_parser import GenericBankCSVParser
from app.ingestion.parsers.gl_csv_parser import GLExportCSVParser
from app.models.entities import Match, ReconciliationException
from app.models.enums import ScenarioType
from app.schemas.common import JobCreateRequest
from app.services.ingestion_service import IngestionService
from app.services.pipeline_service import NormalizationPipelineService
from app.services.reconciliation_service import ReconciliationService


def run_demo() -> None:
    create_tables()
    db = SessionLocal()

    ingestion = IngestionService()
    batch_bank = ingestion.ingest_file(
        db, GenericBankCSVParser(), "sample_data/bank_sample.csv", ScenarioType.BANK_GL
    )
    batch_gl = ingestion.ingest_file(db, GLExportCSVParser(), "sample_data/gl_sample.csv", ScenarioType.BANK_GL)

    pipeline = NormalizationPipelineService()
    pipeline.normalize_batch(db, batch_bank)
    pipeline.normalize_batch(db, batch_gl)

    recon = ReconciliationService()
    job = recon.create_job(
        db,
        JobCreateRequest(
            scenario_type=ScenarioType.BANK_GL,
            period_start=date(2025, 2, 1),
            period_end=date(2025, 2, 28),
        ),
    )
    job = recon.run_job(db, job.id)
    print("Job status:", job.status.value)
    print("Metrics:", job.metrics_json)

    matches = db.query(Match).filter(Match.reconciliation_job_id == job.id).all()
    print("\nMatches:")
    for m in matches[:3]:
        print("-", m.id, m.transaction_a_id, "->", m.transaction_b_id, "conf", m.confidence_score)
        print("  explanation:", recon.explain_match(db, m.id))

    exceptions = db.query(ReconciliationException).filter(ReconciliationException.reconciliation_job_id == job.id).all()
    print("\nExceptions:", len(exceptions))
    for ex in exceptions[:3]:
        print("-", ex.id, ex.reason_code)
        print("  explanation:", recon.explain_exception(db, ex.id))

    db.close()


if __name__ == "__main__":
    run_demo()
