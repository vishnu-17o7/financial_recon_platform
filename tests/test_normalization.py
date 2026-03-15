from app.models.enums import ScenarioType
from app.services.normalization_service import normalize_record


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
