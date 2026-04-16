import pandas as pd

from app.models.enums import ScenarioType
from app.services.mapped_reconciliation_service import (
    ColumnMappingService,
    MappedReconciliationService,
)


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


def test_mapping_validation_allows_debit_credit_without_amount():
    issues = ColumnMappingService.mapping_level_issues(
        [
            {
                "field": "transaction_date",
                "left_column": "txn_date",
                "right_column": "posting_date",
            },
            {"field": "amount", "left_column": None, "right_column": None},
            {"field": "debit", "left_column": "debit", "right_column": "dr"},
            {"field": "credit", "left_column": "credit", "right_column": "cr"},
        ]
    )

    assert not any(issue["severity"] == "error" for issue in issues)


def test_mapping_validation_flags_partial_split_when_both_candidates_exist():
    issues = ColumnMappingService.mapping_level_issues(
        [
            {
                "field": "transaction_date",
                "left_column": "txn_date",
                "right_column": "posting_date",
            },
            {"field": "amount", "left_column": "amount", "right_column": None},
            {"field": "debit", "left_column": None, "right_column": "debit"},
            {"field": "credit", "left_column": None, "right_column": None},
        ],
        left_columns=["txn_date", "amount", "reference"],
        right_columns=["posting_date", "debit", "credit", "voucher_no"],
    )

    assert any(
        issue["severity"] == "error"
        and issue["side"] == "right"
        and issue["field"] == "debit_credit"
        for issue in issues
    )


def test_build_normalize_payload_keeps_amount_when_split_is_partial():
    row = pd.Series(
        {
            "txn_date": "2025-02-21",
            "amount": "1200.00",
            "debit": "1200.00",
            "description": "NEFT transfer",
        }
    )
    mapping_index = {
        "transaction_date": "txn_date",
        "amount": "amount",
        "debit": "debit",
        "description": "description",
    }

    normalize_payload, _ = MappedReconciliationService._build_normalize_payload(
        row, mapping_index
    )

    assert normalize_payload["amount"] == "1200.00"
    assert normalize_payload["debit"] == "1200.00"
    assert normalize_payload["credit"] is None
