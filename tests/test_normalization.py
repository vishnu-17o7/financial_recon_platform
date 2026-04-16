from app.models.enums import ScenarioType
from app.services.normalization_service import bulk_enrich_records, normalize_record


class SingleObjectBulkLLM:
    def complete_json(self, _prompt: str):
        return {
            "raw_transaction_id": "r1",
            "normalized_name": "Acme Ltd",
            "transaction_type": "collection",
            "reference_numbers": ["UTR123"],
        }


def test_normalize_bank_record_basic():
    raw = {
        "txn_date": "2025-02-21",
        "description": "NEFT INV-1001 ACME PVT",
        "amount": "12500.00",
        "currency": "inr",
        "reference": "UTR123",
        "counterparty": "ACME PVT LTD",
        "dr_cr": "credit",
    }
    out = normalize_record(
        raw=raw,
        scenario_type=ScenarioType.BANK_GL,
        source_type="bank_statement",
        source_system="generic_bank",
        raw_transaction_id="r1",
        side="A",
    )
    assert out.currency == "INR"
    assert out.side == "A"
    assert out.amount == 12500
    assert out.counterparty_normalized == "acme pvt ltd"


def test_bulk_enrichment_accepts_single_object_response():
    records = [
        {
            "raw_transaction_id": "r1",
            "description": "customer collection",
            "counterparty": "ACME",
            "reference": "UTR123",
            "invoice_ref": None,
            "scenario_type": ScenarioType.BANK_GL,
        }
    ]

    out = bulk_enrich_records(
        records=records,
        llm_client=SingleObjectBulkLLM(),
        batch_size=20,
    )

    assert out["r1"]["normalized_name"] == "Acme Ltd"
    assert out["r1"]["transaction_type"] == "collection"
    assert out["r1"]["reference_numbers"] == ["UTR123"]
