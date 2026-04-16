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
    build_exception_bucket_classification_prompt,
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
from app.services.normalization_service import bulk_enrich_records, normalize_record
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

RECON_BUCKET_SPECS: dict[str, dict[str, Any]] = {
    "bank_deposits_in_transit": {
        "label": "Add Deposits In Transit",
        "summary_side": "bank_statement",
        "operation": "add",
        "journal_required": False,
    },
    "bank_outstanding_cheques": {
        "label": "Deduct Outstanding Cheques",
        "summary_side": "bank_statement",
        "operation": "deduct",
        "journal_required": False,
    },
    "bank_errors": {
        "label": "Add/Deduct Bank Errors",
        "summary_side": "bank_statement",
        "operation": "variable",
        "journal_required": False,
    },
    "cash_missing_receipts": {
        "label": "Add Missing Receipts",
        "summary_side": "cash_book",
        "operation": "add",
        "journal_required": True,
    },
    "cash_interest_received": {
        "label": "Add Interest Received",
        "summary_side": "cash_book",
        "operation": "add",
        "journal_required": True,
    },
    "cash_bank_fees": {
        "label": "Deduct Bank Fees",
        "summary_side": "cash_book",
        "operation": "deduct",
        "journal_required": True,
    },
    "cash_bounced_cheques": {
        "label": "Deduct Bounced Cheques",
        "summary_side": "cash_book",
        "operation": "deduct",
        "journal_required": True,
    },
    "cash_book_errors": {
        "label": "Add/Deduct Errors In Cash Book",
        "summary_side": "cash_book",
        "operation": "variable",
        "journal_required": True,
    },
    "uncategorized": {
        "label": "Uncategorized",
        "summary_side": None,
        "operation": "none",
        "journal_required": False,
    },
}

