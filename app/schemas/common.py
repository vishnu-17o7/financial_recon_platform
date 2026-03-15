from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import Direction, ExceptionStatus, JobStatus, MatchType, ScenarioType


class RawTransactionIn(BaseModel):
    ingestion_batch_id: str
    source_type: str
    source_system: str
    scenario_type: ScenarioType
    row_number: int
    raw_payload: dict[str, Any]
    file_name: str | None = None
    parser_name: str | None = None


class NormalizedTransactionIn(BaseModel):
    raw_transaction_id: str
    account_id: str | None = None
    source_type: str
    source_system: str
    scenario_type: ScenarioType
    direction: Direction
    transaction_date: date
    value_date: date | None = None
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    description_clean: str
    description_raw: str | None = None
    counterparty_raw: str | None = None
    counterparty_normalized: str | None = None
    reference_number: str | None = None
    invoice_number: str | None = None
    external_txn_id: str | None = None
    tax_code: str | None = None
    classification: str | None = None
    side: str
    metadata_json: dict[str, Any] | None = None


class JobCreateRequest(BaseModel):
    scenario_type: ScenarioType
    period_start: date
    period_end: date
    filters: dict[str, Any] | None = None
    created_by: str | None = "api"


class JobResponse(BaseModel):
    id: str
    scenario_type: ScenarioType
    status: JobStatus
    metrics_json: dict[str, Any] | None
    error_message: str | None
    created_at: datetime


class MatchOverrideRequest(BaseModel):
    match_id: str
    auto_accepted: bool
    reason: str
    actor: str = "user"


class ExplainRequest(BaseModel):
    transaction_id: str
    match_id: str | None = None
    exception_id: str | None = None


class MatchView(BaseModel):
    id: str
    transaction_a_id: str
    transaction_b_id: str
    match_type: MatchType
    confidence_score: Decimal
    algorithm_used: str
    auto_accepted: bool


class ExceptionView(BaseModel):
    id: str
    transaction_id: str
    status: ExceptionStatus
    reason_code: str
    reason_detail: str | None
