import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Numeric, ForeignKey, JSON, Float, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReconciliationRun(Base):
    """One execution of the deterministic reconciliation engine."""
    __tablename__ = "reconciliation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchant_accounts.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_transactions: Mapped[int] = mapped_column(default=0)
    matched_count: Mapped[int] = mapped_column(default=0)
    explained_count: Mapped[int] = mapped_column(default=0)
    needs_review_count: Mapped[int] = mapped_column(default=0)
    failed_count: Mapped[int] = mapped_column(default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    matched_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    unresolved_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    match_rate: Mapped[float] = mapped_column(default=0.0)  # percentage, e.g. 92.0
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")  # RUNNING | COMPLETED | FAILED


class ReconciliationCase(Base):
    """
    A single reconciliation unit — typically one payment/settlement pair being
    checked against bank data. This is the deterministic engine's output;
    the AI never writes to `status` directly without a corresponding
    investigation + evidence trail.
    """
    __tablename__ = "reconciliation_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reconciliation_runs.id"), nullable=False)
    merchant_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchant_accounts.id"), nullable=False)

    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    razorpay_settlement_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    bank_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bank_transactions.id"), nullable=True)

    expected_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    actual_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    difference: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # ReconciliationStatus
    match_rule: Mapped[str | None] = mapped_column(String(64), nullable=True)  # which deterministic rule matched

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Investigation(Base):
    """AI investigation output for a reconciliation case. Structured, not free-form."""
    __tablename__ = "investigations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reconciliation_cases.id"), nullable=False, index=True)

    classification: Mapped[str] = mapped_column(String(32), nullable=False)  # ReconciliationStatus
    root_cause: Mapped[str] = mapped_column(String(64), nullable=False)      # RootCauseCategory
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True)

    ai_model: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_ai_response: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)

    human_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)  # HumanDecision
    human_decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    human_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    human_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class InvestigationEvidence(Base):
    """
    Individual, atomic pieces of evidence the AI used to reach its conclusion.
    Every evidence row must trace back to a real fetched record (payment,
    settlement, refund, or bank row) — never a fabricated fact.
    """
    __tablename__ = "investigation_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("investigations.id"), nullable=False, index=True)

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # RecordSource
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)   # e.g. razorpay_payment_id
    description: Mapped[str] = mapped_column(Text, nullable=False)
    data_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
