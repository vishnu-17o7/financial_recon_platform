import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from dateutil import parser as dt_parser

from app.llm.interfaces import LLMClient
from app.llm.prompt_builders import build_enrichment_prompt
from app.models.enums import Direction, ScenarioType
from app.schemas.common import NormalizedTransactionIn


NOISE_TOKENS = ["txn", "utr", "ref", "payment", "transfer"]


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = text.lower().strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    for token in NOISE_TOKENS:
        cleaned = cleaned.replace(token, "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_date(raw_value: Any) -> datetime.date:
    if raw_value is None:
        raise ValueError("date value missing")
    if isinstance(raw_value, datetime):
        return raw_value.date()
    return dt_parser.parse(str(raw_value)).date()


def _derive_direction(amount: Decimal, dr_cr: str | None) -> Direction:
    if dr_cr:
        v = dr_cr.lower().strip()
        if v in {"debit", "dr", "d"}:
            return Direction.OUT
        if v in {"credit", "cr", "c"}:
            return Direction.IN
    return Direction.IN if amount >= 0 else Direction.OUT


def normalize_record(
    raw: dict[str, Any],
    scenario_type: ScenarioType,
    source_type: str,
    source_system: str,
    raw_transaction_id: str,
    side: str,
    llm_client: LLMClient | None = None,
) -> NormalizedTransactionIn:
    amount_raw = raw.get("amount")
    if amount_raw is None:
        debit = Decimal(str(raw.get("debit", 0) or 0))
        credit = Decimal(str(raw.get("credit", 0) or 0))
        amount = credit - debit
    else:
        amount = Decimal(str(amount_raw))

    date_value = raw.get("txn_date") or raw.get("posting_date") or raw.get("payment_date")
    value_date = raw.get("value_date") or raw.get("settlement_date")
    description = raw.get("description") or raw.get("narration") or ""
    counterparty = raw.get("counterparty") or raw.get("customer_name")
    reference = raw.get("reference") or raw.get("voucher_no") or raw.get("payment_id")
    invoice_ref = raw.get("invoice_ref")

    enrichment = {"normalized_name": counterparty, "transaction_type": None, "reference_numbers": []}
    if llm_client:
        enrichment_prompt = build_enrichment_prompt(
            {
                "description": description,
                "counterparty": counterparty,
                "reference": reference,
                "invoice_ref": invoice_ref,
                "scenario_type": scenario_type.value,
            }
        )
        try:
            enrichment = llm_client.complete_json(enrichment_prompt)
        except Exception:
            enrichment = {"normalized_name": counterparty, "transaction_type": None, "reference_numbers": []}

    cleaned_description = _clean_text(description)
    normalized_counterparty = (enrichment.get("normalized_name") or counterparty or "").strip().lower()
    direction = _derive_direction(amount, raw.get("dr_cr"))

    return NormalizedTransactionIn(
        raw_transaction_id=raw_transaction_id,
        source_type=source_type,
        source_system=source_system,
        scenario_type=scenario_type,
        direction=direction,
        transaction_date=_parse_date(date_value),
        value_date=_parse_date(value_date) if value_date else None,
        amount=abs(amount),
        currency=(raw.get("currency") or "INR").upper(),
        description_clean=cleaned_description,
        description_raw=description,
        counterparty_raw=counterparty,
        counterparty_normalized=normalized_counterparty or None,
        reference_number=reference,
        invoice_number=invoice_ref,
        external_txn_id=raw.get("payment_id") or raw.get("external_txn_id"),
        classification=enrichment.get("transaction_type"),
        side=side,
        metadata_json={"source_account_code": raw.get("account_code")},
    )
