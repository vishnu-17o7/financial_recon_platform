from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.settings import get_settings
from app.db.base import Base
from app.models.enums import AccountType, Direction, ExceptionStatus, JobStatus, MatchType, ScenarioType

settings = get_settings()


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    account_code: Mapped[str] = mapped_column(String(64), index=True)
    account_name: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType), index=True)
    legal_entity: Mapped[str] = mapped_column(String(128), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    source_system: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TransactionRaw(Base):
    __tablename__ = "transactions_raw"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    ingestion_batch_id: Mapped[str] = mapped_column(String(128), index=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    source_system: Mapped[str] = mapped_column(String(64), index=True)
    scenario_type: Mapped[ScenarioType] = mapped_column(Enum(ScenarioType), index=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_number: Mapped[int] = mapped_column()
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    parse_status: Mapped[str] = mapped_column(String(32), default="parsed")
    parser_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TransactionNormalized(Base):
    __tablename__ = "transactions_normalized"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    raw_transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions_raw.id"), index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    source_system: Mapped[str] = mapped_column(String(64), index=True)
    scenario_type: Mapped[ScenarioType] = mapped_column(Enum(ScenarioType), index=True)
    direction: Mapped[Direction] = mapped_column(Enum(Direction), index=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), index=True)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    description_clean: Mapped[str] = mapped_column(Text)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    counterparty_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    reference_number: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    external_txn_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    tax_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    side: Mapped[str] = mapped_column(String(1), index=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    raw_transaction: Mapped[TransactionRaw] = relationship()

    __table_args__ = (
        Index("ix_txn_norm_lookup", "scenario_type", "side", "transaction_date", "amount", "currency"),
    )


class ReconciliationJob(Base):
    __tablename__ = "reconciliation_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    scenario_type: Mapped[ScenarioType] = mapped_column(Enum(ScenarioType), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.CREATED, index=True)
    filters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    reconciliation_job_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_jobs.id"), index=True)
    transaction_a_id: Mapped[str] = mapped_column(ForeignKey("transactions_normalized.id"), index=True)
    transaction_b_id: Mapped[str] = mapped_column(ForeignKey("transactions_normalized.id"), index=True)
    match_type: Mapped[MatchType] = mapped_column(Enum(MatchType), default=MatchType.ONE_TO_ONE)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    algorithm_used: Mapped[str] = mapped_column(String(64))
    amount_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    date_delta_days: Mapped[int | None] = mapped_column(nullable=True)
    auto_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReconciliationException(Base):
    __tablename__ = "exceptions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    reconciliation_job_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_jobs.id"), index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions_normalized.id"), index=True)
    status: Mapped[ExceptionStatus] = mapped_column(Enum(ExceptionStatus), default=ExceptionStatus.OPEN)
    reason_code: Mapped[str] = mapped_column(String(64), index=True)
    reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EmbeddingRecord(Base):
    __tablename__ = "embeddings"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions_normalized.id"), index=True, unique=True)
    embedding_model: Mapped[str] = mapped_column(String(128))
    vector: Mapped[list[float]] = mapped_column(Vector(settings.vector_dim))
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(128), default="system")
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    llm_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
