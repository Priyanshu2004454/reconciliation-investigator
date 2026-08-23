from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant_account
from app.db.session import get_db
from app.models.users import MerchantAccount
from app.schemas.dashboard import DashboardSummary, MismatchCategoryBreakdown, RecentActivityItem
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_dashboard_summary(db, merchant.id)


@router.get("/recent-activity", response_model=list[RecentActivityItem])
async def get_recent_activity(
    limit: int = 10,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_recent_activity(db, merchant.id, limit)


@router.get("/mismatch-breakdown", response_model=list[MismatchCategoryBreakdown])
async def get_mismatch_breakdown(
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_mismatch_breakdown(db, merchant.id)
