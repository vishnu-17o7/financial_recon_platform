from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pandas as pd
from sqlalchemy.orm import Session

from app.llm.interfaces import LLMClient
from app.llm.mock_clients import MockLLMClient
from app.llm.openrouter_client import OpenRouterClient
from app.llm.prompt_builders import (
    build_column_mapping_prompt,
    build_llm_reconciliation_prompt,
)
from app.config.settings import get_settings
from app.models.entities import (
    Match,
    ReconciliationException,
    ReconciliationJob,
    TransactionNormalized,
    TransactionRaw,
)
from app.models.enums import ExceptionStatus, JobStatus, MatchType, ScenarioType
from app.schemas.common import JobCreateRequest
from app.services.ingestion_service import IngestionService
from app.services.normalization_service import normalize_record
from app.services.reconciliation_service import ReconciliationService

SUPPORTED_MAPPING_FIELDS: list[dict[str, Any]] = [
    {"field": "transaction_date", "label": "Transaction Date", "required": True},
    {"field": "value_date", "label": "Value Date", "required": False},
    {"field": "description", "label": "Description", "required": False},
    {"field": "amount", "label": "Amount", "required": False},
    {"field": "debit", "label": "Debit", "required": False},
    {"field": "credit", "label": "Credit", "required": False},
    {"field": "currency", "label": "Currency", "required": False},
    {"field": "reference", "label": "Reference", "required": False},
    {"field": "counterparty", "label": "Counterparty", "required": False},
    {"field": "direction", "label": "Direction", "required": False},
    {"field": "external_txn_id", "label": "External Transaction ID", "required": False},
]

FIELD_SPEC_BY_NAME = {item["field"]: item for item in SUPPORTED_MAPPING_FIELDS}

FIELD_ALIASES: dict[str, list[str]] = {
    "transaction_date": [
        "txn_date",
        "transaction_date",
        "posting_date",
        "payment_date",
        "date",
        "txn_dt",
    ],
    "value_date": ["value_date", "settlement_date", "value_dt", "settled_date"],
    "description": ["description", "narration", "memo", "remarks", "details"],
    "amount": ["amount", "amt", "transaction_amount"],
    "debit": ["debit", "dr", "withdrawal"],
    "credit": ["credit", "cr", "deposit"],
    "currency": ["currency", "ccy", "curr"],
    "reference": ["reference", "ref", "voucher_no", "payment_id", "utr", "rrn"],
    "counterparty": ["counterparty", "party", "customer_name", "beneficiary", "vendor"],
    "direction": ["dr_cr", "direction", "flow", "type", "txn_type"],
    "external_txn_id": [
        "external_txn_id",
        "payment_id",
        "txn_id",
        "transaction_id",
        "id",
    ],
}


def _get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "OpenRouter":
        return OpenRouterClient()
    return MockLLMClient()


