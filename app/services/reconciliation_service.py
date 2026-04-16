from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.llm.interfaces import EmbeddingClient, LLMClient
from app.llm.mock_clients import MockEmbeddingClient, MockLLMClient
from app.llm.openrouter_client import OpenRouterClient
from app.config.settings import get_settings
from app.llm.prompt_builders import (
    build_explanation_prompt,
    build_second_pass_reconciliation_prompt,
)
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

    @staticmethod
    def _normalize_llm_reconciliation_payload(payload: object) -> dict[str, list[dict]]:
        if not isinstance(payload, dict):
            return {
                "matches": [],
                "unmatched_left": [],
                "unmatched_right": [],
            }

        def _dict_items(value: object) -> list[dict]:
            if not isinstance(value, list):
                return []
            return [item for item in value if isinstance(item, dict)]

        return {
            "matches": _dict_items(payload.get("matches")),
            "unmatched_left": _dict_items(payload.get("unmatched_left")),
            "unmatched_right": _dict_items(payload.get("unmatched_right")),
        }

    @staticmethod
    def _extract_match_ids(item: dict) -> tuple[str, str]:
        left_id = str(
            item.get("left_transaction_id")
            or item.get("transaction_a_id")
            or item.get("left_id")
            or ""
        ).strip()
        right_id = str(
            item.get("right_transaction_id")
            or item.get("transaction_b_id")
            or item.get("right_id")
            or ""
        ).strip()
        return left_id, right_id

    @staticmethod
    def _confidence(raw_value: object, default_value: float = 0.0) -> float:
        try:
            return max(0.0, min(1.0, float(raw_value)))
        except (TypeError, ValueError):
            return default_value

    @staticmethod
    def _llm_transaction_payload(txn: TransactionNormalized) -> dict:
        return {
            "id": txn.id,
            "transaction_date": str(txn.transaction_date),
            "value_date": str(txn.value_date) if txn.value_date else None,
            "amount": str(txn.amount),
            "currency": txn.currency,
            "reference": txn.reference_number,
            "counterparty": txn.counterparty_normalized,
            "description": txn.description_clean,
            "direction": txn.direction.value,
        }

    def run_second_pass_on_exceptions(self, db: Session, job_id: str) -> dict:
        job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
        if not job:
            raise ValueError("job not found")

        open_exceptions = (
            db.query(ReconciliationException)
            .filter(
                ReconciliationException.reconciliation_job_id == job_id,
                ReconciliationException.status == ExceptionStatus.OPEN,
            )
            .all()
        )
        if not open_exceptions:
            return {
                "job_id": job_id,
                "second_pass_stats": {
                    "evaluated_exceptions": 0,
                    "second_pass_matches": 0,
                    "resolved_exceptions": 0,
                    "remaining_exceptions": 0,
                },
            }

        exception_txn_ids = {ex.transaction_id for ex in open_exceptions}
        exception_txns = (
            db.query(TransactionNormalized)
            .filter(TransactionNormalized.id.in_(exception_txn_ids))
            .all()
        )
        txn_by_id = {txn.id: txn for txn in exception_txns}

        side_a_candidates = [txn for txn in exception_txns if txn.side == "A"]
        side_b_candidates = [txn for txn in exception_txns if txn.side == "B"]

        if not side_a_candidates or not side_b_candidates:
            return {
                "job_id": job_id,
                "second_pass_stats": {
                    "evaluated_exceptions": len(open_exceptions),
                    "second_pass_matches": 0,
                    "resolved_exceptions": 0,
                    "remaining_exceptions": len(open_exceptions),
                },
            }

        existing_matches = (
            db.query(Match)
            .filter(Match.reconciliation_job_id == job_id)
            .all()
        )
        used_left = {m.transaction_a_id for m in existing_matches}
        used_right = {m.transaction_b_id for m in existing_matches}

        available_left = [txn for txn in side_a_candidates if txn.id not in used_left]
        available_right = [txn for txn in side_b_candidates if txn.id not in used_right]

        if not available_left or not available_right:
            return {
                "job_id": job_id,
                "second_pass_stats": {
                    "evaluated_exceptions": len(open_exceptions),
                    "second_pass_matches": 0,
                    "resolved_exceptions": 0,
                    "remaining_exceptions": len(open_exceptions),
                },
            }

        prompt = build_second_pass_reconciliation_prompt(
            scenario_type=job.scenario_type.value,
            left_transactions=[self._llm_transaction_payload(txn) for txn in available_left],
            right_transactions=[
                self._llm_transaction_payload(txn) for txn in available_right
            ],
        )

        llm_response: object = None
        try:
            llm_response = self.llm_client.complete_json(prompt)
            parsed = self._normalize_llm_reconciliation_payload(llm_response)
        except Exception as exc:
            logger.exception(
                "Second-pass LLM reconciliation failed",
                extra={"extra_data": {"job_id": job_id, "error": str(exc)}},
            )
            parsed = {
                "matches": [],
                "unmatched_left": [],
                "unmatched_right": [],
            }

        available_left_ids = {txn.id for txn in available_left}
        available_right_ids = {txn.id for txn in available_right}
        newly_matched_ids: set[str] = set()
        new_matches_count = 0

        for item in parsed.get("matches", []):
            left_id, right_id = self._extract_match_ids(item)
            if not left_id or not right_id:
                continue
            if left_id not in available_left_ids or right_id not in available_right_ids:
                continue
            if left_id in used_left or right_id in used_right:
                continue

            left_txn = txn_by_id.get(left_id)
            right_txn = txn_by_id.get(right_id)
            if not left_txn or not right_txn:
                continue

            confidence = self._confidence(item.get("confidence"), default_value=0.65)
            if confidence < 0.65:
                continue

            amount_delta = abs(
                Decimal(str(left_txn.amount)) - Decimal(str(right_txn.amount))
            )
            date_delta_days = abs(
                (left_txn.transaction_date - right_txn.transaction_date).days
            )

            db.add(
                Match(
                    reconciliation_job_id=job.id,
                    transaction_a_id=left_id,
                    transaction_b_id=right_id,
                    match_type=MatchType.ONE_TO_ONE,
                    confidence_score=Decimal(str(round(confidence, 4))),
                    algorithm_used="llm_second_pass",
                    amount_delta=amount_delta,
                    date_delta_days=date_delta_days,
                    auto_accepted=confidence >= 0.8,
                    llm_reason=str(item.get("reason") or "Second-pass LLM retry match"),
                )
            )

            used_left.add(left_id)
            used_right.add(right_id)
            newly_matched_ids.add(left_id)
            newly_matched_ids.add(right_id)
            new_matches_count += 1

        resolved_exceptions = 0
        if newly_matched_ids:
            resolved_exceptions = (
                db.query(ReconciliationException)
                .filter(
                    ReconciliationException.reconciliation_job_id == job_id,
                    ReconciliationException.status == ExceptionStatus.OPEN,
                    ReconciliationException.transaction_id.in_(newly_matched_ids),
                )
                .delete(synchronize_session=False)
            )

        db.flush()

        total_matches = (
            db.query(func.count(Match.id))
            .filter(Match.reconciliation_job_id == job_id)
            .scalar()
            or 0
        )
        total_open_exceptions = (
            db.query(func.count(ReconciliationException.id))
            .filter(
                ReconciliationException.reconciliation_job_id == job_id,
                ReconciliationException.status == ExceptionStatus.OPEN,
            )
            .scalar()
            or 0
        )
        reconciled_amt = (
            db.query(func.coalesce(func.sum(Match.amount_delta), 0))
            .filter(Match.reconciliation_job_id == job_id)
            .scalar()
            or Decimal("0")
        )

        metrics = job.metrics_json if isinstance(job.metrics_json, dict) else {}
        side_a_count = int(metrics.get("side_a_count") or 0)
        metrics.update(
            {
                "matched_count": int(total_matches),
                "exception_count": int(total_open_exceptions),
                "matched_pct": round((int(total_matches) / side_a_count) * 100, 2)
                if side_a_count
                else 0,
                "reconciled_amount_delta_total": str(reconciled_amt),
            }
        )
        second_pass_stats = {
            "evaluated_exceptions": len(open_exceptions),
            "second_pass_matches": new_matches_count,
            "resolved_exceptions": int(resolved_exceptions),
            "remaining_exceptions": int(total_open_exceptions),
        }
        metrics["second_pass_stats"] = second_pass_stats
        job.metrics_json = metrics
        job.completed_at = datetime.utcnow()

        db.add(
            AuditLog(
                entity_type="reconciliation_job",
                entity_id=job.id,
                action="second_pass_run",
                actor="system",
                llm_prompt=prompt,
                llm_response=str(llm_response),
                new_value=second_pass_stats,
            )
        )

        db.commit()

        return {
            "job_id": job_id,
            "second_pass_stats": second_pass_stats,
        }

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
