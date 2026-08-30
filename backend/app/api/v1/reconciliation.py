"""
KNOWN LIMITATION (documented per section 37 — explain, don't invent):
Razorpay's Test Mode API does not expose which specific payments were batched
into a given settlement (that mapping requires the enterprise Settlement
Recon Report, out of scope for this MVP per section 30). This means for
*live-synced* settlements, `payment_ids` is empty and Rules 4/5 (fee/tax and
refund explanations) won't fire — only Rules 1/2/3/6 apply. Seeded demo data
(section 21) sets this linkage explicitly so the full rule set is demonstrable.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant_account, get_current_user
from app.db.session import get_db
from app.models.financial import RazorpayPayment, RazorpayRefund, RazorpaySettlement, BankTransaction
from app.models.reconciliation import ReconciliationCase, ReconciliationRun, Investigation
from app.models.users import MerchantAccount, User
from app.schemas.dashboard import ExceptionCaseOut, ReconciliationRunOut
from app.schemas.financial import DemoSeedResponse
from app.schemas.reconciliation_engine import BankRowInput, PaymentInput, RefundInput, SettlementInput, ReconciliationInput
from app.seed_demo import seed_merchant_demo_dataset
from app.services.reconciliation_persistence import run_and_persist_reconciliation

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


async def _build_reconciliation_input(db: AsyncSession, merchant_id: uuid.UUID) -> ReconciliationInput:
    payments = (
        await db.execute(select(RazorpayPayment).where(RazorpayPayment.merchant_account_id == merchant_id))
    ).scalars().all()
    settlements = (
        await db.execute(select(RazorpaySettlement).where(RazorpaySettlement.merchant_account_id == merchant_id))
    ).scalars().all()
    refunds = (
        await db.execute(select(RazorpayRefund).where(RazorpayRefund.merchant_account_id == merchant_id))
    ).scalars().all()
    bank_rows = (
        await db.execute(
            select(BankTransaction).where(
                BankTransaction.merchant_account_id == merchant_id,
                BankTransaction.is_duplicate.is_(False),
            )
        )
    ).scalars().all()

    if not settlements:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No settlements found. Sync Razorpay data (POST /razorpay/sync) or run the demo seed before running reconciliation.",
        )

    def _linked_payment_ids(settlement: RazorpaySettlement) -> list[str]:
        # See module docstring in the original limitation note: live Test Mode
        # settlements don't carry payment linkage. Seeded demo data embeds a
        # "linked_payment_id" key in raw_payload specifically so Rules 4/5 can
        # be demonstrated — real synced settlements never have this key, so
        # this is a no-op for live data (payment_ids stays []).
        linked = (settlement.raw_payload or {}).get("linked_payment_id")
        return [linked] if linked else []

    return ReconciliationInput(
        payments=[
            PaymentInput(razorpay_payment_id=p.razorpay_payment_id, amount=float(p.amount),
                         fee=float(p.fee or 0), tax=float(p.tax or 0), status=p.status)
            for p in payments
        ],
        refunds=[
            RefundInput(razorpay_refund_id=r.razorpay_refund_id, razorpay_payment_id=r.razorpay_payment_id,
                        amount=float(r.amount), status=r.status)
            for r in refunds
        ],
        settlements=[
            SettlementInput(
                razorpay_settlement_id=s.razorpay_settlement_id, utr=s.utr, amount=float(s.amount),
                fees=float(s.fees or 0), tax=float(s.tax or 0), status=s.status,
                settlement_date=s.settlement_date.date(),
                payment_ids=_linked_payment_ids(s),
            )
            for s in settlements
        ],
        bank_rows=[
            BankRowInput(id=str(b.id), transaction_date=b.transaction_date, reference_id=b.reference_id,
                         utr=b.utr, credit=float(b.credit) if b.credit is not None else None,
                         debit=float(b.debit) if b.debit is not None else None)
            for b in bank_rows
        ],
    )


def _run_to_dict(run: ReconciliationRun) -> dict:
    return {
        "run_id": str(run.id),
        "status": run.status,
        "total_transactions": run.total_transactions,
        "matched": run.matched_count,
        "explained": run.explained_count,
        "needs_review": run.needs_review_count,
    }


def _run_to_out(run: ReconciliationRun) -> ReconciliationRunOut:
    return ReconciliationRunOut(
        id=str(run.id),
        status=run.status,
        total_records=run.total_transactions,
        matched_records=run.matched_count,
        explained_records=run.explained_count,
        unresolved_records=run.needs_review_count,
        failed_records=run.failed_count,
        total_amount=float(run.total_amount or 0),
        matched_amount=float(run.matched_amount or 0),
        unresolved_amount=float(run.unresolved_amount or 0),
        match_rate=float(run.match_rate or 0),
        started_at=run.started_at,
        completed_at=run.finished_at,
    )


@router.post("/seed-demo", response_model=DemoSeedResponse, status_code=status.HTTP_201_CREATED)
async def seed_demo_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Seeds the reproducible 100-record synthetic dataset for the currently
    authenticated user. If no merchant account exists yet, automatically
    initializes a demo merchant account so judges/users can test reconciliation
    immediately without manually connecting a Razorpay key.
    """
    account = (
        await db.execute(select(MerchantAccount).where(MerchantAccount.owner_id == current_user.id))
    ).scalars().first()

    if account is None:
        account = MerchantAccount(
            owner_id=current_user.id,
            business_name="Demo Ledger Pvt Ltd",
            razorpay_key_id="rzp_test_demo0000000000",
            is_test_mode=True,
        )
        db.add(account)
        await db.flush()

    summary = await seed_merchant_demo_dataset(db, account.id)
    return DemoSeedResponse(**summary)