class ColumnMappingService:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client or _get_llm_client()

    @staticmethod
    def read_tabular_file(file_path: str) -> pd.DataFrame:
        lower = file_path.lower()
        if lower.endswith((".xlsx", ".xls")):
            return pd.read_excel(file_path)
        return pd.read_csv(file_path)

    @staticmethod
    def _is_missing(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return True
        text = str(value).strip().lower()
        return text in {"", "nan", "nat", "none", "<na>"}

    @staticmethod
    def _normalize_column_name(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")

    @staticmethod
    def _pick_best_column(columns: list[str], aliases: list[str]) -> str | None:
        if not columns:
            return None

        normalized_aliases = [a.lower().strip() for a in aliases]
        best_column = None
        best_score = 0

        for col in columns:
            norm_col = ColumnMappingService._normalize_column_name(col)
            score = 0
            for alias in normalized_aliases:
                if norm_col == alias:
                    score = max(score, 100)
                elif alias in norm_col:
                    score = max(score, 70)
                elif norm_col in alias:
                    score = max(score, 40)
            if score > best_score:
                best_score = score
                best_column = col

        return best_column if best_score > 0 else None

    def build_preview(self, df: pd.DataFrame, max_rows: int = 6) -> dict[str, Any]:
        safe_rows: list[dict[str, Any]] = []
        for _, row in df.head(max_rows).iterrows():
            row_payload: dict[str, Any] = {}
            for col in df.columns:
                row_payload[str(col)] = IngestionService._json_safe(row.get(col))
            safe_rows.append(row_payload)

        return {
            "columns": [str(c) for c in df.columns],
            "row_count": int(len(df.index)),
            "preview_rows": safe_rows,
        }

    def _heuristic_suggestions(
        self, left_columns: list[str], right_columns: list[str]
    ) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        for spec in SUPPORTED_MAPPING_FIELDS:
            field = spec["field"]
            aliases = FIELD_ALIASES.get(field, [field])
            left = self._pick_best_column(left_columns, aliases)
            right = self._pick_best_column(right_columns, aliases)
            has_match = bool(left or right)
            suggestions.append(
                {
                    "field": field,
                    "label": spec["label"],
                    "required": spec["required"],
                    "left_column": left,
                    "right_column": right,
                    "confidence": 0.76 if has_match else 0.32,
                    "rationale": "Matched by column-name similarity"
                    if has_match
                    else "No clear heuristic match",
                    "source": "heuristic",
                }
            )
        return suggestions

    @staticmethod
    def _llm_mapping_items(response: dict[str, Any]) -> list[dict[str, Any]]:
        mappings = response.get("mappings")
        if isinstance(mappings, list):
            return [item for item in mappings if isinstance(item, dict)]
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        return []

    def suggest_mappings(
        self,
        scenario_type: ScenarioType,
        left_preview: dict[str, Any],
        right_preview: dict[str, Any],
    ) -> dict[str, Any]:
        left_columns = left_preview["columns"]
        right_columns = right_preview["columns"]

        prompt = build_column_mapping_prompt(
            scenario_type=scenario_type.value,
            left_columns=left_columns,
            right_columns=right_columns,
            left_preview=left_preview["preview_rows"],
            right_preview=right_preview["preview_rows"],
            supported_fields=SUPPORTED_MAPPING_FIELDS,
        )

        llm_response: dict[str, Any]
        try:
            llm_response = self.llm_client.complete_json(prompt)
        except Exception:
            llm_response = {}

        llm_by_field: dict[str, dict[str, Any]] = {}
        for item in self._llm_mapping_items(llm_response):
            field = str(item.get("field", "")).strip()
            if field in FIELD_SPEC_BY_NAME:
                llm_by_field[field] = item

        suggestions: list[dict[str, Any]] = []
        for spec in SUPPORTED_MAPPING_FIELDS:
            field = spec["field"]
            llm_item = llm_by_field.get(field)
            if not llm_item:
                suggestions.append(
                    {
                        "field": field,
                        "label": spec["label"],
                        "required": spec["required"],
                        "left_column": None,
                        "right_column": None,
                        "confidence": 0.0,
                        "rationale": "LLM did not return a mapping suggestion for this field",
                        "source": "llm",
                    }
                )
                continue

            left_column = llm_item.get("left_column")
            if left_column not in left_columns:
                left_column = None

            right_column = llm_item.get("right_column")
            if right_column not in right_columns:
                right_column = None

            confidence_raw = llm_item.get("confidence", 0)
            try:
                confidence = max(0.0, min(1.0, float(confidence_raw)))
            except (TypeError, ValueError):
                confidence = 0.0

            suggestions.append(
                {
                    "field": field,
                    "label": spec["label"],
                    "required": spec["required"],
                    "left_column": left_column,
                    "right_column": right_column,
                    "confidence": confidence,
                    "rationale": str(
                        llm_item.get("rationale") or "LLM semantic mapping suggestion"
                    ),
                    "source": "llm",
                }
            )

        return {
            "suggestions": suggestions,
            "llm_response": llm_response,
        }

    @staticmethod
    def normalize_mapping_payload(
        mapping_payload: dict[str, Any] | list[dict[str, Any]],
        left_columns: list[str],
        right_columns: list[str],
    ) -> list[dict[str, Any]]:
        if isinstance(mapping_payload, dict):
            mapping_items = mapping_payload.get("mappings", [])
        elif isinstance(mapping_payload, list):
            mapping_items = mapping_payload
        else:
            raise ValueError("mapping_json must be a JSON object or array")

        by_field: dict[str, dict[str, Any]] = {}
        for raw_item in mapping_items:
            if not isinstance(raw_item, dict):
                continue
            field = str(raw_item.get("field", "")).strip()
            if field not in FIELD_SPEC_BY_NAME:
                continue

            left_column = raw_item.get("left_column")
            right_column = raw_item.get("right_column")

            if left_column is not None and left_column not in left_columns:
                left_column = None
            if right_column is not None and right_column not in right_columns:
                right_column = None

            by_field[field] = {
                "field": field,
                "label": FIELD_SPEC_BY_NAME[field]["label"],
                "required": FIELD_SPEC_BY_NAME[field]["required"],
                "left_column": left_column,
                "right_column": right_column,
            }

        normalized = []
        for spec in SUPPORTED_MAPPING_FIELDS:
            existing = by_field.get(spec["field"])
            if existing:
                normalized.append(existing)
            else:
                normalized.append(
                    {
                        "field": spec["field"],
                        "label": spec["label"],
                        "required": spec["required"],
                        "left_column": None,
                        "right_column": None,
                    }
                )
        return normalized

    @staticmethod
    def mapping_level_issues(
        mapping_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        by_field = {item["field"]: item for item in mapping_items}

        issues: list[dict[str, Any]] = []
        for side_key in ("left_column", "right_column"):
            side_name = "left" if side_key == "left_column" else "right"
            if not by_field["transaction_date"].get(side_key):
                issues.append(
                    {
                        "scope": "mapping",
                        "severity": "error",
                        "side": side_name,
                        "field": "transaction_date",
                        "message": f"{side_name.capitalize()} file must map Transaction Date",
                    }
                )

            has_amount = bool(by_field["amount"].get(side_key))
            has_debit_credit = bool(
                by_field["debit"].get(side_key) or by_field["credit"].get(side_key)
            )
            if not has_amount and not has_debit_credit:
                issues.append(
                    {
                        "scope": "mapping",
                        "severity": "error",
                        "side": side_name,
                        "field": "amount",
                        "message": (
                            f"{side_name.capitalize()} file needs Amount or Debit/Credit mapping "
                            "to support reconciliation"
                        ),
                    }
                )

        return issues


class MappedReconciliationService:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client or _get_llm_client()
        self.mapping_service = ColumnMappingService(self.llm_client)
        self.recon_service = ReconciliationService(llm_client=self.llm_client)

    @staticmethod
    def _build_mapping_index(
        mapping_items: list[dict[str, Any]], side_key: str
    ) -> dict[str, str]:
        mapped: dict[str, str] = {}
        for item in mapping_items:
            col = item.get(side_key)
            if col:
                mapped[item["field"]] = str(col)
        return mapped

    @staticmethod
    def _extract_row_value(row: pd.Series, column_name: str | None) -> Any:
        if not column_name:
            return None
        if column_name not in row.index:
            return None
        return IngestionService._json_safe(row.get(column_name))

    @classmethod
    def _build_normalize_payload(
        cls, row: pd.Series, mapping_index: dict[str, str]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        mapped_fields: dict[str, Any] = {}
        for field in FIELD_SPEC_BY_NAME:
            mapped_fields[field] = cls._extract_row_value(row, mapping_index.get(field))

        normalize_payload = {
            "txn_date": mapped_fields.get("transaction_date"),
            "value_date": mapped_fields.get("value_date"),
            "description": mapped_fields.get("description"),
            "amount": mapped_fields.get("amount"),
            "debit": mapped_fields.get("debit"),
            "credit": mapped_fields.get("credit"),
            "currency": mapped_fields.get("currency") or "INR",
            "reference": mapped_fields.get("reference"),
            "counterparty": mapped_fields.get("counterparty"),
            "dr_cr": mapped_fields.get("direction"),
            "external_txn_id": mapped_fields.get("external_txn_id"),
        }
        return normalize_payload, mapped_fields

    @staticmethod
    def _build_discrepancies(db: Session, job_id: str) -> list[dict[str, Any]]:
        matches = db.query(Match).filter(Match.reconciliation_job_id == job_id).all()
        if not matches:
            return []

        txn_ids = {m.transaction_a_id for m in matches} | {
            m.transaction_b_id for m in matches
        }
        txns = (
            db.query(TransactionNormalized)
            .filter(TransactionNormalized.id.in_(txn_ids))
            .all()
        )
        txn_by_id = {t.id: t for t in txns}

        raw_ids = {t.raw_transaction_id for t in txns}
        raws = db.query(TransactionRaw).filter(TransactionRaw.id.in_(raw_ids)).all()
        raw_by_id = {r.id: r for r in raws}

        report: list[dict[str, Any]] = []

        for match in matches:
            left = txn_by_id.get(match.transaction_a_id)
            right = txn_by_id.get(match.transaction_b_id)
            if not left or not right:
                continue

            left_raw_payload = (
                (raw_by_id.get(left.raw_transaction_id).raw_payload or {})
                if left.raw_transaction_id
                else {}
            )
            right_raw_payload = (
                (raw_by_id.get(right.raw_transaction_id).raw_payload or {})
                if right.raw_transaction_id
                else {}
            )

            issues: list[dict[str, Any]] = []

            amount_delta = abs(Decimal(str(left.amount)) - Decimal(str(right.amount)))
            if amount_delta > Decimal("0"):
                issues.append(
                    {
                        "field": "amount",
                        "severity": "high"
                        if amount_delta >= Decimal("1")
                        else "medium",
                        "left": str(left.amount),
                        "right": str(right.amount),
                        "note": f"Amount delta is {amount_delta}",
                    }
                )

            date_delta = abs((left.transaction_date - right.transaction_date).days)
            if date_delta > 0:
                issues.append(
                    {
                        "field": "transaction_date",
                        "severity": "medium",
                        "left": str(left.transaction_date),
                        "right": str(right.transaction_date),
                        "note": f"Date delta is {date_delta} day(s)",
                    }
                )

            if left.currency != right.currency:
                issues.append(
                    {
                        "field": "currency",
                        "severity": "high",
                        "left": left.currency,
                        "right": right.currency,
                        "note": "Currencies do not match",
                    }
                )

            left_ref = (left.reference_number or "").strip().lower()
            right_ref = (right.reference_number or "").strip().lower()
            if left_ref and right_ref and left_ref != right_ref:
                issues.append(
                    {
                        "field": "reference",
                        "severity": "low",
                        "left": left.reference_number,
                        "right": right.reference_number,
                        "note": "Reference values differ",
                    }
                )

            report.append(
                {
                    "match_id": match.id,
                    "status": "has_discrepancy" if issues else "aligned",
                    "confidence": str(match.confidence_score),
                    "left_transaction_id": left.id,
                    "right_transaction_id": right.id,
                    "left_snapshot": left_raw_payload.get("mapped_fields", {}),
                    "right_snapshot": right_raw_payload.get("mapped_fields", {}),
                    "issues": issues,
                }
            )

        return report

    @staticmethod
    def _llm_transaction_payload(txn: TransactionNormalized) -> dict[str, Any]:
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

    @staticmethod
    def _confidence(raw_value: Any, default_value: float = 0.0) -> float:
        try:
            return max(0.0, min(1.0, float(raw_value)))
        except (TypeError, ValueError):
            return default_value

    @staticmethod
    def _reason_by_transaction(items: Any) -> dict[str, str]:
        if not isinstance(items, list):
            return {}
        reasons: dict[str, str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            txn_id = str(item.get("transaction_id") or "").strip()
            if not txn_id:
                continue
            reasons[txn_id] = str(
                item.get("reason") or "No counterpart identified by LLM"
            )
        return reasons

    def _run_llm_reconciliation(
        self,
        db: Session,
        job_id: str,
        scenario_type: ScenarioType,
        ingestion_batch_id: str,
    ) -> None:
        job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job_id).first()
        if not job:
            raise ValueError("job not found")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        try:
            txns = (
                db.query(TransactionNormalized)
                .join(
                    TransactionRaw,
                    TransactionRaw.id == TransactionNormalized.raw_transaction_id,
                )
                .filter(
                    TransactionRaw.ingestion_batch_id == ingestion_batch_id,
                    TransactionNormalized.scenario_type == scenario_type,
                    TransactionNormalized.transaction_date >= job.period_start,
                    TransactionNormalized.transaction_date <= job.period_end,
                )
                .all()
            )

            side_a = [txn for txn in txns if txn.side == "A"]
            side_b = [txn for txn in txns if txn.side == "B"]
            side_a_by_id = {txn.id: txn for txn in side_a}
            side_b_by_id = {txn.id: txn for txn in side_b}

            llm_prompt = build_llm_reconciliation_prompt(
                scenario_type=scenario_type.value,
                left_transactions=[
                    self._llm_transaction_payload(txn) for txn in side_a
                ],
                right_transactions=[
                    self._llm_transaction_payload(txn) for txn in side_b
                ],
            )
            llm_response = self.llm_client.complete_json(llm_prompt)

            raw_matches = (
                llm_response.get("matches", [])
                if isinstance(llm_response, dict)
                else []
            )
            matched_left_ids: set[str] = set()
            matched_right_ids: set[str] = set()
            persisted_matches: list[Match] = []

            for item in raw_matches:
                if not isinstance(item, dict):
                    continue

                left_id = str(
                    item.get("left_transaction_id")
                    or item.get("transaction_a_id")
                    or ""
                ).strip()
                right_id = str(
                    item.get("right_transaction_id")
                    or item.get("transaction_b_id")
                    or ""
                ).strip()

                if not left_id or not right_id:
                    continue
                if left_id in matched_left_ids or right_id in matched_right_ids:
                    continue
                if left_id not in side_a_by_id or right_id not in side_b_by_id:
                    continue

                left_txn = side_a_by_id[left_id]
                right_txn = side_b_by_id[right_id]
                confidence = self._confidence(
                    item.get("confidence"), default_value=0.75
                )
                amount_delta = abs(
                    Decimal(str(left_txn.amount)) - Decimal(str(right_txn.amount))
                )
                date_delta_days = abs(
                    (left_txn.transaction_date - right_txn.transaction_date).days
                )

                match_record = Match(
                    reconciliation_job_id=job.id,
                    transaction_a_id=left_id,
                    transaction_b_id=right_id,
                    match_type=MatchType.ONE_TO_ONE,
                    confidence_score=Decimal(str(round(confidence, 4))),
                    algorithm_used="llm_reconciliation",
                    amount_delta=amount_delta,
                    date_delta_days=date_delta_days,
                    auto_accepted=confidence >= 0.8,
                    llm_reason=str(
                        item.get("reason") or "LLM semantic reconciliation decision"
                    ),
                )
                db.add(match_record)
                persisted_matches.append(match_record)

                matched_left_ids.add(left_id)
                matched_right_ids.add(right_id)

            unmatched_left_ids = set(side_a_by_id.keys()) - matched_left_ids
            unmatched_right_ids = set(side_b_by_id.keys()) - matched_right_ids
            unmatched_left_reasons = self._reason_by_transaction(
                llm_response.get("unmatched_left")
                if isinstance(llm_response, dict)
                else None
            )
            unmatched_right_reasons = self._reason_by_transaction(
                llm_response.get("unmatched_right")
                if isinstance(llm_response, dict)
                else None
            )

            for txn_id in unmatched_left_ids:
                db.add(
                    ReconciliationException(
                        reconciliation_job_id=job.id,
                        transaction_id=txn_id,
                        status=ExceptionStatus.OPEN,
                        reason_code="NO_MATCH_LLM_LEFT",
                        reason_detail=unmatched_left_reasons.get(
                            txn_id, "LLM found no valid counterpart on the right side"
                        ),
                        recommended_action="Review left transaction attributes and mapping alignment",
                    )
                )

            for txn_id in unmatched_right_ids:
                db.add(
                    ReconciliationException(
                        reconciliation_job_id=job.id,
                        transaction_id=txn_id,
                        status=ExceptionStatus.OPEN,
                        reason_code="NO_MATCH_LLM_RIGHT",
                        reason_detail=unmatched_right_reasons.get(
                            txn_id, "LLM found no valid counterpart on the left side"
                        ),
                        recommended_action="Review right transaction attributes and mapping alignment",
                    )
                )

            matched_count = len(persisted_matches)
            side_a_count = len(side_a)
            side_b_count = len(side_b)
            exception_count = len(unmatched_left_ids) + len(unmatched_right_ids)
            reconciled_amt = sum(
                (match.amount_delta for match in persisted_matches), Decimal("0")
            )

            job.metrics_json = {
                "side_a_count": side_a_count,
                "side_b_count": side_b_count,
                "matched_count": matched_count,
                "matched_pct": round((matched_count / side_a_count) * 100, 2)
                if side_a_count
                else 0,
                "exception_count": exception_count,
                "reconciled_amount_delta_total": str(reconciled_amt),
                "reconciliation_engine": "llm",
            }
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()

            db.commit()
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db.commit()
            raise

    def suggest_for_files(
        self,
        scenario_type: ScenarioType,
        left_file_path: str,
        right_file_path: str,
        left_file_name: str,
        right_file_name: str,
    ) -> dict[str, Any]:
        left_df = self.mapping_service.read_tabular_file(left_file_path)
        right_df = self.mapping_service.read_tabular_file(right_file_path)

        left_preview = self.mapping_service.build_preview(left_df)
        right_preview = self.mapping_service.build_preview(right_df)
        suggestions_payload = self.mapping_service.suggest_mappings(
            scenario_type=scenario_type,
            left_preview=left_preview,
            right_preview=right_preview,
        )

        return {
            "scenario_type": scenario_type.value,
            "fields": SUPPORTED_MAPPING_FIELDS,
            "left": {
                "file_name": left_file_name,
                **left_preview,
            },
            "right": {
                "file_name": right_file_name,
                **right_preview,
            },
            "suggestions": suggestions_payload["suggestions"],
            "llm_response": suggestions_payload["llm_response"],
        }

    def reconcile_with_mapping(
        self,
        db: Session,
        scenario_type: ScenarioType,
        created_by: str,
        left_label: str,
        right_label: str,
        left_file_path: str,
        right_file_path: str,
        mapping_payload: dict[str, Any] | list[dict[str, Any]],
    ) -> dict[str, Any]:
        left_df = self.mapping_service.read_tabular_file(left_file_path)
        right_df = self.mapping_service.read_tabular_file(right_file_path)

        left_columns = [str(c) for c in left_df.columns]
        right_columns = [str(c) for c in right_df.columns]

        mapping_items = self.mapping_service.normalize_mapping_payload(
            mapping_payload, left_columns, right_columns
        )
        mapping_issues = self.mapping_service.mapping_level_issues(mapping_items)
        if mapping_issues:
            return {
                "status": "mapping_failed",
                "mapping_issues": mapping_issues,
                "matches": [],
                "exceptions": [],
                "discrepancies": [],
                "metrics": {},
            }

        batch_id = str(uuid4())
        left_mapping = self._build_mapping_index(mapping_items, "left_column")
        right_mapping = self._build_mapping_index(mapping_items, "right_column")

        inserted_counts = {"left": 0, "right": 0}
        all_dates: list[date] = []

        side_payload = [
            ("A", "mapped_left", left_label, left_df, left_mapping, "left"),
            ("B", "mapped_right", right_label, right_df, right_mapping, "right"),
        ]

        for (
            side,
            source_type,
            source_system,
            frame,
            mapping_index,
            side_name,
        ) in side_payload:
            for idx, row in frame.iterrows():
                normalize_payload, mapped_fields = self._build_normalize_payload(
                    row, mapping_index
                )
                source_row = {
                    str(c): IngestionService._json_safe(row.get(c))
                    for c in frame.columns
                }

                raw_payload = {
                    **normalize_payload,
                    "mapped_fields": mapped_fields,
                    "source_row": source_row,
                }

                raw = TransactionRaw(
                    ingestion_batch_id=batch_id,
                    source_type=source_type,
                    source_system=source_system,
                    scenario_type=scenario_type,
                    file_name=None,
                    row_number=int(idx) + 1,
                    raw_payload=raw_payload,
                    parse_status="parsed",
                    parser_name="MappedColumnParser",
                )
                db.add(raw)
                db.flush()

                try:
                    norm = normalize_record(
                        raw=normalize_payload,
                        scenario_type=scenario_type,
                        source_type=source_type,
                        source_system=source_system,
                        raw_transaction_id=raw.id,
                        side=side,
                        llm_client=self.llm_client,
                    )
                    norm_data = norm.model_dump()
                    metadata = norm_data.get("metadata_json") or {}
                    metadata.update(
                        {
                            "mapped_fields": mapped_fields,
                            "source_label": source_system,
                            "ingestion_batch_id": batch_id,
                            "row_number": int(idx) + 1,
                        }
                    )
                    norm_data["metadata_json"] = metadata

                    db.add(TransactionNormalized(**norm_data))
                    inserted_counts[side_name] += 1
                    all_dates.append(norm.transaction_date)
                except Exception as exc:
                    raw.parse_status = "mapping_error"
                    raw.raw_payload = {
                        **raw_payload,
                        "mapping_error": str(exc),
                    }
                    mapping_issues.append(
                        {
                            "scope": "row",
                            "severity": "error",
                            "side": side_name,
                            "row_number": int(idx) + 1,
                            "message": str(exc),
                        }
                    )

        db.commit()

        if inserted_counts["left"] == 0 or inserted_counts["right"] == 0:
            return {
                "status": "mapping_failed",
                "mapping_issues": mapping_issues
                + [
                    {
                        "scope": "mapping",
                        "severity": "error",
                        "side": "left",
                        "field": "amount",
                        "message": "No valid normalized rows available for one or both sides",
                    }
                ],
                "matches": [],
                "exceptions": [],
                "discrepancies": [],
                "metrics": {},
            }

        period_start = min(all_dates)
        period_end = max(all_dates)

        job = self.recon_service.create_job(
            db,
            JobCreateRequest(
                scenario_type=scenario_type,
                period_start=period_start,
                period_end=period_end,
                filters={"ingestion_batch_id": batch_id, "reconciliation_mode": "llm"},
                created_by=created_by,
            ),
        )
        self._run_llm_reconciliation(
            db=db,
            job_id=job.id,
            scenario_type=scenario_type,
            ingestion_batch_id=batch_id,
        )
        job = db.query(ReconciliationJob).filter(ReconciliationJob.id == job.id).first()
        results = self.recon_service.job_results(db, job.id)

        # Include unmatched-side context for diff-style discrepancy review in the UI.
        exception_ids = [item["txn"] for item in results.get("exceptions", [])]
        exception_map: dict[str, dict[str, Any]] = {}
        if exception_ids:
            txns = (
                db.query(TransactionNormalized)
                .filter(TransactionNormalized.id.in_(exception_ids))
                .all()
            )
            raws = (
                db.query(TransactionRaw)
                .filter(TransactionRaw.id.in_([t.raw_transaction_id for t in txns]))
                .all()
            )
            raw_by_id = {raw.id: raw for raw in raws}
            for txn in txns:
                raw = raw_by_id.get(txn.raw_transaction_id)
                exception_map[txn.id] = {
                    "transaction_id": txn.id,
                    "side": txn.side,
                    "amount": str(txn.amount),
                    "transaction_date": str(txn.transaction_date),
                    "currency": txn.currency,
                    "reference": txn.reference_number,
                    "counterparty": txn.counterparty_normalized,
                    "mapped_snapshot": (raw.raw_payload or {}).get("mapped_fields", {})
                    if raw
                    else {},
                }

        enriched_exceptions: list[dict[str, Any]] = []
        for exception in results.get("exceptions", []):
            enriched_exceptions.append(
                {
                    **exception,
                    "transaction": exception_map.get(exception["txn"]),
                }
            )

        return {
            "status": job.status.value,
            "ingestion_batch_id": batch_id,
            "job_id": job.id,
            "period_start": str(period_start),
            "period_end": str(period_end),
            "left_file": {
                "label": left_label,
                "rows": int(len(left_df.index)),
                "valid_rows": inserted_counts["left"],
            },
            "right_file": {
                "label": right_label,
                "rows": int(len(right_df.index)),
                "valid_rows": inserted_counts["right"],
            },
            "mapping_used": mapping_items,
            "mapping_issues": mapping_issues,
            "metrics": results.get("metrics", {}),
            "matches": results.get("matches", []),
            "exceptions": enriched_exceptions,
            "exception_buckets": results.get("exception_buckets", {}),
            "reconciliation_engine": "llm",
            "discrepancies": self._build_discrepancies(db, job.id),
        }
