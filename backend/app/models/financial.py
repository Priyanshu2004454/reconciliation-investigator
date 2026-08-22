import uuid
from datetime import datetime, date

from sqlalchemy import String, DateTime, Date, Numeric, ForeignKey, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RazorpayPayment(Base):
    __tablename__ = "razorpay_payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchant_accounts.id"), nullable=False)
    razorpay_payment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)  # stored in rupees
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fee: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    tax: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    payment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_payment_order", "order_id"),
    )


class RazorpayOrder(Base):
    __tablename__ = "razorpay_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchant_accounts.id"), nullable=False)
    razorpay_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    receipt: Mapped[str | None] = mapped_column(String(128), nullable=True)
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class RazorpayRefund(Base):
    __tablename__ = "razorpay_refunds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchant_accounts.id"), nullable=False)
    razorpay_refund_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    razorpay_payment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    refund_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class RazorpaySettlement(Base):
    __tablename__ = "razorpay_settlements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchant_accounts.id"), nullable=False)
    razorpay_settlement_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    utr: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    fees: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    tax: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    settlement_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class BankTransaction(Base):
    """Normalized row from an uploaded bank statement CSV."""
    __tablename__ = "bank_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchant_accounts.id"), nullable=False)
    import_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    utr: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    credit: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    debit: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    balance: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    row_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # for duplicate detection
    is_duplicate: Mapped[bool] = mapped_column(default=False)
    raw_row: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
