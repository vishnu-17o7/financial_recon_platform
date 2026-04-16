import json
from typing import Any


def build_enrichment_prompt(record: dict[str, Any]) -> str:
    return (
        "You are a strict financial data normalizer. "
        "Return JSON object only with keys: normalized_name, transaction_type, reference_numbers. "
        "Keep values concise and deterministic.\n"
        f"Record: {json.dumps(record, default=str)}"
    )


def build_bulk_enrichment_prompt(records: list[dict[str, Any]]) -> str:
    payload = {
        "task": "bulk_enrichment",
        "objective": (
            "Normalize financial transaction text fields in batches. "
            "For each input record, return normalized_name, transaction_type, and reference_numbers."
        ),
        "records": records,
        "output_contract": {
            "enrichments": [
                {
                    "raw_transaction_id": "string - copied from input record",
                    "normalized_name": "string or null",
                    "transaction_type": "string or null",
                    "reference_numbers": ["list of string references"],
                }
            ]
        },
        "instruction": (
            "Return JSON object only. Do not include markdown. "
            "Include every record from input exactly once in enrichments. "
            "Keep each field value concise."
        ),
    }
    return json.dumps(payload, default=str)


def build_tiebreak_prompt(
    source_txn: dict[str, Any], candidates: list[dict[str, Any]]
) -> str:
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
        "objective": "Map columns from two different source files (e.g., Bank Statement and GL) to a standard reconciliation schema. Your goal is to identify which column in each file corresponds to each standard field.",
        "left_columns": left_columns,
        "right_columns": right_columns,
        "left_preview": left_preview,
        "right_preview": right_preview,
        "supported_fields": supported_fields,
        "matching_guidelines": [
            "Look for exact or close matches in column names (e.g., 'Transaction Date' = 'txn_date' = 'posting_date')",
            "Check the data values in preview rows to confirm your mapping is correct",
            "If a column name doesn't match but the data pattern does (e.g., dates, amounts), use that as evidence",
            "Coverage guardrail: for each side, map transaction_date and map at least one of amount/debit/credit when monetary columns exist",
            "Monetary strategy must be complete per side: map amount OR map both debit and credit",
            "If a side has separate debit and credit columns, map BOTH debit and credit and set amount to null on that side",
            "Cross-side monetary mapping is valid: one side can map amount while the other side maps debit and credit",
            "Do not output partial split mapping: debit mapped with credit null, or credit mapped with debit null, when both columns exist",
            "If split mapping is incomplete for a side, prefer amount on that side when available",
            "Do not force-map non-monetary fields when evidence is weak; set those fields to null",
            "Monetary exception: when a side has monetary candidates, map one of amount/debit/credit even with moderate confidence",
            "Map amount only when there is clear amount-like evidence in both name and preview values",
            "Monetary aliases include amount, amt, value, total, debit, credit, dr, cr, withdrawal, deposit, paid, received",
            "Do not leave amount, debit, and credit all null for a side if any monetary candidate exists",
            "Set confidence based on how certain you are: 0.9+ for clear matches, 0.6-0.9 for probable, 0.3-0.6 for uncertain, <0.3 for unlikely",
            "Provide a brief rationale explaining WHY you chose this mapping",
        ],
        "examples": {
            "example_1": {
                "scenario": "Bank Statement vs GL Reconciliation",
                "left_columns": [
                    "Txn Date",
                    "Description",
                    "Amount",
                    "Ref No",
                    "Value Dt",
                ],
                "right_columns": [
                    "posting_date",
                    "narration",
                    "amt",
                    "UTR",
                    "currency",
                ],
                "mappings": [
                    {
                        "field": "transaction_date",
                        "left_column": "Txn Date",
                        "right_column": "posting_date",
                        "confidence": 0.95,
                        "rationale": "Direct match - 'Txn Date' in bank file maps to 'posting_date' in GL",
                    },
                    {
                        "field": "description",
                        "left_column": "Description",
                        "right_column": "narration",
                        "confidence": 0.9,
                        "rationale": "Both contain free-form text describing transactions",
                    },
                    {
                        "field": "amount",
                        "left_column": "Amount",
                        "right_column": "amt",
                        "confidence": 0.95,
                        "rationale": "Numeric column for transaction values",
                    },
                    {
                        "field": "reference",
                        "left_column": "Ref No",
                        "right_column": "UTR",
                        "confidence": 0.85,
                        "rationale": "Both contain reference identifiers (UTR is common in Indian banking)",
                    },
                    {
                        "field": "value_date",
                        "left_column": "Value Dt",
                        "right_column": None,
                        "confidence": 0.4,
                        "rationale": "Value date exists in left file but no obvious match in right file",
                    },
                ],
            },
            "example_2": {
                "scenario": "Credit Card Statement vs Expense Report",
                "left_columns": [
                    "Posting Date",
                    "Transaction Description",
                    "Debit",
                    "Credit",
                    "Currency",
                    "Merchant ID",
                ],
                "right_columns": [
                    "expense_date",
                    "notes",
                    "dr_amount",
                    "cr_amount",
                    "ccy",
                    "vendor_ref",
                ],
                "mappings": [
                    {
                        "field": "transaction_date",
                        "left_column": "Posting Date",
                        "right_column": "expense_date",
                        "confidence": 0.92,
                        "rationale": "Date columns from both sources",
                    },
                    {
                        "field": "description",
                        "left_column": "Transaction Description",
                        "right_column": "notes",
                        "confidence": 0.88,
                        "rationale": "Text descriptions in both files",
                    },
                    {
                        "field": "debit",
                        "left_column": "Debit",
                        "right_column": "dr_amount",
                        "confidence": 0.9,
                        "rationale": "Debit amounts in both systems",
                    },
                    {
                        "field": "credit",
                        "left_column": "Credit",
                        "right_column": "cr_amount",
                        "confidence": 0.9,
                        "rationale": "Credit amounts in both systems",
                    },
                    {
                        "field": "currency",
                        "left_column": "Currency",
                        "right_column": "ccy",
                        "confidence": 0.95,
                        "rationale": "Currency codes (ccy is common abbreviation)",
                    },
                    {
                        "field": "counterparty",
                        "left_column": "Merchant ID",
                        "right_column": "vendor_ref",
                        "confidence": 0.6,
                        "rationale": "Possible vendor reference but naming is different",
                    },
                ],
            },
            "example_3": {
                "scenario": "Bank amount vs GL debit/credit",
                "left_columns": [
                    "Txn Date",
                    "Description",
                    "Amount",
                    "Ref No",
                ],
                "right_columns": [
                    "posting_date",
                    "narration",
                    "debit",
                    "credit",
                    "voucher_no",
                ],
                "mappings": [
                    {
                        "field": "transaction_date",
                        "left_column": "Txn Date",
                        "right_column": "posting_date",
                        "confidence": 0.95,
                        "rationale": "Date columns align clearly across both files",
                    },
                    {
                        "field": "amount",
                        "left_column": "Amount",
                        "right_column": None,
                        "confidence": 0.9,
                        "rationale": "Bank side uses single signed amount column",
                    },
                    {
                        "field": "debit",
                        "left_column": None,
                        "right_column": "debit",
                        "confidence": 0.9,
                        "rationale": "GL side stores outflows in debit column",
                    },
                    {
                        "field": "credit",
                        "left_column": None,
                        "right_column": "credit",
                        "confidence": 0.9,
                        "rationale": "GL side stores inflows in credit column",
                    },
                    {
                        "field": "reference",
                        "left_column": "Ref No",
                        "right_column": "voucher_no",
                        "confidence": 0.82,
                        "rationale": "Reference IDs align semantically",
                    },
                ],
            },
            "negative_example_1": {
                "scenario": "Partial split mapping is invalid",
                "wrong_mapping": [
                    {
                        "field": "debit",
                        "left_column": None,
                        "right_column": "debit",
                        "confidence": 0.85,
                        "rationale": "Debit column appears obvious",
                    },
                    {
                        "field": "credit",
                        "left_column": None,
                        "right_column": None,
                        "confidence": 0.2,
                        "rationale": "Credit uncertain",
                    },
                ],
                "why_wrong": "When both debit and credit columns exist, map both or use amount strategy",
            },
        },
        "output_contract": {
            "mappings": [
                {
                    "field": "string (one of the supported_fields)",
                    "left_column": "string (column name from left_columns) or null",
                    "right_column": "string (column name from right_columns) or null",
                    "confidence": "number between 0 and 1",
                    "rationale": "string explaining why this mapping was chosen",
                }
            ]
        },
        "instruction": (
            "Return JSON only. Do not include markdown or commentary. "
            "The output must have a top-level key 'mappings' containing an array of mapping objects. "
            "For each supported field, include: field, left_column, right_column, confidence (0-1), and rationale. "
            "If no suitable column is found for a field, set the column to null. "
            "Never guess a mapping from schema expectations alone; use only column names and preview evidence. "
            "When debit/credit columns exist for a side, map BOTH debit and credit and leave amount null on that side. "
            "Do not output partial split mapping: debit mapped with credit null, or credit mapped with debit null, when both columns exist. "
            "Cross-side mapping is valid: one side can use amount while the other side uses debit and credit. "
            "If an amount-like column is not clearly present on a side, set amount to null for that side. "
            "Before returning, validate each side has a complete monetary strategy: amount OR both debit and credit, when monetary candidates exist. This is a hard constraint. "
            "Never output amount, debit, and credit all null for a side if monetary columns are present. "
            "Use confidence to indicate certainty: 0.9+ = very sure, 0.7-0.9 = probable, 0.5-0.7 = uncertain, <0.5 = unlikely match. "
            "Be strict and concise: rationale must be one short sentence (max 12 words)."
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
        "objective": (
            "You are performing financial reconciliation between two sets of transactions (e.g., Bank Statement vs GL, "
            "Credit Card vs Expense Report). Your goal is to find matching transaction pairs between left and right sources. "
            "STRICT RULE: Each transaction can only be matched ONCE - one-to-one matching only. "
            "Do NOT create duplicate matches. Each left must match at most one right, and vice versa."
        ),
        "matching_rules": [
            "1. ONE-TO-ONE ONLY: Each left transaction can match at most ONE right transaction, and each right can match at most ONE left.",
            "2. CURRENCY HARD BLOCK: Never match transactions with different currencies - this is an absolute blocker.",
            "3. AMOUNT CONSISTENCY: Exact amount match is ideal. Small variance (<1%) allowed only if description suggests fee/charge/interest.",
            "4. DATE PROXIMITY: 0-3 days = strong match, 4-7 days = weak match (needs strong reference/counterparty), 7+ days = no match.",
            "5. REFERENCE EQUALITY: Exact or near-exact reference (after trimming spaces, uppercasing) is STRONG positive signal.",
            "6. COUNTERPARTY EQUALITY: Matching counterparty names (after normalization) is STRONG positive signal.",
            "7. DESCRIPTION SIMILARITY: Similar descriptions are supporting evidence but CANNOT override hard conflicts.",
            "8. CONFIDENCE THRESHOLD: Below 0.70 confidence = keep unmatched with clear reason.",
            "9. NO FORCED MATCHES: Don't match just to improve coverage - accuracy is more important.",
        ],
        "scoring_weights": {
            "exact_amount_match": "+0.3",
            "amount_within_1pct": "+0.2",
            "amount_within_5pct": "+0.1",
            "same_date": "+0.25",
            "date_within_1_day": "+0.2",
            "date_within_3_days": "+0.15",
            "exact_reference_match": "+0.25",
            "reference_partial_match": "+0.1",
            "exact_counterparty_match": "+0.2",
            "description_similarity_high": "+0.1",
            "currency_mismatch": "-1.0 (hard block)",
            "date_diff_over_7_days": "-0.5",
        },
        "when_to_match": [
            "✓ Amount matches exactly OR within 1% AND date is within 3 days AND (reference OR counterparty matches)",
            "✓ Amount matches AND date matches AND description suggests same business event",
            "✓ Strong reference match even with minor date/amount variance if explained by processing delays",
        ],
        "when_not_to_match": [
            "✗ Different currencies - ALWAYS reject",
            "✗ Amount gap is >5% and cannot be explained by fee/charge/interest in description",
            "✗ References conflict (both exist but different) with no stronger corroborating evidence",
            "✗ Date difference >7 days regardless of other factors",
            "✗ When matching would create a duplicate (transaction already matched elsewhere)",
        ],
        "output_contract": {
            "matches": [
                {
                    "left_transaction_id": "string - MUST match an ID from left_transactions",
                    "right_transaction_id": "string - MUST match an ID from right_transactions",
                    "confidence": "number between 0 and 1",
                    "reason": "short, concrete justification of why these match",
                    "matching_fields": [
                        "list of fields that contributed to the match: amount, date, reference, counterparty, description"
                    ],
                }
            ],
            "unmatched_left": [
                {
                    "transaction_id": "string - MUST be an ID from left_transactions that is NOT in matches",
                    "reason": "why no valid right counterpart exists (e.g., 'No right transaction with matching amount within date range', 'Currency mismatch with all candidates')",
                }
            ],
            "unmatched_right": [
                {
                    "transaction_id": "string - MUST be an ID from right_transactions that is NOT in matches",
                    "reason": "why no valid left counterpart exists",
                }
            ],
        },
        "examples": {
            "positive_example_1": {
                "description": "Exact amount, date, and reference match",
                "left_transaction": {
                    "id": "L-1001",
                    "transaction_date": "2025-02-21",
                    "amount": "12500.00",
                    "currency": "INR",
                    "reference": "UTR123456789",
                    "counterparty": "acme pvt ltd",
                    "description": "neft payment to acme pvt ltd inv-1001",
                },
                "right_transaction": {
                    "id": "R-9001",
                    "transaction_date": "2025-02-21",
                    "amount": "12500.00",
                    "currency": "INR",
                    "reference": "UTR123456789",
                    "counterparty": "ACME PVT LTD",
                    "description": "customer receipt from acme",
                },
                "decision": {
                    "should_match": True,
                    "confidence": 0.98,
                    "reason": "Exact amount, date, currency, reference + matching counterparty",
                    "matching_fields": ["amount", "date", "reference", "counterparty"],
                },
            },
            "positive_example_2": {
                "description": "Amount match with minor date variance but strong reference",
                "left_transaction": {
                    "id": "L-2005",
                    "transaction_date": "2025-03-01",
                    "amount": "50000.00",
                    "currency": "USD",
                    "reference": "WIRE-2025-0301",
                    "counterparty": "global tech inc",
                    "description": "wire transfer global tech march",
                },
                "right_transaction": {
                    "id": "R-8050",
                    "transaction_date": "2025-03-02",
                    "amount": "50000.00",
                    "currency": "USD",
                    "reference": "WIRE-2025-0301",
                    "counterparty": "Global Tech Inc",
                    "description": "receipt global tech",
                },
                "decision": {
                    "should_match": True,
                    "confidence": 0.85,
                    "reason": "Exact amount, reference match, 1-day date variance allowed with strong reference",
                    "matching_fields": ["amount", "reference", "counterparty"],
                },
            },
            "negative_example_1": {
                "description": "Currency mismatch - hard block",
                "left_transaction": {
                    "id": "L-3001",
                    "transaction_date": "2025-02-22",
                    "amount": "250.00",
                    "currency": "INR",
                    "reference": "FEEFEB",
                    "counterparty": None,
                    "description": "bank charge february",
                },
                "right_transaction": {
                    "id": "R-9100",
                    "transaction_date": "2025-02-22",
                    "amount": "3.00",
                    "currency": "USD",
                    "reference": "JV1002",
                    "counterparty": None,
                    "description": "bank charges expense",
                },
                "decision": {
                    "should_match": False,
                    "reason": "Currency mismatch (INR vs USD) is a hard block - NEVER match different currencies",
                },
            },
            "negative_example_2": {
                "description": "Amount too far apart with no explanation",
                "left_transaction": {
                    "id": "L-4001",
                    "transaction_date": "2025-01-15",
                    "amount": "10000.00",
                    "currency": "EUR",
                    "reference": "INV-001",
                    "counterparty": "supplier xyz",
                    "description": "payment to supplier xyz",
                },
                "right_transaction": {
                    "id": "R-7500",
                    "transaction_date": "2025-01-15",
                    "amount": "8500.00",
                    "currency": "EUR",
                    "reference": "INV-001",
                    "counterparty": "supplier xyz",
                    "description": "invoice payment",
                },
                "decision": {
                    "should_match": False,
                    "reason": "Amount difference is 500 EUR (5%) - exceeds threshold without fee/charge explanation in description",
                },
            },
            "negative_example_3": {
                "description": "Date too far apart",
                "left_transaction": {
                    "id": "L-5001",
                    "transaction_date": "2025-01-01",
                    "amount": "1500.00",
                    "currency": "GBP",
                    "reference": "PAY-001",
                    "counterparty": "service provider",
                    "description": "january service payment",
                },
                "right_transaction": {
                    "id": "R-6200",
                    "transaction_date": "2025-01-20",
                    "amount": "1500.00",
                    "currency": "GBP",
                    "reference": "PAY-001",
                    "counterparty": "service provider",
                    "description": "service provider payment",
                },
                "decision": {
                    "should_match": False,
                    "reason": "Date difference is 19 days - exceeds 7-day threshold",
                },
            },
        },
        "left_transactions": left_transactions,
        "right_transactions": right_transactions,
        "instruction": (
            "IMPORTANT: Return JSON only. No markdown, no explanations outside JSON. "
            "Use exactly these top-level keys: matches, unmatched_left, unmatched_right. "
            "Each match must reference valid transaction IDs from the input. "
            "Each unmatched transaction must be listed with a clear reason. "
            "Prioritize accuracy over coverage - it's better to leave unmatched than to force incorrect matches. "
            "Remember: ONE-TO-ONE matching only - never match a transaction that is already in another pair. "
            "Be strict and concise: keep reason text short and concrete. "
            "For ties, choose deterministically by the lexicographically smallest right_transaction_id."
        ),
    }
    return json.dumps(payload, default=str)


