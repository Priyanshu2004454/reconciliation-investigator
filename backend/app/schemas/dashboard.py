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
    reconciliation_rate: float  # percentage, e.g. 99.3
    amount_requiring_investigation: float
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
