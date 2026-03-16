from app.models.enums import ScenarioType
from app.services.mapped_reconciliation_service import ColumnMappingService


def test_suggest_mappings_returns_transaction_date_candidates():
    service = ColumnMappingService()
    left_preview = {
        "columns": ["txn_date", "amount", "reference"],
        "preview_rows": [{"txn_date": "2025-02-21", "amount": 100, "reference": "UTR1"}],
    }
    right_preview = {
        "columns": ["posting_date", "debit", "credit", "voucher_no"],
        "preview_rows": [{"posting_date": "2025-02-21", "debit": 0, "credit": 100, "voucher_no": "JV1"}],
    }

    out = service.suggest_mappings(
        scenario_type=ScenarioType.BANK_GL,
        left_preview=left_preview,
        right_preview=right_preview,
    )

    transaction_date = next(item for item in out["suggestions"] if item["field"] == "transaction_date")
    assert transaction_date["left_column"] == "txn_date"
    assert transaction_date["right_column"] == "posting_date"
    assert transaction_date["source"] == "llm"


def test_mapping_validation_requires_date_and_amount_strategy():
    issues = ColumnMappingService.mapping_level_issues(
        [
            {"field": "transaction_date", "left_column": "txn_date", "right_column": None},
            {"field": "amount", "left_column": "amount", "right_column": None},
            {"field": "debit", "left_column": None, "right_column": None},
            {"field": "credit", "left_column": None, "right_column": None},
        ]
    )

    assert any(issue["side"] == "right" and issue["field"] == "transaction_date" for issue in issues)
    assert any(issue["side"] == "right" and issue["field"] == "amount" for issue in issues)
