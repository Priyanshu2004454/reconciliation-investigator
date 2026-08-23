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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant_account
from app.db.session import get_db
from app.models.financial import RazorpayPayment, RazorpayRefund, RazorpaySettlement, BankTransaction
from app.models.reconciliation import ReconciliationCase
from app.models.users import MerchantAccount
from app.schemas.reconciliation_engine import BankRowInput, PaymentInput, RefundInput, SettlementInput, ReconciliationInput
from app.services.reconciliation_persistence import run_and_persist_reconciliation

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


@router.post("/run", status_code=status.HTTP_201_CREATED)
async def run_reconciliation(
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    payments = (
        await db.execute(select(RazorpayPayment).where(RazorpayPayment.merchant_account_id == merchant.id))
    ).scalars().all()
    settlements = (
        await db.execute(select(RazorpaySettlement).where(RazorpaySettlement.merchant_account_id == merchant.id))
    ).scalars().all()
    refunds = (
        await db.execute(select(RazorpayRefund).where(RazorpayRefund.merchant_account_id == merchant.id))
    ).scalars().all()
    bank_rows = (
        await db.execute(
            select(BankTransaction).where(
                BankTransaction.merchant_account_id == merchant.id,
                BankTransaction.is_duplicate.is_(False),
            )
        )
    ).scalars().all()

    if not settlements:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No settlements found. Sync Razorpay data (POST /razorpay/sync) before running reconciliation.",
        )

    data = ReconciliationInput(
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
                payment_ids=[],  # see module docstring — live linkage not available in Test Mode
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

    run = await run_and_persist_reconciliation(db, merchant.id, data)
    return {
        "run_id": str(run.id),
        "status": run.status,
        "total_transactions": run.total_transactions,
        "matched": run.matched_count,
        "explained": run.explained_count,
        "needs_review": run.needs_review_count,
    }


@router.get("/cases")
async def list_cases(
    status_filter: str | None = None,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ReconciliationCase).where(ReconciliationCase.merchant_account_id == merchant.id)
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
    }
