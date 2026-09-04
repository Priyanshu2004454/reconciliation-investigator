import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.data_store import InvestigationDataStore
from app.models.financial import RazorpayPayment, RazorpaySettlement, RazorpayRefund, BankTransaction
from app.models.reconciliation import ReconciliationCase
from app.services.reconciliation_engine import calculate_expected_settlement as _calc
from app.schemas.reconciliation_engine import PaymentInput, RefundInput


class DbInvestigationStore(InvestigationDataStore):

    def __init__(self, db: AsyncSession, merchant_account_id: uuid.UUID):
        self.db = db
        self.merchant_account_id = merchant_account_id

    async def get_payment(self, payment_id: str) -> Optional[dict]:
        row = (
            await self.db.execute(
                select(RazorpayPayment).where(
                    RazorpayPayment.razorpay_payment_id == payment_id,
                    RazorpayPayment.merchant_account_id == self.merchant_account_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "razorpay_payment_id": row.razorpay_payment_id, "order_id": row.order_id,
            "amount": float(row.amount), "currency": row.currency, "status": row.status,
            "method": row.method, "fee": float(row.fee or 0), "tax": float(row.tax or 0),
            "payment_date": row.payment_date.isoformat(),
        }

    async def get_settlement(self, settlement_id: str) -> Optional[dict]:
        row = (
            await self.db.execute(
                select(RazorpaySettlement).where(
                    RazorpaySettlement.razorpay_settlement_id == settlement_id,
                    RazorpaySettlement.merchant_account_id == self.merchant_account_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "razorpay_settlement_id": row.razorpay_settlement_id, "utr": row.utr,
            "amount": float(row.amount), "fees": float(row.fees or 0), "tax": float(row.tax or 0),
            "status": row.status, "settlement_date": row.settlement_date.isoformat(),
        }

    async def get_refunds(self, payment_id: str) -> list[dict]:
        rows = (
            await self.db.execute(
                select(RazorpayRefund).where(
                    RazorpayRefund.razorpay_payment_id == payment_id,
                    RazorpayRefund.merchant_account_id == self.merchant_account_id,
                )
            )
        ).scalars().all()
        return [
            {"razorpay_refund_id": r.razorpay_refund_id, "razorpay_payment_id": r.razorpay_payment_id,
             "amount": float(r.amount), "status": r.status, "refund_date": r.refund_date.isoformat()}
            for r in rows
        ]

    async def search_bank_transactions(
        self, utr=None, reference_id=None, amount=None, date_from=None, date_to=None,
    ) -> list[dict]:
        from datetime import date, datetime

        stmt = select(BankTransaction).where(
            BankTransaction.merchant_account_id == self.merchant_account_id,
            BankTransaction.is_duplicate.is_(False),
        )
        if utr:
            stmt = stmt.where(BankTransaction.utr == utr)
        if reference_id:
            stmt = stmt.where(BankTransaction.reference_id == reference_id)
        if amount is not None:
            stmt = stmt.where(BankTransaction.credit == amount)
        if date_from:
            if isinstance(date_from, str):
                try:
                    date_from = date.fromisoformat(date_from.split("T")[0])
                except Exception:
                    pass
            stmt = stmt.where(BankTransaction.transaction_date >= date_from)
        if date_to:
            if isinstance(date_to, str):
                try:
                    date_to = date.fromisoformat(date_to.split("T")[0])
                except Exception:
                    pass
            stmt = stmt.where(BankTransaction.transaction_date <= date_to)

        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            {"id": str(b.id), "transaction_date": b.transaction_date.isoformat(), "description": b.description,
             "reference_id": b.reference_id, "utr": b.utr,
             "credit": float(b.credit) if b.credit is not None else None,
             "debit": float(b.debit) if b.debit is not None else None}
            for b in rows
        ]

    async def get_reconciliation_case(self, case_id: str) -> Optional[dict]:
        try:
            case_uuid = uuid.UUID(case_id)
        except ValueError:
            return None
        row = (
            await self.db.execute(
                select(ReconciliationCase).where(
                    ReconciliationCase.id == case_uuid,
                    ReconciliationCase.merchant_account_id == self.merchant_account_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        # NOTE: payment_ids reflects the single-payment linkage available on this
        # MVP's case model (see reconciliation.py's module docstring for the
        # documented limitation around live settlement->payment batching).
        payment_ids = [row.razorpay_payment_id] if row.razorpay_payment_id else []
        return {
            "id": str(row.id), "razorpay_settlement_id": row.razorpay_settlement_id,
            "razorpay_payment_id": row.razorpay_payment_id, "status": row.status,
            "match_rule": row.match_rule, "payment_ids": payment_ids,
        }

    async def calculate_expected_settlement(self, case_id: str) -> Optional[float]:
        case = await self.get_reconciliation_case(case_id)
        if not case:
            return None
        payments, refunds = [], []
        for pid in case["payment_ids"]:
            p = await self.get_payment(pid)
            if p:
                payments.append(PaymentInput(**p))
                for r in await self.get_refunds(pid):
                    refunds.append(RefundInput(**r))
        return _calc(payments, refunds)

    async def mark_case_for_review(self, case_id: str, reason: str) -> bool:
        try:
            case_uuid = uuid.UUID(case_id)
        except ValueError:
            return False
        row = (
            await self.db.execute(
                select(ReconciliationCase).where(
                    ReconciliationCase.id == case_uuid,
                    ReconciliationCase.merchant_account_id == self.merchant_account_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.status = "NEEDS_REVIEW"
        await self.db.flush()
        return True
