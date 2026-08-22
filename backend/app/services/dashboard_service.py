import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reconciliation import ReconciliationCase, ReconciliationRun
from app.schemas.dashboard import DashboardSummary, MismatchCategoryBreakdown, RecentActivityItem


async def get_dashboard_summary(db: AsyncSession, merchant_account_id: uuid.UUID) -> DashboardSummary:
    base_filter = ReconciliationCase.merchant_account_id == merchant_account_id

    counts_stmt = (
        select(ReconciliationCase.status, func.count())
        .where(base_filter)
        .group_by(ReconciliationCase.status)
    )
    counts_result = await db.execute(counts_stmt)
    counts_by_status = {status: count for status, count in counts_result.all()}

    total = sum(counts_by_status.values())
    matched = counts_by_status.get("MATCHED", 0)
    explained = counts_by_status.get("EXPLAINED", 0)
    needs_review = counts_by_status.get("NEEDS_REVIEW", 0)

    reconciliation_rate = round(((matched + explained) / total) * 100, 2) if total else 0.0

    processed_value_stmt = select(func.coalesce(func.sum(ReconciliationCase.actual_amount), 0)).where(base_filter)
    processed_value = float((await db.execute(processed_value_stmt)).scalar_one())

    review_amount_stmt = (
        select(func.coalesce(func.sum(ReconciliationCase.actual_amount), 0))
        .where(base_filter, ReconciliationCase.status == "NEEDS_REVIEW")
    )
    amount_requiring_investigation = float((await db.execute(review_amount_stmt)).scalar_one())

    last_run_stmt = (
        select(ReconciliationRun)
        .where(ReconciliationRun.merchant_account_id == merchant_account_id)
        .order_by(ReconciliationRun.started_at.desc())
        .limit(1)
    )
    last_run = (await db.execute(last_run_stmt)).scalar_one_or_none()

    return DashboardSummary(
        total_transactions=total,
        processed_value=processed_value,
        total_settlements=total,  # in this MVP one case == one settlement
        matched_count=matched,
        explained_count=explained,
        needs_review_count=needs_review,
        reconciliation_rate=reconciliation_rate,
        amount_requiring_investigation=amount_requiring_investigation,
        last_run_at=last_run.started_at if last_run else None,
        last_run_status=last_run.status if last_run else None,
    )


async def get_recent_activity(db: AsyncSession, merchant_account_id: uuid.UUID, limit: int = 10) -> list[RecentActivityItem]:
    stmt = (
        select(ReconciliationCase)
        .where(ReconciliationCase.merchant_account_id == merchant_account_id)
        .order_by(ReconciliationCase.updated_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        RecentActivityItem(
            case_id=str(row.id),
            razorpay_settlement_id=row.razorpay_settlement_id,
            status=row.status,
            root_cause=None,  # populated from the latest Investigation, joined at the API layer if needed
            amount=float(row.actual_amount) if row.actual_amount is not None else None,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


async def get_mismatch_breakdown(db: AsyncSession, merchant_account_id: uuid.UUID) -> list[MismatchCategoryBreakdown]:
    """
    Top mismatch categories (section 19). Root cause lives on Investigation, not
    ReconciliationCase, so this joins through investigations for NEEDS_REVIEW /
    EXPLAINED cases.
    """
    from app.models.reconciliation import Investigation

    stmt = (
        select(Investigation.root_cause, func.count(), func.coalesce(func.sum(ReconciliationCase.actual_amount), 0))
        .join(ReconciliationCase, ReconciliationCase.id == Investigation.case_id)
        .where(ReconciliationCase.merchant_account_id == merchant_account_id)
        .group_by(Investigation.root_cause)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        MismatchCategoryBreakdown(category=root_cause, count=count, total_amount=float(total))
        for root_cause, count, total in rows
    ]
