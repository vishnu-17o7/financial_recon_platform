import json
from typing import Any


def build_enrichment_prompt(record: dict[str, Any]) -> str:
    return (
        "You are a financial data normalizer. Return JSON only with keys: "
        "normalized_name, transaction_type, reference_numbers.\n"
        f"Record: {json.dumps(record, default=str)}"
    )


def build_tiebreak_prompt(source_txn: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    payload = {
        "task": "tie-break matching",
        "source_transaction": source_txn,
        "candidates": candidates,
        "instruction": (
            "Return JSON: recommended_match_index, suggested_confidence (0..1), "
            "reason, requires_human_review"
        ),
    }
    return json.dumps(payload, default=str)


def build_column_mapping_prompt(
    scenario_type: str,
    left_columns: list[str],
    right_columns: list[str],
    left_preview: list[dict[str, Any]],
    right_preview: list[dict[str, Any]],
    supported_fields: list[dict[str, Any]],
) -> str:
    payload = {
        "task": "column_mapping_suggestion",
        "scenario_type": scenario_type,
        "left_columns": left_columns,
        "right_columns": right_columns,
        "left_preview": left_preview,
        "right_preview": right_preview,
        "supported_fields": supported_fields,
        "instruction": (
            "Return JSON with key 'mappings'. Each mapping object must include: "
            "field, left_column, right_column, confidence (0..1), rationale."
        ),
    }
    return json.dumps(payload, default=str)


def build_llm_reconciliation_prompt(
    scenario_type: str,
    left_transactions: list[dict[str, Any]],
    right_transactions: list[dict[str, Any]],
) -> str:
    payload = {
        "task": "llm_reconciliation",
        "scenario_type": scenario_type,
        "left_transactions": left_transactions,
        "right_transactions": right_transactions,
        "instruction": (
            "Return JSON only with keys: matches, unmatched_left, unmatched_right. "
            "Each match item must include left_transaction_id, right_transaction_id, confidence (0..1), reason. "
            "Use one-to-one matching only and avoid duplicate transaction usage."
        ),
    }
    return json.dumps(payload, default=str)


def build_explanation_prompt(context: dict[str, Any], is_exception: bool) -> str:
    mode = "unreconciled exception" if is_exception else "matched item"
    return (
        f"Explain {mode} in plain language. Return JSON with explanation and actions. "
        f"Context: {json.dumps(context, default=str)}"
    )
