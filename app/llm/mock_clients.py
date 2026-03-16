import hashlib
import json
import re
from datetime import date, datetime
from typing import Any

import numpy as np

from app.config.settings import get_settings
from app.llm.interfaces import EmbeddingClient, LLMClient


class MockLLMClient(LLMClient):
    @staticmethod
    def _pick_column(columns: list[str], aliases: list[str]) -> str | None:
        normalized = [str(c) for c in columns]
        if not normalized:
            return None

        alias_set = [a.lower().strip() for a in aliases]
        best_name = None
        best_score = 0

        for name in normalized:
            name_norm = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            score = 0
            for alias in alias_set:
                if name_norm == alias:
                    score = max(score, 100)
                elif alias in name_norm:
                    score = max(score, 70)
                elif name_norm in alias:
                    score = max(score, 40)
            if score > best_score:
                best_score = score
                best_name = name

        return best_name if best_score > 0 else None

    @staticmethod
    def _as_amount(value: Any) -> float:
        try:
            return abs(float(value))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _as_date(value: Any) -> date | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return datetime.fromisoformat(text[:10]).date()
            except ValueError:
                return None

    @classmethod
    def _score_reconciliation_pair(cls, left: dict[str, Any], right: dict[str, Any]) -> tuple[float, str]:
        left_amount = cls._as_amount(left.get("amount"))
        right_amount = cls._as_amount(right.get("amount"))
        amount_delta = abs(left_amount - right_amount)
        denom = max(left_amount, right_amount, 1.0)
        amount_score = max(0.0, 1.0 - (amount_delta / denom))

        left_date = cls._as_date(left.get("transaction_date") or left.get("date"))
        right_date = cls._as_date(right.get("transaction_date") or right.get("date"))
        if left_date and right_date:
            date_delta = abs((left_date - right_date).days)
            date_score = max(0.0, 1.0 - (date_delta / 7.0))
        else:
            date_score = 0.5

        left_currency = str(left.get("currency") or "").upper()
        right_currency = str(right.get("currency") or "").upper()
        currency_bonus = 0.1 if left_currency and left_currency == right_currency else 0.0

        left_ref = str(left.get("reference") or "").strip().lower()
        right_ref = str(right.get("reference") or "").strip().lower()
        reference_bonus = 0.2 if left_ref and right_ref and left_ref == right_ref else 0.0

        left_counterparty = str(left.get("counterparty") or "").strip().lower()
        right_counterparty = str(right.get("counterparty") or "").strip().lower()
        counterparty_bonus = 0.1 if left_counterparty and right_counterparty and left_counterparty == right_counterparty else 0.0

        score = min(1.0, (0.55 * amount_score) + (0.25 * date_score) + currency_bonus + reference_bonus + counterparty_bonus)
        reason = (
            f"Amount delta={amount_delta:.2f}; date score={date_score:.2f}; "
            f"currency match={left_currency == right_currency}; reference match={left_ref == right_ref}"
        )
        return score, reason

    def complete_json(self, prompt: str) -> dict[str, Any]:
        prompt_l = prompt.lower()
        if "column_mapping_suggestion" in prompt_l:
            try:
                payload = json.loads(prompt)
                left_columns = [str(v) for v in payload.get("left_columns", [])]
                right_columns = [str(v) for v in payload.get("right_columns", [])]
                fields = payload.get("supported_fields", [])
            except Exception:
                left_columns = []
                right_columns = []
                fields = []

            alias_map = {
                "transaction_date": ["txn_date", "posting_date", "payment_date", "date", "transaction_date"],
                "value_date": ["value_date", "settlement_date", "value_dt"],
                "description": ["description", "narration", "remarks", "memo"],
                "amount": ["amount", "amt", "transaction_amount"],
                "debit": ["debit", "dr", "withdrawal"],
                "credit": ["credit", "cr", "deposit"],
                "currency": ["currency", "ccy", "curr"],
                "reference": ["reference", "voucher_no", "payment_id", "utr", "ref"],
                "counterparty": ["counterparty", "customer_name", "party", "beneficiary"],
                "direction": ["dr_cr", "direction", "flow", "type"],
                "external_txn_id": ["external_txn_id", "payment_id", "txn_id", "transaction_id"],
            }

            mappings = []
            for item in fields:
                field = str(item.get("field", "")).strip()
                aliases = alias_map.get(field, [field])
                left_match = self._pick_column(left_columns, aliases)
                right_match = self._pick_column(right_columns, aliases)
                has_match = bool(left_match or right_match)
                mappings.append(
                    {
                        "field": field,
                        "left_column": left_match,
                        "right_column": right_match,
                        "confidence": 0.84 if has_match else 0.35,
                        "rationale": (
                            "Matched by semantic column similarity"
                            if has_match
                            else "No reliable semantic match found"
                        ),
                    }
                )

            return {
                "mappings": mappings,
                "model": "mock-column-mapper",
            }

        if "llm_reconciliation" in prompt_l:
            try:
                payload = json.loads(prompt)
                left_items = [item for item in payload.get("left_transactions", []) if isinstance(item, dict)]
                right_items = [item for item in payload.get("right_transactions", []) if isinstance(item, dict)]
            except Exception:
                left_items = []
                right_items = []

            used_right_ids: set[str] = set()
            matches: list[dict[str, Any]] = []

            for left in left_items:
                left_id = str(left.get("id") or "").strip()
                if not left_id:
                    continue

                best_right: dict[str, Any] | None = None
                best_score = 0.0
                best_reason = ""

                for right in right_items:
                    right_id = str(right.get("id") or "").strip()
                    if not right_id or right_id in used_right_ids:
                        continue
                    score, reason = self._score_reconciliation_pair(left, right)
                    if score > best_score:
                        best_score = score
                        best_right = right
                        best_reason = reason

                if best_right is None:
                    continue

                right_id = str(best_right.get("id") or "").strip()
                if best_score >= 0.67:
                    used_right_ids.add(right_id)
                    matches.append(
                        {
                            "left_transaction_id": left_id,
                            "right_transaction_id": right_id,
                            "confidence": round(best_score, 4),
                            "reason": f"Mock LLM matched pair. {best_reason}",
                        }
                    )

            matched_left_ids = {item["left_transaction_id"] for item in matches}
            unmatched_left = [
                {
                    "transaction_id": str(left.get("id")),
                    "reason": "No sufficiently confident LLM candidate found",
                }
                for left in left_items
                if str(left.get("id") or "").strip() and str(left.get("id")) not in matched_left_ids
            ]
            unmatched_right = [
                {
                    "transaction_id": str(right.get("id")),
                    "reason": "No sufficiently confident LLM candidate found",
                }
                for right in right_items
                if str(right.get("id") or "").strip() and str(right.get("id")) not in used_right_ids
            ]

            return {
                "matches": matches,
                "unmatched_left": unmatched_left,
                "unmatched_right": unmatched_right,
                "model": "mock-llm-reconciliation",
            }

        if "tie-break" in prompt_l or "candidate" in prompt_l:
            return {
                "recommended_match_index": 0,
                "suggested_confidence": 0.82,
                "reason": "Top candidate has closest amount/date/reference overlap.",
                "requires_human_review": False,
            }
        if "unreconciled" in prompt_l or "exception" in prompt_l:
            return {
                "explanation": "No candidate satisfied tolerance and date constraints.",
                "actions": [
                    "Post missing entry in counterpart ledger.",
                    "Validate reference mapping and vendor/customer master.",
                ],
            }
        return {
            "normalized_name": "unknown",
            "transaction_type": "other",
            "reference_numbers": [],
        }


class MockEmbeddingClient(EmbeddingClient):
    def __init__(self) -> None:
        self.dim = get_settings().vector_dim

    def embed_text(self, text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = np.random.default_rng(seed)
        return rng.normal(0, 1, self.dim).astype(float).tolist()
