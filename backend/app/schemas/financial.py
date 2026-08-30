from datetime import datetime, date
from typing import Optional, Any

from pydantic import BaseModel, ConfigDict


class NormalizedRecord(BaseModel):
    """
    Common shape every source (Razorpay payment/order/refund/settlement, bank row)
    gets mapped into before the reconciliation engine touches it. Keeps the engine
    from ever having to know about Razorpay's or a bank's raw field names.
    """
    model_config = ConfigDict(from_attributes=True)

    internal_id: Optional[str] = None
    source: str
    external_id: str
    amount: float
    currency: str = "INR"
    date: datetime
    reference_id: Optional[str] = None
    utr: Optional[str] = None
    status: str
    metadata: dict[str, Any] = {}


class RazorpayPaymentOut(BaseModel):
    razorpay_payment_id: str
    order_id: Optional[str]
    amount: float
    currency: str
    status: str
    method: Optional[str]
    fee: Optional[float]
    tax: Optional[float]
    payment_date: datetime


class RazorpaySettlementOut(BaseModel):
    razorpay_settlement_id: str
    utr: Optional[str]
    amount: float
    fees: Optional[float]
    tax: Optional[float]
    status: str
    settlement_date: datetime


class RazorpayRefundOut(BaseModel):
    razorpay_refund_id: str
    razorpay_payment_id: str
    amount: float
    status: str
    refund_date: datetime


class RazorpayOrderOut(BaseModel):
    razorpay_order_id: str
    amount: float
    currency: str
    status: str
    receipt: Optional[str]
    order_date: datetime


class SyncResult(BaseModel):
    """Returned by every fetch_and_store_* operation for observability."""
    source: str
    fetched: int
    created: int
    updated: int
    skipped: int
    errors: list[str] = []
    duration_ms: int


class DemoSeedResponse(BaseModel):
    merchant_account_id: str
    records_created: int
    records_existing: int
    payments_count: int
    settlements_count: int
    refunds_count: int
    bank_transactions_count: int
    total_records: int
    counts: dict[str, int]

