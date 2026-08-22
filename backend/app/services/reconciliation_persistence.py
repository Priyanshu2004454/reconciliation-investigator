"""
Bridges the pure, DB-agnostic reconciliation engine (app.services.reconciliation_engine)
to actual database rows. The engine itself never touches SQLAlchemy — this module
is what turns its CaseResult objects into ReconciliationRun / ReconciliationCase
rows and writes the corresponding audit trail.
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reconciliation import ReconciliationRun, ReconciliationCase
from app.schemas.reconciliation_engine import ReconciliationInput
from app.services import audit_service
from app.services.reconciliation_engine import reconcile


async def run_and_persist_reconciliation(
    db: AsyncSession,
    merchant_account_id: uuid.UUID,
    data: ReconciliationInput,
) -> ReconciliationRun:
    run = ReconciliationRun(
        merchant_account_id=merchant_account_id,
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(run)
    await db.flush()  # get run.id

    await audit_service.log_action(
        db, actor_type="SYSTEM", action="RECONCILIATION_RUN_STARTED",
        new_state={"run_id": str(run.id), "settlement_count": len(data.settlements)},
    )

    try:
        result = reconcile(data)
    except Exception as exc:  # noqa: BLE001
        run.status = "FAILED"
        run.finished_at = datetime.utcnow()
        await audit_service.log_action(
            db, actor_type="SYSTEM", action="RECONCILIATION_RUN_FAILED",
            reason=str(exc), new_state={"run_id": str(run.id)},
        )
        await db.commit()
        raise

    for case in result.cases:
        case_row = ReconciliationCase(
            run_id=run.id,
            merchant_account_id=merchant_account_id,
            razorpay_settlement_id=case.razorpay_settlement_id,
            razorpay_payment_id=case.razorpay_payment_id,
            bank_transaction_id=uuid.UUID(case.bank_transaction_id) if case.bank_transaction_id else None,
            expected_amount=case.expected_amount,
            actual_amount=case.actual_amount,
            difference=case.difference,
            status=case.status,
            match_rule=case.match_rule,
        )
        db.add(case_row)
        await db.flush()  # get case_row.id

        await audit_service.log_action(
            db, actor_type="SYSTEM", action="RECONCILIATION_CASE_CREATED",
            case_id=case_row.id,
            new_state={
                "status": case.status,
                "match_rule": case.match_rule,
                "root_cause": case.root_cause,
                "difference": case.difference,
            },
            reason=case.notes or None,
        )

    run.finished_at = datetime.utcnow()
    run.total_transactions = result.total_cases
    run.matched_count = result.matched
    run.explained_count = result.explained
    run.needs_review_count = result.needs_review
    run.status = "COMPLETED"

    await audit_service.log_action(
        db, actor_type="SYSTEM", action="RECONCILIATION_RUN_COMPLETED",
        new_state={
            "run_id": str(run.id),
            "matched": result.matched,
            "explained": result.explained,
            "needs_review": result.needs_review,
        },
    )

    await db.commit()
    await db.refresh(run)
    return run
