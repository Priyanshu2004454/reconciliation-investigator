"""
Every meaningful state change in the system goes through this module.
This is intentionally the ONLY place that writes to `audit_logs`, so the
audit trail can't accidentally be bypassed by a route or service forgetting
to log something.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    actor_type: str,  # "AI" | "HUMAN" | "SYSTEM"
    action: str,
    case_id: Optional[uuid.UUID] = None,
    actor_id: Optional[str] = None,
    previous_state: Optional[dict] = None,
    new_state: Optional[dict] = None,
    reason: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        case_id=case_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        previous_state=previous_state,
        new_state=new_state,
        reason=reason,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    await db.flush()  # get entry.id without committing the whole transaction yet
    return entry
