import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from app.ai.client import get_ai_client, AIClientNotConfiguredError
from app.ai.db_data_store import DbInvestigationStore
from app.ai.providers import (
    InvestigationError,
    InvestigationHallucinationError,
    InvestigationTimeoutError,
)
from app.api.deps import get_current_merchant_account, get_current_user
from app.db.session import get_db
from app.models.reconciliation import ReconciliationCase, Investigation, InvestigationEvidence
from app.models.users import MerchantAccount, User
from app.schemas.investigation_api import InvestigationOut, HumanDecisionRequest, EvidenceOut
from app.services import audit_service

router = APIRouter(prefix="/investigations", tags=["investigations"])
limiter = Limiter(key_func=get_remote_address)


async def _load_investigation_with_evidence(db: AsyncSession, investigation: Investigation) -> dict:
    evidence_rows = (
        await db.execute(
            select(InvestigationEvidence).where(InvestigationEvidence.investigation_id == investigation.id)
        )
    ).scalars().all()
    return {
        "id": investigation.id, "case_id": investigation.case_id,
        "classification": investigation.classification, "root_cause": investigation.root_cause,
        "explanation": investigation.explanation, "confidence": investigation.confidence,
        "recommended_action": investigation.recommended_action,
        "requires_human_review": investigation.requires_human_review,
        "human_decision": investigation.human_decision, "human_notes": investigation.human_notes,
        "evidence": [
            EvidenceOut(source_type=e.source_type, source_id=e.source_id, description=e.description)
            for e in evidence_rows
        ],
        "created_at": investigation.created_at,
    }


async def _run_single_investigation(db: AsyncSession, merchant: MerchantAccount, case: ReconciliationCase) -> dict:
    """
    Shared investigation logic used by both the single-case endpoint and the
    batch endpoint. Raises the same InvestigationError family as investigate_case
    itself (or AIClientNotConfiguredError) — callers decide how to surface that
    (HTTP error for the single endpoint, a per-case failure entry for batch).
    """
    client = get_ai_client()
    store = DbInvestigationStore(db, merchant.id)

    await audit_service.log_action(
        db, actor_type="AI", action="INVESTIGATION_STARTED", case_id=case.id, actor_id="ai-investigator",
    )

    run_result = await client.investigate(str(case.id), store)

    result = run_result.result
    investigation = Investigation(
        case_id=case.id,
        classification=result.classification,
        root_cause=result.root_cause,
        explanation=result.explanation,
        confidence=result.confidence,
        recommended_action=result.recommended_action,
        requires_human_review=result.requires_human_review,
        ai_model=run_result.ai_model,
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
    return await _load_investigation_with_evidence(db, investigation)


@router.get("/cases/{case_id}", response_model=InvestigationOut | None)
async def get_latest_investigation_for_case(
    case_id: uuid.UUID,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    """
    NEW in this phase (additive, read-only): lets the frontend show a
    previously-run investigation without re-triggering the AI (which costs
    time and tokens) every time the case detail page loads.
    """
    case = (
        await db.execute(
            select(ReconciliationCase).where(
                ReconciliationCase.id == case_id, ReconciliationCase.merchant_account_id == merchant.id,
            )
        )
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    investigation = (
        await db.execute(
            select(Investigation)
            .where(Investigation.case_id == case_id)
            .order_by(Investigation.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if investigation is None:
        return None
    return await _load_investigation_with_evidence(db, investigation)


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
        return await _run_single_investigation(db, merchant, case)
    except AIClientNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
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


@router.post("/batch-investigate")
async def batch_investigate(
    run_id: uuid.UUID | None = None,
    limit: int = 20,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    """
    Investigates every NEEDS_REVIEW case (optionally scoped to one
    reconciliation run) that doesn't already have an investigation, up to
    `limit` cases per call. Each case is processed independently — one
    case's AI failure (timeout, hallucination, etc.) never stops the batch;
    it's simply recorded as a failure and the batch continues, matching
    section 24's "never crash the whole app over one bad record".
    """
    try:
        get_ai_client()
    except AIClientNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    already_investigated_subq = select(Investigation.case_id).distinct()

    stmt = (
        select(ReconciliationCase)
        .where(
            ReconciliationCase.merchant_account_id == merchant.id,
            ReconciliationCase.status == "NEEDS_REVIEW",
            ReconciliationCase.id.not_in(already_investigated_subq),
        )
        .order_by(ReconciliationCase.created_at.asc())
        .limit(limit)
    )
    if run_id:
        stmt = stmt.where(ReconciliationCase.run_id == run_id)

    cases = (await db.execute(stmt)).scalars().all()

    investigated: list[dict] = []
    failed: list[dict] = []

    for case in cases:
        try:
            result = await _run_single_investigation(db, merchant, case)
            investigated.append({"case_id": str(case.id), "classification": result["classification"]})
        except Exception as exc:  # noqa: BLE001 — one bad case must not stop the batch
            await db.rollback()
            await audit_service.log_action(
                db, actor_type="AI", action="INVESTIGATION_FAILED", case_id=case.id, reason=str(exc),
            )
            await db.commit()
            failed.append({"case_id": str(case.id), "error": str(exc)})

    return {
        "cases_considered": len(cases),
        "investigated": len(investigated),
        "failed": len(failed),
        "results": investigated,
        "failures": failed,
    }


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
    return await _load_investigation_with_evidence(db, investigation)