def build_second_pass_reconciliation_prompt(
    scenario_type: str,
    left_transactions: list[dict[str, Any]],
    right_transactions: list[dict[str, Any]],
) -> str:
    payload = {
        "task": "llm_reconciliation_second_pass",
        "scenario_type": scenario_type,
        "objective": (
            "You are running a SECOND PASS reconciliation retry for transactions that were previously unmatched. "
            "This pass is for borderline operational delays in bank processes while still preserving accuracy and one-to-one mapping."
        ),
        "matching_rules": [
            "1. ONE-TO-ONE ONLY: Each left transaction can match at most ONE right transaction, and vice versa.",
            "2. CURRENCY HARD BLOCK: Never match transactions with different currencies.",
            "3. DATE DELAY ALLOWANCE: Treat up to 10 days date difference as acceptable when other evidence supports the same business event.",
            "4. AMOUNT PRIORITY: Amount agreement is primary evidence. Exact is best; small variance may be allowed with explicit justification.",
            "5. REFERENCE WEAK SIGNAL ONLY: Reference can support confidence but MUST NEVER be the deciding factor.",
            "6. COUNTERPARTY + DESCRIPTION: Use as contextual support for delayed settlements and posting lag.",
            "7. CONFIDENCE THRESHOLD: Below 0.65 confidence keep unmatched with clear reason.",
            "8. NO FORCED MATCHES: If evidence is weak/conflicting, keep unmatched.",
        ],
        "when_to_match": [
            "✓ Amounts align and date difference is <=10 days with supportive counterparty/description context",
            "✓ Amount aligns and delay pattern is plausible for bank clearing/posting lag",
            "✓ Multiple supporting signals align; reference may help but cannot decide alone",
        ],
        "when_not_to_match": [
            "✗ Currency mismatch",
            "✗ Date difference >10 days with no strong corroboration",
            "✗ Match depends only on reference equality while amount/date/context conflict",
            "✗ Ambiguous candidate set where confidence remains below threshold",
        ],
        "output_contract": {
            "matches": [
                {
                    "left_transaction_id": "string - MUST match an ID from left_transactions",
                    "right_transaction_id": "string - MUST match an ID from right_transactions",
                    "confidence": "number between 0 and 1",
                    "reason": "short concrete justification",
                    "matching_fields": [
                        "amount, date, counterparty, description, reference"
                    ],
                }
            ],
            "unmatched_left": [
                {
                    "transaction_id": "string from left_transactions",
                    "reason": "why no valid right counterpart exists",
                }
            ],
            "unmatched_right": [
                {
                    "transaction_id": "string from right_transactions",
                    "reason": "why no valid left counterpart exists",
                }
            ],
        },
        "left_transactions": left_transactions,
        "right_transactions": right_transactions,
        "instruction": (
            "IMPORTANT: Return JSON only. No markdown. "
            "Use exactly these top-level keys: matches, unmatched_left, unmatched_right. "
            "Each match must reference valid input IDs. "
            "Keep one-to-one integrity. "
            "Reference is weak supporting evidence only and cannot be the sole deciding factor. "
            "For ties, choose deterministically by lexicographically smallest right_transaction_id."
        ),
    }
    return json.dumps(payload, default=str)


