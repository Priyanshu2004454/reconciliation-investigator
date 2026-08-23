import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from app.ai.client import get_ai_client, AIClientNotConfiguredError
from app.ai.db_data_store import DbInvestigationStore
from app.ai.investigator import (
    investigate_case,
    InvestigationError,
    InvestigationHallucinationError,
    InvestigationTimeoutError,
)
from app.api.deps import get_current_merchant_account, get_current_user
from app.db.session import get_db
from app.models.reconciliation import ReconciliationCase, Investigation, InvestigationEvidence
from app.models.users import MerchantAccount, User
from app.schemas.investigation_api import InvestigationOut, HumanDecisionRequest
from app.services import audit_service

router = APIRouter(prefix="/investigations", tags=["investigations"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/cases/{case_id}/investigate", response_model=InvestigationOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def investigate(
    request: Request,
    case_id: uuid.UUID,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    case = (
        await db.execute(
            select(ReconciliationCase).where(
                ReconciliationCase.id == case_id, ReconciliationCase.merchant_account_id == merchant.id,
            )
        )
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    try:
        client = get_ai_client()
    except AIClientNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    store = DbInvestigationStore(db, merchant.id)

    await audit_service.log_action(
        db, actor_type="AI", action="INVESTIGATION_STARTED", case_id=case.id, actor_id="ai-investigator",
    )

    try:
        run_result = await investigate_case(str(case.id), store, client)
    except InvestigationTimeoutError as exc:
        await audit_service.log_action(
            db, actor_type="AI", action="INVESTIGATION_TIMEOUT", case_id=case.id, reason=str(exc),
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="AI investigation timed out") from exc
    except InvestigationHallucinationError as exc:
        await audit_service.log_action(
            db, actor_type="AI", action="INVESTIGATION_REJECTED_HALLUCINATION", case_id=case.id, reason=str(exc),
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI produced an unverifiable finding and it was rejected. Please retry or review manually.",
        ) from exc
    except InvestigationError as exc:
        await audit_service.log_action(
            db, actor_type="AI", action="INVESTIGATION_FAILED", case_id=case.id, reason=str(exc),
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI investigation failed") from exc

    result = run_result.result
    investigation = Investigation(
        case_id=case.id,
        classification=result.classification,
        root_cause=result.root_cause,
        explanation=result.explanation,
        confidence=result.confidence,
        recommended_action=result.recommended_action,
        requires_human_review=result.requires_human_review,
        ai_model="claude-sonnet-4-6",
        raw_ai_response=run_result.raw_final_input,
        duration_ms=run_result.duration_ms,
    )
    db.add(investigation)
    await db.flush()

    for item in result.evidence:
        db.add(InvestigationEvidence(
            investigation_id=investigation.id,
            source_type=item.source_type,
            source_id=item.source_id,
            description=item.description,
            data_snapshot={},
        ))

    await audit_service.log_action(
        db, actor_type="AI", action="INVESTIGATION_COMPLETED", case_id=case.id, actor_id="ai-investigator",
        new_state={
            "classification": result.classification, "root_cause": result.root_cause,
            "confidence": result.confidence, "tool_calls": len(run_result.tool_calls),
        },
    )

    await db.commit()
    await db.refresh(investigation)
    return investigation


@router.post("/{investigation_id}/decision", response_model=InvestigationOut)
async def submit_human_decision(
    investigation_id: uuid.UUID,
    payload: HumanDecisionRequest,
    current_user: User = Depends(get_current_user),
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime

    investigation = (
        await db.execute(select(Investigation).where(Investigation.id == investigation_id))
    ).scalar_one_or_none()
    if investigation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")

    case = (
        await db.execute(
            select(ReconciliationCase).where(
                ReconciliationCase.id == investigation.case_id, ReconciliationCase.merchant_account_id == merchant.id,
            )
        )
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found for this merchant")

    previous_state = {"case_status": case.status, "human_decision": investigation.human_decision}

    investigation.human_decision = payload.decision
    investigation.human_decided_by = current_user.id
    investigation.human_decided_at = datetime.utcnow()
    investigation.human_notes = payload.notes

    # The AI never resolves a case on its own — only a recorded human decision can.
    if payload.decision == "RESOLVED":
        case.status = "RESOLVED"
    elif payload.decision == "NEEDS_REVIEW":
        case.status = "NEEDS_REVIEW"
    elif payload.decision == "REJECTED":
        case.status = "NEEDS_REVIEW"  # rejecting the AI's finding still needs a human to resolve it

    await audit_service.log_action(
        db, actor_type="HUMAN", action="HUMAN_DECISION_RECORDED", case_id=case.id,
        actor_id=str(current_user.id),
        previous_state=previous_state,
        new_state={"case_status": case.status, "human_decision": payload.decision},
        reason=payload.notes,
    )

    await db.commit()
    await db.refresh(investigation)
    return investigation
