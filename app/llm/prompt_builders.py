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


def build_explanation_prompt(context: dict[str, Any], is_exception: bool) -> str:
    mode = "unreconciled exception" if is_exception else "matched item"
    return (
        f"Explain {mode} in plain language. Return JSON with explanation and actions. "
        f"Context: {json.dumps(context, default=str)}"
    )
