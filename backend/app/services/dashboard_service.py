import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reconciliation import ReconciliationCase, ReconciliationRun, Investigation
from app.schemas.dashboard import DashboardSummary, MismatchCategoryBreakdown, RecentActivityItem


async def get_dashboard_summary(db: AsyncSession, merchant_account_id: uuid.UUID) -> DashboardSummary:
    last_run_stmt = (
        select(ReconciliationRun)
        .where(ReconciliationRun.merchant_account_id == merchant_account_id)
        .order_by(ReconciliationRun.started_at.desc())
        .limit(1)
    )
    last_run = (await db.execute(last_run_stmt)).scalar_one_or_none()

    if last_run is None:
        return DashboardSummary(
            total_transactions=0,
            processed_value=0.0,
            total_settlements=0,
            matched_count=0,
            explained_count=0,
            needs_review_count=0,
            resolved_count=0,
            reconciliation_rate=0.0,
            amount_requiring_investigation=0.0,
            ai_investigation_rate=0.0,
            human_review_rate=0.0,
            avg_investigation_time_ms=None,
            last_run_at=None,
            last_run_status=None,
        )

    base_filter = (
        (ReconciliationCase.merchant_account_id == merchant_account_id)
        & (ReconciliationCase.run_id == last_run.id)
    )

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
    resolved = counts_by_status.get("RESOLVED", 0)

    reconciliation_rate = round(((matched + explained) / total) * 100, 2) if total else 0.0

    processed_value_stmt = select(func.coalesce(func.sum(ReconciliationCase.actual_amount), 0)).where(base_filter)
    processed_value = float((await db.execute(processed_value_stmt)).scalar_one())

    review_amount_stmt = (
        select(func.coalesce(func.sum(ReconciliationCase.actual_amount), 0))
        .where(base_filter, ReconciliationCase.status == "NEEDS_REVIEW")
    )
    amount_requiring_investigation = float((await db.execute(review_amount_stmt)).scalar_one())

    # AI investigation rate: of the cases in this run needing review,
    # how many have had an investigation run?
    investigated_case_ids_stmt = (
        select(Investigation.case_id)
        .join(ReconciliationCase, ReconciliationCase.id == Investigation.case_id)
        .where(base_filter)
        .distinct()
    )
    investigated_case_ids = {row[0] for row in (await db.execute(investigated_case_ids_stmt)).all()}
    needing_investigation_denominator = needs_review + len(investigated_case_ids)
    ai_investigation_rate = (
        round((len(investigated_case_ids) / needing_investigation_denominator) * 100, 2)
        if needing_investigation_denominator else 0.0
    )

    # Human review rate: of all investigations for this run, how many
    # received an explicit human decision (Resolve/Needs Review/Reject)?
    investigation_counts_stmt = (
        select(func.count(), func.count(Investigation.human_decision))
        .join(ReconciliationCase, ReconciliationCase.id == Investigation.case_id)
        .where(base_filter)
    )
    total_investigations, decided_investigations = (await db.execute(investigation_counts_stmt)).one()
    human_review_rate = (
        round((decided_investigations / total_investigations) * 100, 2) if total_investigations else 0.0
    )

    avg_duration_stmt = (
        select(func.avg(Investigation.duration_ms))
        .join(ReconciliationCase, ReconciliationCase.id == Investigation.case_id)
        .where(base_filter, Investigation.duration_ms.is_not(None))
    )
    avg_investigation_time_ms = (await db.execute(avg_duration_stmt)).scalar_one()

    return DashboardSummary(
        total_transactions=total,
        processed_value=processed_value,
        total_settlements=total,
        matched_count=matched,
        explained_count=explained,
        needs_review_count=needs_review,
        resolved_count=resolved,
        reconciliation_rate=reconciliation_rate,
        amount_requiring_investigation=amount_requiring_investigation,
        ai_investigation_rate=ai_investigation_rate,
        human_review_rate=human_review_rate,
        avg_investigation_time_ms=float(avg_investigation_time_ms) if avg_investigation_time_ms is not None else None,
        last_run_at=last_run.started_at,
        last_run_status=last_run.status,
    )


async def get_recent_activity(db: AsyncSession, merchant_account_id: uuid.UUID, limit: int = 10) -> list[RecentActivityItem]:
    last_run_id_stmt = (
        select(ReconciliationRun.id)
        .where(ReconciliationRun.merchant_account_id == merchant_account_id)
        .order_by(ReconciliationRun.started_at.desc())
        .limit(1)
    )
    last_run_id = (await db.execute(last_run_id_stmt)).scalar_one_or_none()

    if last_run_id is None:
        return []

    # Latest investigation per case, joined so recent activity can show root cause
    # without an N+1 query per row.
    latest_investigation_subq = (
        select(Investigation.case_id, Investigation.root_cause, func.max(Investigation.created_at).label("max_created"))
        .group_by(Investigation.case_id, Investigation.root_cause)
        .subquery()
    )

    stmt = (
        select(ReconciliationCase, latest_investigation_subq.c.root_cause)
        .outerjoin(latest_investigation_subq, latest_investigation_subq.c.case_id == ReconciliationCase.id)
        .where(
            ReconciliationCase.merchant_account_id == merchant_account_id,
            ReconciliationCase.run_id == last_run_id,
        )
        .order_by(ReconciliationCase.updated_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        RecentActivityItem(
            case_id=str(row.ReconciliationCase.id),
            razorpay_settlement_id=row.ReconciliationCase.razorpay_settlement_id,
            status=row.ReconciliationCase.status,
            root_cause=row.root_cause,
            amount=float(row.ReconciliationCase.actual_amount) if row.ReconciliationCase.actual_amount is not None else None,
            updated_at=row.ReconciliationCase.updated_at,
        )
        for row in rows
    ]


async def get_mismatch_breakdown(db: AsyncSession, merchant_account_id: uuid.UUID) -> list[MismatchCategoryBreakdown]:
    """
    Top mismatch categories (section 19) for the latest reconciliation run.
    """
    last_run_id_stmt = (
        select(ReconciliationRun.id)
        .where(ReconciliationRun.merchant_account_id == merchant_account_id)
        .order_by(ReconciliationRun.started_at.desc())
        .limit(1)
    )
    last_run_id = (await db.execute(last_run_id_stmt)).scalar_one_or_none()

    if last_run_id is None:
        return []

    stmt = (
        select(Investigation.root_cause, func.count(), func.coalesce(func.sum(ReconciliationCase.actual_amount), 0))
        .join(ReconciliationCase, ReconciliationCase.id == Investigation.case_id)
        .where(
            ReconciliationCase.merchant_account_id == merchant_account_id,
            ReconciliationCase.run_id == last_run_id,
        )
        .group_by(Investigation.root_cause)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        MismatchCategoryBreakdown(category=root_cause, count=count, total_amount=float(total))
        for root_cause, count, total in rows
    ]
