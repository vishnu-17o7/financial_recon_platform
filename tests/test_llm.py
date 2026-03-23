import json

from app.llm.mock_clients import MockLLMClient
from app.llm.prompt_builders import build_llm_reconciliation_prompt
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
