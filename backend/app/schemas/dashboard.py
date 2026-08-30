from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_transactions: int
    processed_value: float
    total_settlements: int
    matched_count: int
    explained_count: int
    needs_review_count: int
    resolved_count: int
    reconciliation_rate: float  # percentage, e.g. 99.3
    amount_requiring_investigation: float
    ai_investigation_rate: float  # % of NEEDS_REVIEW cases that have been investigated at least once
    human_review_rate: float  # % of investigations that received a human decision
    avg_investigation_time_ms: Optional[float] = None
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None


class RecentActivityItem(BaseModel):
    case_id: str
    razorpay_settlement_id: Optional[str] = None
    status: str
    root_cause: Optional[str] = None
    amount: Optional[float] = None
    updated_at: datetime


class MismatchCategoryBreakdown(BaseModel):
    category: str  # RootCauseCategory
    count: int
    total_amount: float


class ReconciliationRunOut(BaseModel):
    id: str
    status: str
    total_records: int
    matched_records: int
    explained_records: int
    unresolved_records: int
    failed_records: int
    total_amount: float
    matched_amount: float
    unresolved_amount: float
    match_rate: float
    started_at: datetime
    completed_at: Optional[datetime] = None


class ExceptionCaseOut(BaseModel):
    case_id: str
    razorpay_payment_id: Optional[str] = None
    razorpay_settlement_id: Optional[str] = None
    amount: Optional[float] = None
    status: str
    mismatch_type: Optional[str] = None  # root_cause from latest investigation, if any
    confidence: Optional[float] = None
    recommended_action: Optional[str] = None
    created_at: datetime
