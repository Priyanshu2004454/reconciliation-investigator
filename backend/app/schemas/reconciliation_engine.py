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
    payment_ids: list[str] = []  


class BankRowInput(BaseModel):
    id: str  
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

    status: str  
    match_rule: str  
    root_cause: Optional[str] = None  
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
