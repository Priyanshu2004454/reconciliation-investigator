"""
Typed inputs/outputs for the deterministic reconciliation engine.

The engine treats a Razorpay *settlement* as the anchor of each case, since
the settlement is what actually carries a UTR and therefore what a bank
credit can be matched against. Each settlement can have one or more
underlying payments linked to it (in Razorpay's real model, one settlement
batches many payments; for this MVP we accept an explicit `payment_ids`
link per settlement rather than reconstructing Razorpay's internal batching,
which is out of scope per section 30 of the spec).
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class PaymentInput(BaseModel):
    razorpay_payment_id: str
    amount: float
    fee: float = 0.0
    tax: float = 0.0
    status: str = "captured"


class RefundInput(BaseModel):
    razorpay_refund_id: str
    razorpay_payment_id: str
    amount: float
    status: str = "processed"


class SettlementInput(BaseModel):
    razorpay_settlement_id: str
    utr: Optional[str] = None
    amount: float
    fees: float = 0.0
    tax: float = 0.0
    status: str = "processed"
    settlement_date: date
    payment_ids: list[str] = []  # payments this settlement is understood to cover


class BankRowInput(BaseModel):
    id: str  # internal bank_transactions.id (or a temp key pre-persist)
    transaction_date: date
    reference_id: Optional[str] = None
    utr: Optional[str] = None
    credit: Optional[float] = None
    debit: Optional[float] = None


class CaseResult(BaseModel):
    razorpay_settlement_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    bank_transaction_id: Optional[str] = None

    expected_amount: Optional[float] = None
    actual_amount: Optional[float] = None
    difference: Optional[float] = None

    status: str  # ReconciliationStatus
    match_rule: str  # which rule (1-6) resolved this case
    root_cause: Optional[str] = None  # RootCauseCategory, set when EXPLAINED/NEEDS_REVIEW
    notes: str = ""


class ReconciliationInput(BaseModel):
    payments: list[PaymentInput] = []
    settlements: list[SettlementInput] = []
    refunds: list[RefundInput] = []
    bank_rows: list[BankRowInput] = []


class ReconciliationOutput(BaseModel):
    total_cases: int
    matched: int
    explained: int
    needs_review: int
    cases: list[CaseResult]
