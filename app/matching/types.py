from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class TransactionFeature:
    id: str
    side: str
    date: date
    amount: Decimal
    currency: str
    description: str
    counterparty: str | None
    reference: str | None
    account_id: str | None
    scenario_type: str


@dataclass
class CandidateScore:
    transaction_a_id: str
    transaction_b_id: str
    score: float
    algorithm: str
    reason: str
    amount_delta: Decimal
    date_delta_days: int
