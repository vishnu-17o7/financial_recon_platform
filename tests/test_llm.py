import json

from app.llm.mock_clients import MockLLMClient
from app.llm.prompt_builders import (
    build_exception_bucket_classification_prompt,
    build_llm_reconciliation_prompt,
    build_second_pass_reconciliation_prompt,
)
from app.services.mapped_reconciliation_service import MappedReconciliationService


def test_mock_llm_tiebreak_response_shape():
    client = MockLLMClient()
    out = client.complete_json("tie-break candidate list")
    assert "recommended_match_index" in out
    assert "suggested_confidence" in out


def test_mock_llm_exception_response_shape():
    client = MockLLMClient()
    out = client.complete_json("explain unreconciled exception")
    assert "explanation" in out
    assert "actions" in out


def test_mock_llm_reconciliation_response_shape():
    client = MockLLMClient()
    prompt = json.dumps(
        {
            "task": "llm_reconciliation",
            "left_transactions": [
                {
                    "id": "left-1",
                    "transaction_date": "2025-02-21",
                    "amount": "100.00",
                    "currency": "INR",
                    "reference": "ABC123",
                    "counterparty": "acme",
                }
            ],
            "right_transactions": [
                {
                    "id": "right-1",
                    "transaction_date": "2025-02-21",
                    "amount": "100.00",
                    "currency": "INR",
                    "reference": "ABC123",
                    "counterparty": "acme",
                }
            ],
        }
    )
    out = client.complete_json(prompt)
    assert "matches" in out
    assert "unmatched_left" in out
    assert "unmatched_right" in out


def test_mock_llm_second_pass_response_shape():
    client = MockLLMClient()
    prompt = json.dumps(
        {
            "task": "llm_reconciliation_second_pass",
            "left_transactions": [
                {
                    "id": "left-1",
                    "transaction_date": "2025-02-21",
                    "amount": "100.00",
                    "currency": "INR",
                    "reference": "ABC123",
                    "counterparty": "acme",
                }
            ],
            "right_transactions": [
                {
                    "id": "right-1",
                    "transaction_date": "2025-02-28",
                    "amount": "100.00",
                    "currency": "INR",
                    "reference": "XYZ999",
                    "counterparty": "acme",
                }
            ],
        }
    )
    out = client.complete_json(prompt)
    assert "matches" in out
    assert "unmatched_left" in out
    assert "unmatched_right" in out


def test_reconciliation_prompt_has_rules_and_examples():
    prompt = build_llm_reconciliation_prompt(
        scenario_type="bank_gl",
        left_transactions=[],
        right_transactions=[],
    )
    payload = json.loads(prompt)

    assert payload["task"] == "llm_reconciliation"
    assert isinstance(payload.get("matching_rules"), list)
    assert len(payload["matching_rules"]) > 0
    assert "output_contract" in payload
    assert "examples" in payload
    assert any(key.startswith("positive_example") for key in payload["examples"])
    assert any(key.startswith("negative_example") for key in payload["examples"])


def test_second_pass_prompt_has_relaxed_delay_and_weak_reference_rules():
    prompt = build_second_pass_reconciliation_prompt(
        scenario_type="bank_gl",
        left_transactions=[],
        right_transactions=[],
    )
    payload = json.loads(prompt)

    assert payload["task"] == "llm_reconciliation_second_pass"
    rules_text = " ".join(payload.get("matching_rules", []))
    assert "10 days" in rules_text
    assert "Reference" in rules_text or "REFERENCE" in rules_text
    assert "weak" in rules_text.lower()


def test_updated_reconciliation_template_is_supported_by_parser():
    llm_payload = {
        "matches": [
            {
                "left_transaction_id": "left-1",
                "right_transaction_id": "right-1",
                "confidence": 0.91,
                "reason": "Amount/date/reference alignment",
                "matching_fields": ["amount", "date", "reference"],
            }
        ],
        "unmatched_left": [
            {
                "transaction_id": "left-2",
                "reason": "No right transaction within amount and date constraints",
            }
        ],
        "unmatched_right": [
            {
                "transaction_id": "right-2",
                "reason": "No left transaction with compatible reference",
            }
        ],
    }

    normalized = MappedReconciliationService._normalize_llm_reconciliation_payload(
        llm_payload
    )
    assert len(normalized["matches"]) == 1
    assert len(normalized["unmatched_left"]) == 1
    assert len(normalized["unmatched_right"]) == 1

    left_id, right_id = MappedReconciliationService._extract_match_ids(
        normalized["matches"][0]
    )
    assert left_id == "left-1"
    assert right_id == "right-1"

    left_reasons = MappedReconciliationService._reason_by_transaction(
        normalized["unmatched_left"]
    )
    right_reasons = MappedReconciliationService._reason_by_transaction(
        normalized["unmatched_right"]
    )
    assert left_reasons["left-2"]
    assert right_reasons["right-2"]


def test_reconciliation_parser_handles_non_dict_payload_safely():
    normalized = MappedReconciliationService._normalize_llm_reconciliation_payload(
        "not-a-dict"
    )
    assert normalized == {
        "matches": [],
        "unmatched_left": [],
        "unmatched_right": [],
    }


def test_exception_bucket_prompt_has_strict_contract_and_examples():
    prompt = build_exception_bucket_classification_prompt(
        left_label="Bank Statement",
        right_label="Cash Book",
        exceptions=[
            {
                "exception_id": "EX-1",
                "transaction_id": "TX-1",
                "side": "B",
                "description": "bank charges monthly",
            }
        ],
    )
    payload = json.loads(prompt)

    assert payload["task"] == "exception_bucket_classification"
    assert isinstance(payload.get("bucket_definitions"), list)
    assert len(payload["bucket_definitions"]) > 0
    assert isinstance(payload.get("positive_examples"), list)
    assert isinstance(payload.get("negative_examples"), list)
    assert "output_contract" in payload


def test_mock_llm_exception_bucket_classification_shape():
    client = MockLLMClient()
    prompt = build_exception_bucket_classification_prompt(
        left_label="Bank Statement",
        right_label="Cash Book",
        exceptions=[
            {
                "exception_id": "EX-1",
                "transaction_id": "TX-1",
                "side": "B",
                "amount": "50",
                "description": "bank charges monthly fee",
                "reason_detail": "missing in cash book",
            }
        ],
    )
    out = client.complete_json(prompt)
    assert "classified_exceptions" in out
    assert isinstance(out["classified_exceptions"], list)
    assert out["classified_exceptions"][0]["exception_id"] == "EX-1"
