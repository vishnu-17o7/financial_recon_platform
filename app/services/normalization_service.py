import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from dateutil import parser as dt_parser

from app.llm.interfaces import LLMClient
from app.llm.prompt_builders import (
    build_bulk_enrichment_prompt,
    build_enrichment_prompt,
)
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


def _parse_decimal(raw_value: Any) -> Decimal:
    if raw_value is None:
        return Decimal("0")

    text = str(raw_value).strip()
    if not text:
        return Decimal("0")

    if text.lower() in {"nan", "none", "null", "nat", "<na>"}:
        return Decimal("0")

    wrapped_negative = text.startswith("(") and text.endswith(")")
    if wrapped_negative:
        text = text[1:-1]

    text = text.replace(",", "").replace(" ", "")

    try:
        value = Decimal(text)
    except Exception:
        cleaned = re.sub(r"[^0-9.\-]", "", text)
        if cleaned in {"", "-", ".", "-."}:
            return Decimal("0")
        value = Decimal(cleaned)

    if wrapped_negative:
        return -abs(value)
    return value


def _default_enrichment(counterparty: Any) -> dict[str, Any]:
    return {
        "normalized_name": counterparty,
        "transaction_type": None,
        "reference_numbers": [],
    }


def _sanitize_reference_numbers(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                result.append(text)
        return result

    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []

    return []


def _sanitize_enrichment(value: Any, counterparty: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return _default_enrichment(counterparty)

    normalized_name_raw = value.get("normalized_name")
    normalized_name = str(normalized_name_raw).strip() if normalized_name_raw else ""
    if not normalized_name:
        normalized_name = str(counterparty).strip() if counterparty else ""

    transaction_type_raw = value.get("transaction_type")
    transaction_type = (
        str(transaction_type_raw).strip() if transaction_type_raw is not None else ""
    )

    return {
        "normalized_name": normalized_name or None,
        "transaction_type": transaction_type or None,
        "reference_numbers": _sanitize_reference_numbers(value.get("reference_numbers")),
    }


def _chunk_items(items: list[Any], chunk_size: int) -> list[list[Any]]:
    safe_chunk_size = max(1, int(chunk_size or 1))
    return [items[i : i + safe_chunk_size] for i in range(0, len(items), safe_chunk_size)]


def _bulk_enrichment_items(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]

    if not isinstance(response, dict):
        return []

    for key in ("enrichments", "records", "results", "data"):
        value = response.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    # Some providers ignore the bulk contract and return a single enrichment object.
    # Accept that shape when it carries a transaction id + enrichment fields.
    has_id = any(
        response.get(key) is not None
        for key in ("raw_transaction_id", "transaction_id", "id")
    )
    has_enrichment_fields = any(
        key in response
        for key in ("normalized_name", "transaction_type", "reference_numbers")
    )
    if has_id and has_enrichment_fields:
        return [response]

    return []


def bulk_enrich_records(
    records: list[dict[str, Any]],
    llm_client: LLMClient | None = None,
    batch_size: int = 20,
) -> dict[str, dict[str, Any]]:
    enrichment_by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        raw_id = str(record.get("raw_transaction_id") or "").strip()
        if not raw_id:
            continue
        enrichment_by_id[raw_id] = _default_enrichment(record.get("counterparty"))

    if not llm_client or not enrichment_by_id:
        return enrichment_by_id

    for chunk in _chunk_items(records, max(1, int(batch_size or 20))):
        prompt_records: list[dict[str, Any]] = []
        for record in chunk:
            raw_id = str(record.get("raw_transaction_id") or "").strip()
            if not raw_id:
                continue
            scenario_value = record.get("scenario_type")
            scenario_type = (
                scenario_value.value
                if hasattr(scenario_value, "value")
                else str(scenario_value or "")
            )
            prompt_records.append(
                {
                    "raw_transaction_id": raw_id,
                    "description": record.get("description") or "",
                    "counterparty": record.get("counterparty"),
                    "reference": record.get("reference"),
                    "invoice_ref": record.get("invoice_ref"),
                    "scenario_type": scenario_type,
                }
            )

        if not prompt_records:
            continue

        prompt = build_bulk_enrichment_prompt(prompt_records)
        llm_response: Any = None
        try:
            llm_response = llm_client.complete_json(prompt)
        except Exception as exc:
            print("Bulk normalization LLM call failed.")
            print("Prompt sent to LLM:")
            print(prompt)
            print("LLM output received before failure:")
            print(llm_response)
            print(f"Error while parsing bulk normalization response: {exc}")
            continue

        items = _bulk_enrichment_items(llm_response)
        if not items:
            print("Bulk normalization response had no usable enrichment list.")
            print("Prompt sent to LLM:")
            print(prompt)
            print("LLM output received:")
            print(llm_response)
            continue

        for item in items:
            raw_id = str(
                item.get("raw_transaction_id")
                or item.get("transaction_id")
                or item.get("id")
                or ""
            ).strip()
            if raw_id not in enrichment_by_id:
                continue

            fallback_counterparty = enrichment_by_id[raw_id].get("normalized_name")
            enrichment_by_id[raw_id] = _sanitize_enrichment(
                item,
                fallback_counterparty,
            )

    return enrichment_by_id


def normalize_record(
    raw: dict[str, Any],
    scenario_type: ScenarioType,
    source_type: str,
    source_system: str,
    raw_transaction_id: str,
    side: str,
    llm_client: LLMClient | None = None,
    enrichment_override: dict[str, Any] | None = None,
) -> NormalizedTransactionIn:
    amount_raw = raw.get("amount")
    amount_text = str(amount_raw).strip() if amount_raw is not None else ""
    if amount_raw is None or amount_text.lower() in {"", "nan", "none", "null", "nat", "<na>"}:
        debit = _parse_decimal(raw.get("debit", 0) or 0)
        credit = _parse_decimal(raw.get("credit", 0) or 0)
        amount = credit - debit
    else:
        amount = _parse_decimal(amount_raw)

    date_value = raw.get("txn_date") or raw.get("posting_date") or raw.get("payment_date")
    value_date = raw.get("value_date") or raw.get("settlement_date")
    description = raw.get("description") or raw.get("narration") or ""
    counterparty = raw.get("counterparty") or raw.get("customer_name")
    reference = raw.get("reference") or raw.get("voucher_no") or raw.get("payment_id")
    invoice_ref = raw.get("invoice_ref")

    enrichment = _default_enrichment(counterparty)
    if isinstance(enrichment_override, dict):
        enrichment = _sanitize_enrichment(enrichment_override, counterparty)
    elif llm_client:
        enrichment_prompt = build_enrichment_prompt(
            {
                "description": description,
                "counterparty": counterparty,
                "reference": reference,
                "invoice_ref": invoice_ref,
                "scenario_type": scenario_type.value,
            }
        )
        llm_response: Any = None
        try:
            llm_response = llm_client.complete_json(enrichment_prompt)
            enrichment = _sanitize_enrichment(llm_response, counterparty)
        except Exception as exc:
            print("Normalization LLM call failed.")
            print("Prompt sent to LLM:")
            print(enrichment_prompt)
            print("LLM output received before failure:")
            print(llm_response)
            print(f"Error while parsing normalization response: {exc}")
            enrichment = _default_enrichment(counterparty)

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
