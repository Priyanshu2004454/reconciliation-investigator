import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)  # razorpay event id -> idempotency key
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), default="RECEIVED")  # WebhookProcessingStatus
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    """
    Immutable (from the normal UI) record of every meaningful action taken
    by either the AI or a human on a reconciliation case.
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("reconciliation_cases.id"), nullable=True, index=True)

    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)  # AuditActor: AI | HUMAN | SYSTEM
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)  # user id or "ai-investigator"
    action: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "SETTLEMENT_FETCHED", "CASE_MARKED_RESOLVED"

    previous_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
