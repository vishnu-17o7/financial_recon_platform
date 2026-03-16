from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.llm.interfaces import EmbeddingClient, LLMClient
from app.llm.mock_clients import MockEmbeddingClient, MockLLMClient
from app.llm.openrouter_client import OpenRouterClient
from app.config.settings import get_settings
from app.llm.prompt_builders import build_explanation_prompt
from app.matching.engine import to_feature
from app.matching.strategies.bank_gl_strategy import BankGLMatchingStrategy
from app.matching.strategies.customer_ar_strategy import CustomerARMatchingStrategy
from app.matching.strategies.generic_profile_strategy import (
    GenericProfileMatchingStrategy,
)
from app.models.entities import (
    AuditLog,
    Match,
    ReconciliationException,
    ReconciliationJob,
    TransactionNormalized,
    TransactionRaw,
)
from app.models.enums import ExceptionStatus, JobStatus, MatchType, ScenarioType
from app.schemas.common import JobCreateRequest

logger = get_logger(__name__)


def _get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "OpenRouter":
        return OpenRouterClient()
    return MockLLMClient()


class ReconciliationService:
    def __init__(
        self,
        llm_client: LLMClient | None = None,
        embedding_client: EmbeddingClient | None = None,
    ):
        self.llm_client = llm_client or _get_llm_client()
        self.embedding_client = embedding_client or MockEmbeddingClient()

    @staticmethod
    def _get_strategy(scenario: ScenarioType):
        if scenario == ScenarioType.BANK_GL:
            return BankGLMatchingStrategy()
        if scenario == ScenarioType.CUSTOMER_AR:
            return CustomerARMatchingStrategy()
        if scenario in {
            ScenarioType.VENDOR_AP,
            ScenarioType.CREDIT_CARD_EXPENSE,
            ScenarioType.PAYROLL,
            ScenarioType.TAX,
            ScenarioType.INTERCOMPANY,
            ScenarioType.SUBLEDGER_GL,
            ScenarioType.CASH_BALANCE,
        }:
            return GenericProfileMatchingStrategy(scenario)
        return BankGLMatchingStrategy()

    def create_job(self, db: Session, request: JobCreateRequest) -> ReconciliationJob:
        job = ReconciliationJob(
            scenario_type=request.scenario_type,
            period_start=request.period_start,
            period_end=request.period_end,
            status=JobStatus.CREATED,
            filters_json=request.filters,
            created_by=request.created_by,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def run_job(self, db: Session, job_id: str) -> ReconciliationJob:
        job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
        if not job:
            raise ValueError("job not found")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        try:
            tx_query = db.query(TransactionNormalized).filter(
                and_(
                    TransactionNormalized.scenario_type == job.scenario_type,
                    TransactionNormalized.transaction_date >= job.period_start,
                    TransactionNormalized.transaction_date <= job.period_end,
                )
            )

            filters = job.filters_json if isinstance(job.filters_json, dict) else {}
            ingestion_batch_id = filters.get("ingestion_batch_id")
            if ingestion_batch_id:
                tx_query = tx_query.join(
                    TransactionRaw,
                    TransactionRaw.id == TransactionNormalized.raw_transaction_id,
                ).filter(TransactionRaw.ingestion_batch_id == ingestion_batch_id)

            txns = tx_query.all()
            side_a = [to_feature(t) for t in txns if t.side == "A"]
            side_b = [to_feature(t) for t in txns if t.side == "B"]

            strategy = self._get_strategy(job.scenario_type)
            matches, unmatched_a_ids = strategy.match(
                db, side_a, side_b, self.llm_client, self.embedding_client
            )

            for m in matches:
                db.add(
                    Match(
                        reconciliation_job_id=job.id,
                        transaction_a_id=m.transaction_a_id,
                        transaction_b_id=m.transaction_b_id,
                        match_type=MatchType.ONE_TO_ONE,
                        confidence_score=Decimal(str(round(m.score, 4))),
                        algorithm_used=m.algorithm,
                        amount_delta=m.amount_delta,
                        date_delta_days=m.date_delta_days,
                        auto_accepted=m.score >= 0.85,
                        llm_reason=m.reason,
                    )
                )

            for txn_id in unmatched_a_ids:
                db.add(
                    ReconciliationException(
                        reconciliation_job_id=job.id,
                        transaction_id=txn_id,
                        status=ExceptionStatus.OPEN,
                        reason_code="NO_MATCH",
                        reason_detail="No candidate satisfied deterministic and similarity constraints",
                        recommended_action="Review counterpart entries or update mapping/reference data",
                    )
                )

            db.flush()

            matched_count = len(matches)
            total_a = len(side_a)
            exception_count = len(unmatched_a_ids)
            reconciled_amt = sum((m.amount_delta for m in matches), Decimal("0"))

            job.metrics_json = {
                "side_a_count": total_a,
                "side_b_count": len(side_b),
                "matched_count": matched_count,
                "matched_pct": round((matched_count / total_a) * 100, 2)
                if total_a
                else 0,
                "exception_count": exception_count,
                "reconciled_amount_delta_total": str(reconciled_amt),
            }
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()

            db.add(
                AuditLog(
                    entity_type="reconciliation_job",
                    entity_id=job.id,
                    action="job_completed",
                    actor="system",
                    new_value=job.metrics_json,
                )
            )
            db.commit()
            db.refresh(job)
            logger.info(
                "Reconciliation job completed", extra={"extra_data": {"job_id": job.id}}
            )
            return job
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db.commit()
            logger.exception(
                "Reconciliation job failed", extra={"extra_data": {"job_id": job.id}}
            )
            raise

    def explain_match(self, db: Session, match_id: str) -> dict:
        match = db.query(Match).filter(Match.id == match_id).first()
        if not match:
            raise ValueError("match not found")
        context = {
            "match_id": match.id,
            "algorithm": match.algorithm_used,
            "confidence": str(match.confidence_score),
            "amount_delta": str(match.amount_delta),
            "date_delta_days": match.date_delta_days,
            "llm_reason": match.llm_reason,
        }
        prompt = build_explanation_prompt(context, is_exception=False)
        response = self.llm_client.complete_json(prompt)
        db.add(
            AuditLog(
                entity_type="match",
                entity_id=match.id,
                action="llm_explain_match",
                actor="system",
                llm_prompt=prompt,
                llm_response=str(response),
            )
        )
        db.commit()
        return response

    def explain_exception(self, db: Session, exception_id: str) -> dict:
        ex = (
            db.query(ReconciliationException)
            .filter(ReconciliationException.id == exception_id)
            .first()
        )
        if not ex:
            raise ValueError("exception not found")
        context = {
            "exception_id": ex.id,
            "reason_code": ex.reason_code,
            "reason_detail": ex.reason_detail,
            "recommended_action": ex.recommended_action,
        }
        prompt = build_explanation_prompt(context, is_exception=True)
        response = self.llm_client.complete_json(prompt)
        db.add(
            AuditLog(
                entity_type="exception",
                entity_id=ex.id,
                action="llm_explain_exception",
                actor="system",
                llm_prompt=prompt,
                llm_response=str(response),
            )
        )
        db.commit()
        return response

    def override_match(
        self, db: Session, match_id: str, auto_accepted: bool, reason: str, actor: str
    ) -> Match:
        match = db.query(Match).filter(Match.id == match_id).first()
        if not match:
            raise ValueError("match not found")
        old_val = {"auto_accepted": match.auto_accepted}
        match.auto_accepted = auto_accepted
        db.add(
            AuditLog(
                entity_type="match",
                entity_id=match.id,
                action="manual_override",
                actor=actor,
                old_value=old_val,
                new_value={"auto_accepted": auto_accepted},
                notes=reason,
            )
        )
        db.commit()
        db.refresh(match)
        return match

    def job_results(self, db: Session, job_id: str) -> dict:
        job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
        if not job:
            raise ValueError("job not found")
        matches = db.query(Match).filter(Match.reconciliation_job_id == job_id).all()
        exceptions = (
            db.query(ReconciliationException)
            .filter(ReconciliationException.reconciliation_job_id == job_id)
            .all()
        )

        transaction_ids = (
            {m.transaction_a_id for m in matches}
            | {m.transaction_b_id for m in matches}
            | {e.transaction_id for e in exceptions}
        )
        txn_by_id: dict[str, TransactionNormalized] = {}
        if transaction_ids:
            txns = (
                db.query(TransactionNormalized)
                .filter(TransactionNormalized.id.in_(transaction_ids))
                .all()
            )
            txn_by_id = {txn.id: txn for txn in txns}

        def txn_summary(txn_id: str) -> dict | None:
            txn = txn_by_id.get(txn_id)
            if not txn:
                return None
            return {
                "id": txn.id,
                "side": txn.side,
                "amount": str(txn.amount),
                "currency": txn.currency,
                "transaction_date": str(txn.transaction_date),
                "reference": txn.reference_number,
                "counterparty": txn.counterparty_normalized,
                "description": txn.description_clean,
            }

        by_reason = {
            r: c
            for r, c in db.query(
                ReconciliationException.reason_code,
                func.count(ReconciliationException.id),
            )
            .filter(ReconciliationException.reconciliation_job_id == job_id)
            .group_by(ReconciliationException.reason_code)
            .all()
        }
        return {
            "job_id": job_id,
            "status": job.status.value,
            "metrics": job.metrics_json,
            "matches": [
                {
                    "id": m.id,
                    "a": m.transaction_a_id,
                    "b": m.transaction_b_id,
                    "confidence": str(m.confidence_score),
                    "algo": m.algorithm_used,
                    "auto_accepted": m.auto_accepted,
                    "amount_delta": str(m.amount_delta)
                    if m.amount_delta is not None
                    else None,
                    "date_delta_days": m.date_delta_days,
                    "left": txn_summary(m.transaction_a_id),
                    "right": txn_summary(m.transaction_b_id),
                }
                for m in matches
            ],
            "exceptions": [
                {
                    "id": e.id,
                    "txn": e.transaction_id,
                    "status": e.status.value,
                    "reason": e.reason_code,
                    "reason_detail": e.reason_detail,
                    "recommended_action": e.recommended_action,
                    "transaction": txn_summary(e.transaction_id),
                }
                for e in exceptions
            ],
            "exception_buckets": by_reason,
        }
