import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant_account
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.reconciliation import ReconciliationCase
from app.models.users import MerchantAccount

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    case_id: uuid.UUID | None = None,
    limit: int = 100,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    """
    Read-only. There is deliberately no PATCH/DELETE route for audit_logs
    anywhere in this API — the audit trail is immutable from the normal UI
    (section 15), and can only be entered via app.services.audit_service.
    """
    stmt = (
        select(AuditLog)
        .join(ReconciliationCase, ReconciliationCase.id == AuditLog.case_id, isouter=True)
        .where(
            (ReconciliationCase.merchant_account_id == merchant.id) | (AuditLog.case_id.is_(None))
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    if case_id:
        stmt = stmt.where(AuditLog.case_id == case_id)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id), "case_id": str(r.case_id) if r.case_id else None,
            "actor_type": r.actor_type, "actor_id": r.actor_id, "action": r.action,
            "previous_state": r.previous_state, "new_state": r.new_state,
            "reason": r.reason, "created_at": r.created_at,
        }
        for r in rows
    ]