BALANCE_COLUMN_HINTS = ["closing balance", "balance", "closing", "bal"]


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

        llm_response: Any = None
        try:
            llm_response = self.llm_client.complete_json(prompt)
        except Exception as exc:
            print("Column mapping LLM call failed.")
            print("Prompt sent to LLM:")
            print(prompt)
            print("LLM output received before failure:")
            print(llm_response)
            print(f"Error while parsing column mapping response: {exc}")
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
        left_columns: list[str] | None = None,
        right_columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        by_field = {item["field"]: item for item in mapping_items}

        issues: list[dict[str, Any]] = []
        for side_key in ("left_column", "right_column"):
            side_name = "left" if side_key == "left_column" else "right"
            source_columns = left_columns if side_key == "left_column" else right_columns
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
            has_debit = bool(by_field["debit"].get(side_key))
            has_credit = bool(by_field["credit"].get(side_key))
            has_debit_credit = bool(
                by_field["debit"].get(side_key) or by_field["credit"].get(side_key)
            )

            if has_debit ^ has_credit:
                has_debit_candidate = False
                has_credit_candidate = False
                if source_columns:
                    has_debit_candidate = (
                        ColumnMappingService._pick_best_column(
                            source_columns,
                            FIELD_ALIASES.get("debit", ["debit"]),
                        )
                        is not None
                    )
                    has_credit_candidate = (
                        ColumnMappingService._pick_best_column(
                            source_columns,
                            FIELD_ALIASES.get("credit", ["credit"]),
                        )
                        is not None
                    )

                if has_debit_candidate and has_credit_candidate:
                    issues.append(
                        {
                            "scope": "mapping",
                            "severity": "error",
                            "side": side_name,
                            "field": "debit_credit",
                            "message": (
                                f"{side_name.capitalize()} file appears to have both debit and credit columns; "
                                "map both debit and credit or use amount for this side"
                            ),
                        }
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

            if has_amount and has_debit_credit:
                issues.append(
                    {
                        "scope": "mapping",
                        "severity": "warning",
                        "side": side_name,
                        "field": "amount",
                        "message": (
                            f"{side_name.capitalize()} maps both Amount and Debit/Credit; "
                            "system will prioritize Debit/Credit for signed normalization"
                        ),
                    }
                )

        return issues


class MappedReconciliationService:
    def __init__(self, llm_client: LLMClient | None = None):
        self.settings = get_settings()
        self.llm_client = llm_client or _get_llm_client()
        self.mapping_service = ColumnMappingService(self.llm_client)
        self.recon_service = ReconciliationService(llm_client=self.llm_client)
        self.llm_reconciliation_batch_size = max(
            1,
            int(getattr(self.settings, "llm_reconciliation_batch_size", 100)),
        )
        self.llm_reconciliation_side_batch_size = max(
            1,
            self.llm_reconciliation_batch_size // 2,
        )
        self.llm_normalization_batch_size = max(
            1,
            int(
                getattr(
                    self.settings,
                    "llm_normalization_batch_size",
                    self.llm_reconciliation_batch_size,
                )
            ),
        )
        self.llm_row_enrichment_enabled = bool(
            getattr(self.settings, "llm_row_enrichment_enabled", False)
        )

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

        debit_value = mapped_fields.get("debit")
        credit_value = mapped_fields.get("credit")
        has_debit_value = not ColumnMappingService._is_missing(debit_value)
        has_credit_value = not ColumnMappingService._is_missing(credit_value)
        amount_value = (
            None
            if has_debit_value and has_credit_value
            else mapped_fields.get("amount")
        )

        normalize_payload = {
            "txn_date": mapped_fields.get("transaction_date"),
            "value_date": mapped_fields.get("value_date"),
            "description": mapped_fields.get("description"),
            "amount": amount_value,
            "debit": debit_value,
            "credit": credit_value,
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
    def _token_set(text: Any) -> set[str]:
        if text is None:
            return set()
        tokens = re.findall(r"[a-z0-9]+", str(text).lower())
        return {token for token in tokens if len(token) > 2}

    @classmethod
    def _best_deterministic_candidate(
        cls,
        left_txn: TransactionNormalized,
        right_candidates: list[TransactionNormalized],
        used_right_ids: set[str],
    ) -> dict[str, Any] | None:
        best_candidate: dict[str, Any] | None = None

        left_ref = str(left_txn.reference_number or "").strip().lower()
        left_cp = str(left_txn.counterparty_normalized or "").strip().lower()
        left_tokens = cls._token_set(left_txn.description_clean)

        for right_txn in right_candidates:
            if right_txn.id in used_right_ids:
                continue

            if str(left_txn.currency or "").upper() != str(right_txn.currency or "").upper():
                continue

            amount_delta = abs(
                Decimal(str(left_txn.amount)) - Decimal(str(right_txn.amount))
            )
            amount_base = max(
                abs(Decimal(str(left_txn.amount))),
                abs(Decimal(str(right_txn.amount))),
                Decimal("1"),
            )
            amount_ratio = float(amount_delta / amount_base)

            date_delta_days = abs(
                (left_txn.transaction_date - right_txn.transaction_date).days
            )

            right_ref = str(right_txn.reference_number or "").strip().lower()
            right_cp = str(right_txn.counterparty_normalized or "").strip().lower()
            right_tokens = cls._token_set(right_txn.description_clean)

            ref_exact = bool(left_ref and right_ref and left_ref == right_ref)
            ref_partial = bool(
                left_ref
                and right_ref
                and (
                    left_ref in right_ref
                    or right_ref in left_ref
                    or left_ref.split("-")[-1] == right_ref.split("-")[-1]
                )
            )
            cp_exact = bool(left_cp and right_cp and left_cp == right_cp)
            desc_overlap = len(left_tokens & right_tokens)

            qualifies = (
                (ref_exact and date_delta_days <= 10 and amount_ratio <= 0.05)
                or (
                    amount_ratio <= 0.005
                    and date_delta_days <= 7
                    and (cp_exact or desc_overlap > 0 or ref_partial)
                )
                or (amount_ratio <= 0.001 and date_delta_days <= 2)
            )
            if not qualifies:
                continue

            rank = (
                0 if ref_exact else 1,
                0 if cp_exact else 1,
                0 if ref_partial else 1,
                round(amount_ratio, 8),
                date_delta_days,
                -desc_overlap,
                str(right_txn.id or ""),
            )

            confidence = min(
                0.79,
                max(
                    0.65,
                    0.62
                    + (0.14 if ref_exact else 0)
                    + (0.06 if ref_partial else 0)
                    + (0.08 if cp_exact else 0)
                    + min(0.08, 0.02 * desc_overlap)
                    + max(0.0, 0.06 - min(0.06, amount_ratio * 1.5))
                    + max(0.0, 0.04 - min(0.04, date_delta_days / 100.0)),
                ),
            )

            reason_parts = [
                "Deterministic fallback",
                f"amount_delta={amount_delta}",
                f"date_delta={date_delta_days}d",
            ]
            if ref_exact:
                reason_parts.append("reference_exact")
            elif ref_partial:
                reason_parts.append("reference_partial")
            if cp_exact:
                reason_parts.append("counterparty_exact")
            if desc_overlap > 0:
                reason_parts.append(f"desc_overlap={desc_overlap}")

            candidate = {
                "rank": rank,
                "right_txn": right_txn,
                "amount_delta": amount_delta,
                "date_delta_days": date_delta_days,
                "confidence": round(confidence, 4),
                "reason": ", ".join(reason_parts),
            }

            if best_candidate is None or candidate["rank"] < best_candidate["rank"]:
                best_candidate = candidate

        return best_candidate

    @staticmethod
    def _dict_items(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _chunk_transactions(
        transactions: list[TransactionNormalized], chunk_size: int
    ) -> list[list[TransactionNormalized]]:
        if chunk_size <= 0:
            chunk_size = 1
        return [
            transactions[i : i + chunk_size]
            for i in range(0, len(transactions), chunk_size)
        ]

    @classmethod
    def _normalize_llm_reconciliation_payload(
        cls, payload: Any
    ) -> dict[str, list[dict[str, Any]]]:
        if not isinstance(payload, dict):
            return {
                "matches": [],
                "unmatched_left": [],
                "unmatched_right": [],
            }

        return {
            "matches": cls._dict_items(payload.get("matches")),
            "unmatched_left": cls._dict_items(payload.get("unmatched_left")),
            "unmatched_right": cls._dict_items(payload.get("unmatched_right")),
        }

    @staticmethod
    def _extract_match_ids(item: dict[str, Any]) -> tuple[str, str]:
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

    @staticmethod
    def _normalize_exception_bucket_payload(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            items = payload.get("classified_exceptions")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    @staticmethod
    def _parse_decimal_like(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))

        text = str(value).strip()
        if not text:
            return Decimal("0")

        negative = False
        if text.startswith("(") and text.endswith(")"):
            negative = True
            text = text[1:-1]

        text = text.replace(",", "")
        cleaned = re.sub(r"[^0-9.\-]", "", text)
        if cleaned in {"", ".", "-", "-."}:
            return Decimal("0")

        try:
            parsed = Decimal(cleaned)
            return -abs(parsed) if negative else parsed
        except Exception:
            return Decimal("0")

    @classmethod
    def _extract_unadjusted_closing_balance(cls, frame: pd.DataFrame) -> Decimal:
        if frame is None or frame.empty:
            return Decimal("0")

        candidates: list[str] = []
        for column in frame.columns:
            col_text = str(column).strip().lower()
            if any(hint in col_text for hint in BALANCE_COLUMN_HINTS):
                candidates.append(str(column))

        for column in candidates:
            series = frame[column]
            for idx in range(len(series) - 1, -1, -1):
                value = series.iloc[idx]
                if ColumnMappingService._is_missing(value):
                    continue
                parsed = cls._parse_decimal_like(value)
                if parsed != Decimal("0"):
                    return parsed

        return Decimal("0")

    @staticmethod
    def _resolve_bucket_operation(
        default_operation: str,
        direction: str | None,
    ) -> str:
        if default_operation in {"add", "deduct", "none"}:
            return default_operation
        if default_operation != "variable":
            return "none"

        direction_text = str(direction or "").strip().lower()
        if direction_text in {"in", "credit", "cr", "c"}:
            return "add"
        if direction_text in {"out", "debit", "dr", "d"}:
            return "deduct"
        return "none"

    @classmethod
    def _signed_amount(cls, amount: Decimal, operation: str) -> Decimal:
        if operation == "add":
            return abs(amount)
        if operation == "deduct":
            return -abs(amount)
        return Decimal("0")

    def _classify_exceptions(
        self,
        left_label: str,
        right_label: str,
        exceptions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not exceptions:
            return []

        llm_input: list[dict[str, Any]] = []
        by_exception_id: dict[str, dict[str, Any]] = {}

        for item in exceptions:
            exception_id = str(item.get("id") or "").strip()
            if not exception_id:
                continue
            transaction = item.get("transaction") or {}
            llm_input.append(
                {
                    "exception_id": exception_id,
                    "transaction_id": str(item.get("txn") or ""),
                    "side": str(transaction.get("side") or ""),
                    "amount": str(transaction.get("amount") or "0"),
                    "currency": str(transaction.get("currency") or ""),
                    "direction": str(transaction.get("direction") or ""),
                    "reference": str(transaction.get("reference") or ""),
                    "counterparty": str(transaction.get("counterparty") or ""),
                    "description": str(transaction.get("description") or ""),
                    "reason": str(item.get("reason") or ""),
                    "reason_detail": str(item.get("reason_detail") or ""),
                    "recommended_action": str(item.get("recommended_action") or ""),
                }
            )
            by_exception_id[exception_id] = item

        prompt = build_exception_bucket_classification_prompt(
            left_label=left_label,
            right_label=right_label,
            exceptions=llm_input,
        )

        llm_response: Any = None
        try:
            llm_response = self.llm_client.complete_json(prompt)
        except Exception as exc:
            print("Exception bucket classification LLM call failed.")
            print("Prompt sent to LLM:")
            print(prompt)
            print("LLM output received before failure:")
            print(llm_response)
            print(f"Error while parsing exception bucket response: {exc}")
            llm_response = {}

        llm_by_exception_id: dict[str, dict[str, Any]] = {}
        for row in self._normalize_exception_bucket_payload(llm_response):
            exception_id = str(row.get("exception_id") or "").strip()
            if exception_id:
                llm_by_exception_id[exception_id] = row

        classified: list[dict[str, Any]] = []
        for item in llm_input:
            exception_id = item["exception_id"]
            original = by_exception_id[exception_id]
            transaction = original.get("transaction") or {}
            side = str(transaction.get("side") or "").upper()
            direction = str(transaction.get("direction") or "")
            amount = self._parse_decimal_like(transaction.get("amount"))

            llm_item = llm_by_exception_id.get(exception_id, {})
            bucket_key = str(llm_item.get("bucket_key") or "uncategorized").strip()
            if bucket_key not in RECON_BUCKET_SPECS:
                bucket_key = "uncategorized"

            if side == "A" and bucket_key.startswith("cash_"):
                bucket_key = "uncategorized"
            if side == "B" and bucket_key.startswith("bank_"):
                bucket_key = "uncategorized"

            bucket_spec = RECON_BUCKET_SPECS[bucket_key]
            operation = self._resolve_bucket_operation(
                str(bucket_spec["operation"]),
                direction,
            )
            signed_amount = self._signed_amount(amount, operation)
            confidence = self._confidence(llm_item.get("confidence"), default_value=0.0)

            classified.append(
                {
                    "exception_id": exception_id,
                    "transaction_id": str(original.get("txn") or ""),
                    "side": side,
                    "bucket_key": bucket_key,
                    "bucket_label": str(bucket_spec["label"]),
                    "summary_side": bucket_spec["summary_side"],
                    "operation": operation,
                    "amount": str(abs(amount)),
                    "signed_amount": str(signed_amount),
                    "direction": direction,
                    "confidence": confidence,
                    "rationale": str(
                        llm_item.get("rationale")
                        or "No reliable classification evidence from model output"
                    ),
                    "journal_required": bool(bucket_spec["journal_required"]),
                }
            )

        return classified

    @classmethod
    def _build_reconciliation_summary(
        cls,
        left_df: pd.DataFrame,
        right_df: pd.DataFrame,
        classified_exceptions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        unadjusted_bank = cls._extract_unadjusted_closing_balance(left_df)
        unadjusted_cash = cls._extract_unadjusted_closing_balance(right_df)

        bucket_totals: dict[str, dict[str, Any]] = {}
        for key, spec in RECON_BUCKET_SPECS.items():
            if key == "uncategorized":
                continue
            bucket_totals[key] = {
                "bucket_key": key,
                "bucket_label": spec["label"],
                "summary_side": spec["summary_side"],
                "operation": spec["operation"],
                "amount_total": Decimal("0"),
                "signed_total": Decimal("0"),
                "count": 0,
            }

        for row in classified_exceptions:
            bucket_key = str(row.get("bucket_key") or "")
            if bucket_key not in bucket_totals:
                continue
            amount = cls._parse_decimal_like(row.get("amount"))
            signed_amount = cls._parse_decimal_like(row.get("signed_amount"))
            bucket_totals[bucket_key]["amount_total"] += abs(amount)
            bucket_totals[bucket_key]["signed_total"] += signed_amount
            bucket_totals[bucket_key]["count"] += 1

        bank_adjustments = [
            {
                "bucket_key": row["bucket_key"],
                "label": row["bucket_label"],
                "operation": cls._resolve_bucket_operation(
                    str(row["operation"]),
                    None,
                ),
                "amount": str(row["amount_total"]),
                "count": row["count"],
                "signed_amount": str(row["signed_total"]),
            }
            for row in bucket_totals.values()
            if row["summary_side"] == "bank_statement"
        ]
        cash_adjustments = [
            {
                "bucket_key": row["bucket_key"],
                "label": row["bucket_label"],
                "operation": cls._resolve_bucket_operation(
                    str(row["operation"]),
                    None,
                ),
                "amount": str(row["amount_total"]),
                "count": row["count"],
                "signed_amount": str(row["signed_total"]),
            }
            for row in bucket_totals.values()
            if row["summary_side"] == "cash_book"
        ]

        bank_signed_total = sum(
            (cls._parse_decimal_like(item["signed_amount"]) for item in bank_adjustments),
            Decimal("0"),
        )
        cash_signed_total = sum(
            (cls._parse_decimal_like(item["signed_amount"]) for item in cash_adjustments),
            Decimal("0"),
        )

        adjusted_bank = unadjusted_bank + bank_signed_total
        adjusted_cash = unadjusted_cash + cash_signed_total
        unreconciled = abs(adjusted_bank - adjusted_cash)

        return {
            "bank_statement": {
                "unadjusted_closing_balance": str(unadjusted_bank),
                "adjustments": bank_adjustments,
                "adjusted_closing_balance": str(adjusted_bank),
            },
            "cash_book": {
                "unadjusted_closing_balance": str(unadjusted_cash),
                "adjustments": cash_adjustments,
                "adjusted_closing_balance": str(adjusted_cash),
            },
            "unreconciled_amount": str(unreconciled),
            "classification_count": len(classified_exceptions),
            "calculation_notes": [
                "Adjusted side balance = unadjusted balance + sum(additions) - sum(deductions)",
                "Unreconciled amount = absolute difference between adjusted side balances",
            ],
        }

    @classmethod
    def _build_journal_entries(
        cls,
        classified_exceptions: list[dict[str, Any]],
        period_end: date,
    ) -> list[dict[str, Any]]:
        account_rules = {
            "cash_missing_receipts": ("Cash", "Accounts Receivable"),
            "cash_interest_received": ("Cash", "Interest Income"),
            "cash_bank_fees": ("Bank Fees Expense", "Cash"),
            "cash_bounced_cheques": ("Accounts Receivable", "Cash"),
        }

        entries: list[dict[str, Any]] = []
        for idx, row in enumerate(classified_exceptions, start=1):
            if not row.get("journal_required"):
                continue

            bucket_key = str(row.get("bucket_key") or "")
            amount = abs(cls._parse_decimal_like(row.get("amount")))
            if amount <= Decimal("0"):
                continue

            debit_account = ""
            credit_account = ""
            operation = str(row.get("operation") or "none")

            if bucket_key in account_rules:
                debit_account, credit_account = account_rules[bucket_key]
            elif bucket_key == "cash_book_errors":
                if operation == "add":
                    debit_account, credit_account = (
                        "Cash",
                        "Suspense - Cash Book Error",
                    )
                elif operation == "deduct":
                    debit_account, credit_account = (
                        "Suspense - Cash Book Error",
                        "Cash",
                    )

            if not debit_account or not credit_account:
                continue

            entries.append(
                {
                    "entry_id": f"JE-{idx:04d}",
                    "entry_date": str(period_end),
                    "bucket_key": bucket_key,
                    "narration": str(
                        row.get("rationale")
                        or "Reconciliation adjustment entry"
                    ),
                    "debit_account": debit_account,
                    "credit_account": credit_account,
                    "amount": str(amount),
                    "source_exception_ids": [str(row.get("exception_id") or "")],
                }
            )

        return entries

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

            def _sort_key(txn: TransactionNormalized) -> tuple[Any, ...]:
                metadata = txn.metadata_json if isinstance(txn.metadata_json, dict) else {}
                row_number_raw = metadata.get("row_number")
                try:
                    row_number = int(row_number_raw)
                except (TypeError, ValueError):
                    row_number = 10**9

                return (
                    txn.transaction_date,
                    Decimal(str(txn.amount)),
                    str(txn.currency or ""),
                    str(txn.reference_number or ""),
                    str(txn.description_clean or ""),
                    str(txn.counterparty_normalized or ""),
                    row_number,
                    str(txn.id or ""),
                )

            side_a.sort(
                key=_sort_key
            )
            side_b.sort(
                key=_sort_key
            )
            side_a_by_id = {txn.id: txn for txn in side_a}
            side_b_by_id = {txn.id: txn for txn in side_b}
            matched_left_ids: set[str] = set()
            matched_right_ids: set[str] = set()
            persisted_matches: list[Match] = []
            unmatched_left_reasons: dict[str, str] = {}
            unmatched_right_reasons: dict[str, str] = {}

            left_chunks = self._chunk_transactions(
                side_a, self.llm_reconciliation_side_batch_size
            )
            for left_batch in left_chunks:

                left_batch = [
                    txn for txn in left_batch if txn.id not in matched_left_ids
                ]

                if not left_batch:
                    continue

                right_pool = [
                    txn for txn in side_b if txn.id not in matched_right_ids
                ]

                if not right_pool:
                    for txn in left_batch:
                        unmatched_left_reasons.setdefault(
                            txn.id,
                            "No right-side counterpart in this reconciliation batch",
                        )
                    continue

                def _right_rank(right_txn: TransactionNormalized) -> tuple[Any, ...]:
                    best_rank: tuple[Any, ...] | None = None
                    for left_txn in left_batch:
                        currency_mismatch = (
                            str(left_txn.currency or "").upper()
                            != str(right_txn.currency or "").upper()
                        )
                        currency_penalty = 1 if currency_mismatch else 0
                        date_delta = abs(
                            (left_txn.transaction_date - right_txn.transaction_date).days
                        )
                        amount_delta = abs(
                            Decimal(str(left_txn.amount))
                            - Decimal(str(right_txn.amount))
                        )
                        rank = (
                            currency_penalty,
                            date_delta,
                            amount_delta,
                            str(right_txn.reference_number or ""),
                            str(right_txn.id or ""),
                        )
                        if best_rank is None or rank < best_rank:
                            best_rank = rank

                    if best_rank is None:
                        return (1, 9999, Decimal("9999999"), "", str(right_txn.id or ""))
                    return best_rank

                right_batch = sorted(right_pool, key=_right_rank)[
                    : max(1, self.llm_reconciliation_batch_size - len(left_batch))
                ]

                if not right_batch:
                    for txn in left_batch:
                        unmatched_left_reasons.setdefault(
                            txn.id,
                            "No right-side candidates available in this reconciliation batch",
                        )
                    continue

                llm_prompt = build_llm_reconciliation_prompt(
                    scenario_type=scenario_type.value,
                    left_transactions=[
                        self._llm_transaction_payload(txn) for txn in left_batch
                    ],
                    right_transactions=[
                        self._llm_transaction_payload(txn) for txn in right_batch
                    ],
                )

                llm_response: Any = None
                try:
                    llm_response = self.llm_client.complete_json(llm_prompt)
                    parsed_response = self._normalize_llm_reconciliation_payload(
                        llm_response
                    )
                except Exception as exc:
                    print("LLM reconciliation batch failed.")
                    print("Prompt sent to LLM:")
                    print(llm_prompt)
                    print("LLM output received before failure:")
                    print(llm_response)
                    print(f"Error while parsing reconciliation response: {exc}")
                    parsed_response = {
                        "matches": [],
                        "unmatched_left": [
                            {
                                "transaction_id": txn.id,
                                "reason": "LLM did not return valid JSON for this batch",
                            }
                            for txn in left_batch
                        ],
                        "unmatched_right": [
                            {
                                "transaction_id": txn.id,
                                "reason": "LLM did not return valid JSON for this batch",
                            }
                            for txn in right_batch
                        ],
                    }

                for txn_id, reason in self._reason_by_transaction(
                    parsed_response.get("unmatched_left")
                ).items():
                    if txn_id in side_a_by_id:
                        unmatched_left_reasons[txn_id] = reason

                for txn_id, reason in self._reason_by_transaction(
                    parsed_response.get("unmatched_right")
                ).items():
                    if txn_id in side_b_by_id:
                        unmatched_right_reasons[txn_id] = reason

                for item in parsed_response.get("matches", []):
                    left_id, right_id = self._extract_match_ids(item)

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
                            item.get("reason")
                            or "LLM semantic reconciliation decision"
                        ),
                    )
                    db.add(match_record)
                    persisted_matches.append(match_record)

                    matched_left_ids.add(left_id)
                    matched_right_ids.add(right_id)

                # Deterministic safety net when strict LLM output returns sparse/empty matches.
                unmatched_left_in_batch = [
                    txn for txn in left_batch if txn.id not in matched_left_ids
                ]
                available_right_in_batch = [
                    txn for txn in right_batch if txn.id not in matched_right_ids
                ]

                for left_txn in unmatched_left_in_batch:
                    candidate = self._best_deterministic_candidate(
                        left_txn=left_txn,
                        right_candidates=available_right_in_batch,
                        used_right_ids=matched_right_ids,
                    )
                    if not candidate:
                        continue

                    best_right = candidate["right_txn"]
                    fallback_match = Match(
                        reconciliation_job_id=job.id,
                        transaction_a_id=left_txn.id,
                        transaction_b_id=best_right.id,
                        match_type=MatchType.ONE_TO_ONE,
                        confidence_score=Decimal(str(candidate["confidence"])),
                        algorithm_used="heuristic_batch_fallback",
                        amount_delta=candidate["amount_delta"],
                        date_delta_days=candidate["date_delta_days"],
                        auto_accepted=False,
                        llm_reason=str(candidate["reason"]),
                    )
                    db.add(fallback_match)
                    persisted_matches.append(fallback_match)
                    matched_left_ids.add(left_txn.id)
                    matched_right_ids.add(best_right.id)

            # Global deterministic pass for cross-batch candidates that may be missed by local batches.
            remaining_left = [txn for txn in side_a if txn.id not in matched_left_ids]
            remaining_right = [txn for txn in side_b if txn.id not in matched_right_ids]

            for left_txn in remaining_left:
                candidate = self._best_deterministic_candidate(
                    left_txn=left_txn,
                    right_candidates=remaining_right,
                    used_right_ids=matched_right_ids,
                )
                if not candidate:
                    continue

                best_right = candidate["right_txn"]
                global_fallback_match = Match(
                    reconciliation_job_id=job.id,
                    transaction_a_id=left_txn.id,
                    transaction_b_id=best_right.id,
                    match_type=MatchType.ONE_TO_ONE,
                    confidence_score=Decimal(str(candidate["confidence"])),
                    algorithm_used="heuristic_global_fallback",
                    amount_delta=candidate["amount_delta"],
                    date_delta_days=candidate["date_delta_days"],
                    auto_accepted=False,
                    llm_reason=str(candidate["reason"]),
                )
                db.add(global_fallback_match)
                persisted_matches.append(global_fallback_match)
                matched_left_ids.add(left_txn.id)
                matched_right_ids.add(best_right.id)

            unmatched_left_ids = set(side_a_by_id.keys()) - matched_left_ids
            unmatched_right_ids = set(side_b_by_id.keys()) - matched_right_ids

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
        mapping_issues = self.mapping_service.mapping_level_issues(
            mapping_items,
            left_columns=left_columns,
            right_columns=right_columns,
        )
        if mapping_issues:
            return {
                "status": "mapping_failed",
                "mapping_issues": mapping_issues,
                "matches": [],
                "exceptions": [],
                "discrepancies": [],
                "metrics": {},
                "classified_exceptions": [],
                "reconciliation_summary": {},
                "journal_entries": [],
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
            pending_rows: list[dict[str, Any]] = []

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

                pending_rows.append(
                    {
                        "row_number": int(idx) + 1,
                        "raw": raw,
                        "raw_payload": raw_payload,
                        "normalize_payload": normalize_payload,
                        "mapped_fields": mapped_fields,
                    }
                )

            enrichment_by_id: dict[str, dict[str, Any]] = {}
            if self.llm_row_enrichment_enabled and pending_rows:
                enrichment_by_id = bulk_enrich_records(
                    records=[
                        {
                            "raw_transaction_id": pending["raw"].id,
                            "scenario_type": scenario_type,
                            "description": pending["normalize_payload"].get("description"),
                            "counterparty": pending["normalize_payload"].get("counterparty"),
                            "reference": pending["normalize_payload"].get("reference"),
                            "invoice_ref": pending["normalize_payload"].get("invoice_ref"),
                        }
                        for pending in pending_rows
                    ],
                    llm_client=self.llm_client,
                    batch_size=self.llm_normalization_batch_size,
                )

            for pending in pending_rows:
                row_number = pending["row_number"]
                raw = pending["raw"]
                raw_payload = pending["raw_payload"]
                normalize_payload = pending["normalize_payload"]
                mapped_fields = pending["mapped_fields"]

                try:
                    norm = normalize_record(
                        raw=normalize_payload,
                        scenario_type=scenario_type,
                        source_type=source_type,
                        source_system=source_system,
                        raw_transaction_id=raw.id,
                        side=side,
                        llm_client=None,
                        enrichment_override=enrichment_by_id.get(raw.id),
                    )
                    norm_data = norm.model_dump()
                    metadata = norm_data.get("metadata_json") or {}
                    metadata.update(
                        {
                            "mapped_fields": mapped_fields,
                            "source_label": source_system,
                            "ingestion_batch_id": batch_id,
                            "row_number": row_number,
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
                            "row_number": row_number,
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
                "classified_exceptions": [],
                "reconciliation_summary": {},
                "journal_entries": [],
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
                    "direction": txn.direction.value,
                    "reference": txn.reference_number,
                    "counterparty": txn.counterparty_normalized,
                    "description": txn.description_clean,
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

        classified_exceptions = self._classify_exceptions(
            left_label=left_label,
            right_label=right_label,
            exceptions=enriched_exceptions,
        )
        reconciliation_summary = self._build_reconciliation_summary(
            left_df=left_df,
            right_df=right_df,
            classified_exceptions=classified_exceptions,
        )
        journal_entries = self._build_journal_entries(
            classified_exceptions=classified_exceptions,
            period_end=period_end,
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
            "classified_exceptions": classified_exceptions,
            "reconciliation_summary": reconciliation_summary,
            "journal_entries": journal_entries,
            "reconciliation_engine": "llm",
            "discrepancies": self._build_discrepancies(db, job.id),
        }