@router.post("/run", status_code=status.HTTP_201_CREATED)
async def run_reconciliation(
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    """Legacy endpoint, kept for backward compatibility. See POST /reconciliation/runs
    for the Track-04 batch-run endpoint with full amount/match-rate metrics."""
    data = await _build_reconciliation_input(db, merchant.id)
    run = await run_and_persist_reconciliation(db, merchant.id, data)
    return _run_to_dict(run)


@router.post("/runs", response_model=ReconciliationRunOut, status_code=status.HTTP_201_CREATED)
async def run_batch_reconciliation(
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    """
    Runs the deterministic engine across every payment/settlement/refund/bank
    row currently stored for this merchant (Razorpay-synced and/or seeded
    demo data) and persists full batch metrics: total/matched/unresolved
    amounts and match rate. The backend is the sole source of truth for these
    numbers — the frontend never recomputes them.
    """
    data = await _build_reconciliation_input(db, merchant.id)
    run = await run_and_persist_reconciliation(db, merchant.id, data)
    return _run_to_out(run)


@router.get("/runs", response_model=list[ReconciliationRunOut])
async def list_reconciliation_runs(
    limit: int = 20,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    runs = (
        await db.execute(
            select(ReconciliationRun)
            .where(ReconciliationRun.merchant_account_id == merchant.id)
            .order_by(ReconciliationRun.started_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [_run_to_out(r) for r in runs]


@router.get("/runs/{run_id}", response_model=ReconciliationRunOut)
async def get_reconciliation_run(
    run_id: uuid.UUID,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    run = (
        await db.execute(
            select(ReconciliationRun).where(
                ReconciliationRun.id == run_id, ReconciliationRun.merchant_account_id == merchant.id,
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return _run_to_out(run)


@router.get("/exceptions", response_model=list[ExceptionCaseOut])
async def list_exceptions(
    run_id: uuid.UUID | None = None,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    """
    Cases the deterministic engine could not cleanly resolve (NEEDS_REVIEW),
    joined with the latest AI investigation (if one has run) so the merchant
    sees mismatch type, confidence, and recommended action in one list
    without opening every case individually.
    """
    latest_investigation_subq = (
        select(
            Investigation.case_id,
            Investigation.root_cause,
            Investigation.confidence,
            Investigation.recommended_action,
            func.max(Investigation.created_at).label("max_created"),
        )
        .group_by(Investigation.case_id, Investigation.root_cause, Investigation.confidence, Investigation.recommended_action)
        .subquery()
    )

    target_run_id = run_id
    if target_run_id is None:
        target_run_id = (
            await db.execute(
                select(ReconciliationRun.id)
                .where(ReconciliationRun.merchant_account_id == merchant.id)
                .order_by(ReconciliationRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    if target_run_id is None:
        return []

    stmt = (
        select(ReconciliationCase, latest_investigation_subq.c.root_cause,
               latest_investigation_subq.c.confidence, latest_investigation_subq.c.recommended_action)
        .outerjoin(latest_investigation_subq, latest_investigation_subq.c.case_id == ReconciliationCase.id)
        .where(
            ReconciliationCase.merchant_account_id == merchant.id,
            ReconciliationCase.run_id == target_run_id,
            ReconciliationCase.status == "NEEDS_REVIEW",
        )
    )
    stmt = stmt.order_by(ReconciliationCase.created_at.desc())

    rows = (await db.execute(stmt)).all()
    return [
        ExceptionCaseOut(
            case_id=str(row.ReconciliationCase.id),
            razorpay_payment_id=row.ReconciliationCase.razorpay_payment_id,
            razorpay_settlement_id=row.ReconciliationCase.razorpay_settlement_id,
            amount=float(row.ReconciliationCase.actual_amount) if row.ReconciliationCase.actual_amount is not None else None,
            status=row.ReconciliationCase.status,
            mismatch_type=row.root_cause,
            confidence=row.confidence,
            recommended_action=row.recommended_action,
            created_at=row.ReconciliationCase.created_at,
        )
        for row in rows
    ]


@router.get("/cases")
async def list_cases(
    status_filter: str | None = None,
    run_id: uuid.UUID | None = None,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    target_run_id = run_id
    if target_run_id is None:
        target_run_id = (
            await db.execute(
                select(ReconciliationRun.id)
                .where(ReconciliationRun.merchant_account_id == merchant.id)
                .order_by(ReconciliationRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    if target_run_id is None:
        return []

    stmt = select(ReconciliationCase).where(
        ReconciliationCase.merchant_account_id == merchant.id,
        ReconciliationCase.run_id == target_run_id,
    )
    if status_filter:
        stmt = stmt.where(ReconciliationCase.status == status_filter)
    stmt = stmt.order_by(ReconciliationCase.updated_at.desc())

    cases = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(c.id),
            "razorpay_settlement_id": c.razorpay_settlement_id,
            "status": c.status,
            "match_rule": c.match_rule,
            "expected_amount": float(c.expected_amount) if c.expected_amount is not None else None,
            "actual_amount": float(c.actual_amount) if c.actual_amount is not None else None,
            "difference": float(c.difference) if c.difference is not None else None,
            "updated_at": c.updated_at,
        }
        for c in cases
    ]


@router.get("/cases/{case_id}")
async def get_case(
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

    settlement = None
    if case.razorpay_settlement_id:
        settlement = (
            await db.execute(
                select(RazorpaySettlement).where(
                    RazorpaySettlement.merchant_account_id == merchant.id,
                    RazorpaySettlement.razorpay_settlement_id == case.razorpay_settlement_id,
                )
            )
        ).scalar_one_or_none()

    payment = None
    if case.razorpay_payment_id:
        payment = (
            await db.execute(
                select(RazorpayPayment).where(
                    RazorpayPayment.merchant_account_id == merchant.id,
                    RazorpayPayment.razorpay_payment_id == case.razorpay_payment_id,
                )
            )
        ).scalar_one_or_none()

    bank_txn = None
    if case.bank_transaction_id:
        bank_txn = (
            await db.execute(
                select(BankTransaction).where(
                    BankTransaction.merchant_account_id == merchant.id,
                    BankTransaction.id == case.bank_transaction_id,
                )
            )
        ).scalar_one_or_none()

    refunds = []
    if case.razorpay_payment_id:
        refund_rows = (
            await db.execute(
                select(RazorpayRefund).where(
                    RazorpayRefund.merchant_account_id == merchant.id,
                    RazorpayRefund.razorpay_payment_id == case.razorpay_payment_id,
                )
            )
        ).scalars().all()
        refunds = [
            {
                "id": str(r.id),
                "razorpay_refund_id": r.razorpay_refund_id,
                "amount": float(r.amount),
                "status": r.status,
                "refund_date": r.refund_date.isoformat() if r.refund_date else None,
            }
            for r in refund_rows
        ]

    return {
        "id": str(case.id),
        "razorpay_settlement_id": case.razorpay_settlement_id,
        "razorpay_payment_id": case.razorpay_payment_id,
        "bank_transaction_id": str(case.bank_transaction_id) if case.bank_transaction_id else None,
        "status": case.status,
        "match_rule": case.match_rule,
        "expected_amount": float(case.expected_amount) if case.expected_amount is not None else None,
        "actual_amount": float(case.actual_amount) if case.actual_amount is not None else None,
        "difference": float(case.difference) if case.difference is not None else None,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "settlement_details": {
            "utr": settlement.utr if settlement else None,
            "amount": float(settlement.amount) if settlement and settlement.amount is not None else None,
            "fees": float(settlement.fees) if settlement and settlement.fees is not None else None,
            "tax": float(settlement.tax) if settlement and settlement.tax is not None else None,
            "status": settlement.status if settlement else None,
            "settlement_date": settlement.settlement_date.isoformat() if settlement and settlement.settlement_date else None,
        } if settlement else None,
        "payment_details": {
            "amount": float(payment.amount) if payment and payment.amount is not None else None,
            "fee": float(payment.fee) if payment and payment.fee is not None else None,
            "tax": float(payment.tax) if payment and payment.tax is not None else None,
            "method": payment.method if payment else None,
            "status": payment.status if payment else None,
            "payment_date": payment.payment_date.isoformat() if payment and payment.payment_date else None,
        } if payment else None,
        "bank_transaction_details": {
            "utr": bank_txn.utr if bank_txn else None,
            "reference_id": bank_txn.reference_id if bank_txn else None,
            "credit": float(bank_txn.credit) if bank_txn and bank_txn.credit is not None else None,
            "debit": float(bank_txn.debit) if bank_txn and bank_txn.debit is not None else None,
            "transaction_date": bank_txn.transaction_date.isoformat() if bank_txn and bank_txn.transaction_date else None,
            "description": bank_txn.description if bank_txn else None,
        } if bank_txn else None,
        "refunds": refunds,
    }