def build_exception_bucket_classification_prompt(
    left_label: str,
    right_label: str,
    exceptions: list[dict[str, Any]],
) -> str:
    payload = {
        "task": "exception_bucket_classification",
        "objective": (
            "Classify unreconciled exceptions into bank reconciliation adjustment buckets. "
            "Each exception must be assigned to exactly one bucket for downstream adjusted-balance math and journal preparation."
        ),
        "source_labels": {
            "left": left_label,
            "right": right_label,
        },
        "bucket_definitions": [
            {
                "bucket_key": "bank_deposits_in_transit",
                "side": "A",
                "effect": "add",
                "description": "Receipts recorded in cash book but not yet reflected in bank statement",
            },
            {
                "bucket_key": "bank_outstanding_cheques",
                "side": "A",
                "effect": "deduct",
                "description": "Payments recorded in cash book but cheque not yet presented in bank statement",
            },
            {
                "bucket_key": "bank_errors",
                "side": "A",
                "effect": "variable",
                "description": "Errors identified in bank statement side",
            },
            {
                "bucket_key": "cash_missing_receipts",
                "side": "B",
                "effect": "add",
                "description": "Receipts present in bank statement but missing in cash book",
            },
            {
                "bucket_key": "cash_interest_received",
                "side": "B",
                "effect": "add",
                "description": "Interest credited by bank but not yet recorded in cash book",
            },
            {
                "bucket_key": "cash_bank_fees",
                "side": "B",
                "effect": "deduct",
                "description": "Bank charges/fees debited by bank and missing in cash book",
            },
            {
                "bucket_key": "cash_bounced_cheques",
                "side": "B",
                "effect": "deduct",
                "description": "Dishonored/bounced cheques requiring cash book deduction",
            },
            {
                "bucket_key": "cash_book_errors",
                "side": "B",
                "effect": "variable",
                "description": "Posting/calculation/classification errors in cash book",
            },
            {
                "bucket_key": "uncategorized",
                "side": "A|B",
                "effect": "none",
                "description": "Insufficient evidence for reliable classification",
            },
        ],
        "classification_rules": [
            "Use transaction side as a hard guardrail: side A must map to bank_* or uncategorized; side B must map to cash_* or uncategorized.",
            "Never assign a cash-only bucket to side A or bank-only bucket to side B.",
            "Prefer keyword+context evidence from description, reason_detail, recommended_action, and reference.",
            "If evidence is weak or conflicting, choose uncategorized with low confidence.",
            "Return every input exception exactly once.",
            "Confidence: >=0.85 clear, 0.65-0.84 probable, <0.65 uncertain.",
        ],
        "positive_examples": [
            {
                "exception": {
                    "exception_id": "EX-1",
                    "transaction_id": "TX-1",
                    "side": "B",
                    "description": "interest credited by bank june",
                    "reason_detail": "Not recorded in cash book",
                },
                "classification": {
                    "exception_id": "EX-1",
                    "bucket_key": "cash_interest_received",
                    "confidence": 0.95,
                    "rationale": "Interest credit on bank side must be added to cash book",
                },
            },
            {
                "exception": {
                    "exception_id": "EX-2",
                    "transaction_id": "TX-2",
                    "side": "B",
                    "description": "bank charges monthly fee",
                    "reason_detail": "Missing in cash book",
                },
                "classification": {
                    "exception_id": "EX-2",
                    "bucket_key": "cash_bank_fees",
                    "confidence": 0.93,
                    "rationale": "Bank fee should reduce cash book adjusted balance",
                },
            },
        ],
        "negative_examples": [
            {
                "exception": {
                    "exception_id": "EX-3",
                    "transaction_id": "TX-3",
                    "side": "A",
                    "description": "deposit in transit",
                },
                "invalid_classification": {
                    "bucket_key": "cash_missing_receipts",
                    "reason": "Invalid because side A cannot map to cash_* bucket",
                },
            },
            {
                "exception": {
                    "exception_id": "EX-4",
                    "transaction_id": "TX-4",
                    "side": "B",
                    "description": "unclear memo",
                },
                "invalid_classification": {
                    "bucket_key": "cash_bank_fees",
                    "reason": "Invalid because there is no fee/charge evidence",
                },
                "valid_alternative": {
                    "bucket_key": "uncategorized",
                },
            },
        ],
        "exceptions": exceptions,
        "output_contract": {
            "classified_exceptions": [
                {
                    "exception_id": "string from input",
                    "bucket_key": "one of the allowed bucket keys",
                    "confidence": "number 0..1",
                    "rationale": "short concrete reason",
                }
            ]
        },
        "instruction": (
            "Return JSON only. No markdown. "
            "Use top-level key classified_exceptions only. "
            "Classify each input exception exactly once by exception_id. "
            "Do not invent exception ids. Keep rationale concise."
        ),
    }
    return json.dumps(payload, default=str)


def build_explanation_prompt(context: dict[str, Any], is_exception: bool) -> str:
    mode = "unreconciled exception" if is_exception else "matched item"
    return (
        f"Explain {mode} in plain language. Return JSON with explanation and actions. "
        f"Context: {json.dumps(context, default=str)}"
    )
