"""
Persists app.services.demo_dataset's synthetic dataset into the database
under a dedicated demo merchant account. Idempotent: every entity is keyed
by a deterministic external ID (pay_demo0001, setl_demo0001, ...), so
re-running this updates existing rows instead of creating duplicates.

Run with:
    python -m app.seed_demo
"""

import asyncio
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.financial import RazorpayPayment, RazorpaySettlement, RazorpayRefund, BankTransaction
from app.models.users import User, MerchantAccount
from app.services.demo_dataset import generate_dataset, BASE_DATE

DEMO_EMAIL = "demo@reconciliation-investigator.local"
DEMO_PASSWORD = "DemoPassword123!"
DEMO_BATCH_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "reconciliation-investigator-demo-seed")


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)


async def _get_or_create_demo_merchant(db: AsyncSession) -> MerchantAccount:
    user = (await db.execute(select(User).where(User.email == DEMO_EMAIL))).scalar_one_or_none()
    if user is None:
        user = User(email=DEMO_EMAIL, hashed_password=hash_password(DEMO_PASSWORD), full_name="Demo Merchant")
        db.add(user)
        await db.flush()

    account = (
        await db.execute(select(MerchantAccount).where(MerchantAccount.owner_id == user.id))
    ).scalars().first()
    if account is None:
        account = MerchantAccount(
            owner_id=user.id, business_name="Demo Ledger Pvt Ltd",
            razorpay_key_id="rzp_test_demo0000000000", is_test_mode=True,
        )
        db.add(account)
        await db.flush()
    return account


from app.services import audit_service


async def _upsert_payment(db: AsyncSession, merchant_id: uuid.UUID, p) -> bool:
    existing = (
        await db.execute(select(RazorpayPayment).where(RazorpayPayment.razorpay_payment_id == p.razorpay_payment_id))
    ).scalar_one_or_none()
    fields = dict(
        merchant_account_id=merchant_id, razorpay_payment_id=p.razorpay_payment_id,
        order_id=f"order_{p.razorpay_payment_id[4:]}", amount=p.amount, currency="INR", status="captured",
        method="upi", fee=p.fee, tax=p.tax, payment_date=_dt(BASE_DATE),
        raw_payload={"id": p.razorpay_payment_id, "seed": True},
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        return False
    else:
        db.add(RazorpayPayment(**fields))
        return True


async def _upsert_settlement(db: AsyncSession, merchant_id: uuid.UUID, s) -> bool:
    existing = (
        await db.execute(
            select(RazorpaySettlement).where(RazorpaySettlement.razorpay_settlement_id == s.razorpay_settlement_id)
        )
    ).scalar_one_or_none()
    raw_payload = {"id": s.razorpay_settlement_id, "seed": True}
    if s.payment_ids:
        raw_payload["linked_payment_id"] = s.payment_ids[0]
    fields = dict(
        merchant_account_id=merchant_id, razorpay_settlement_id=s.razorpay_settlement_id, utr=s.utr,
        amount=s.amount, fees=s.fees, tax=s.tax, status="processed",
        settlement_date=_dt(s.settlement_date), raw_payload=raw_payload,
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        return False
    else:
        db.add(RazorpaySettlement(**fields))
        return True


async def _upsert_refund(db: AsyncSession, merchant_id: uuid.UUID, r) -> bool:
    existing = (
        await db.execute(select(RazorpayRefund).where(RazorpayRefund.razorpay_refund_id == r.razorpay_refund_id))
    ).scalar_one_or_none()
    fields = dict(
        merchant_account_id=merchant_id, razorpay_refund_id=r.razorpay_refund_id,
        razorpay_payment_id=r.razorpay_payment_id, amount=r.amount, status="processed",
        refund_date=_dt(BASE_DATE), raw_payload={"id": r.razorpay_refund_id, "seed": True},
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        return False
    else:
        db.add(RazorpayRefund(**fields))
        return True


async def _upsert_bank_row(db: AsyncSession, merchant_id: uuid.UUID, b) -> bool:
    row_hash = f"seed-{merchant_id.hex[:8]}-{b.id}"
    existing = (
        await db.execute(
            select(BankTransaction).where(
                BankTransaction.merchant_account_id == merchant_id, BankTransaction.row_hash == row_hash,
            )
        )
    ).scalar_one_or_none()
    fields = dict(
        merchant_account_id=merchant_id, import_batch_id=DEMO_BATCH_ID, transaction_date=b.transaction_date,
        description=f"NEFT CR {b.reference_id}", reference_id=b.reference_id, utr=b.utr,
        credit=b.credit, debit=b.debit, balance=None, row_hash=row_hash, is_duplicate=False,
        raw_row={"seed": True},
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        return False
    else:
        db.add(BankTransaction(**fields))
        return True


async def seed_merchant_demo_dataset(db: AsyncSession, merchant_id: uuid.UUID) -> dict:
    prefix = f"m{str(merchant_id).replace('-', '')[:6]}"
    data, ground_truth = generate_dataset(prefix=prefix)

    records_created = 0
    records_existing = 0

    for p in data.payments:
        if await _upsert_payment(db, merchant_id, p):
            records_created += 1
        else:
            records_existing += 1

    for s in data.settlements:
        if await _upsert_settlement(db, merchant_id, s):
            records_created += 1
        else:
            records_existing += 1

    for r in data.refunds:
        if await _upsert_refund(db, merchant_id, r):
            records_created += 1
        else:
            records_existing += 1

    for b in data.bank_rows:
        if await _upsert_bank_row(db, merchant_id, b):
            records_created += 1
        else:
            records_existing += 1

    counts: dict[str, int] = {}
    for label in ground_truth.values():
        counts[label] = counts.get(label, 0) + 1

    await audit_service.log_action(
        db,
        actor_type="SYSTEM",
        action="DEMO_DATASET_SEEDED",
        new_state={
            "merchant_account_id": str(merchant_id),
            "records_created": records_created,
            "records_existing": records_existing,
            "settlements": len(data.settlements),
            "payments": len(data.payments),
        },
    )

    await db.commit()

    return {
        "merchant_account_id": str(merchant_id),
        "records_created": records_created,
        "records_existing": records_existing,
        "payments_count": len(data.payments),
        "settlements_count": len(data.settlements),
        "refunds_count": len(data.refunds),
        "bank_transactions_count": len(data.bank_rows),
        "total_records": len(data.payments) + len(data.settlements) + len(data.refunds) + len(data.bank_rows),
        "counts": counts,
    }


async def seed_demo_dataset(db: AsyncSession) -> dict:
    merchant = await _get_or_create_demo_merchant(db)
    summary = await seed_merchant_demo_dataset(db, merchant.id)
    summary["merchant_email"] = DEMO_EMAIL
    summary["total_settlements"] = summary["settlements_count"]
    return summary


async def _main() -> None:
    async with AsyncSessionLocal() as db:
        summary = await seed_demo_dataset(db)
        print(f"Seeded demo dataset for merchant {summary['merchant_account_id']}")
        print(f"Total settlements: {summary['settlements_count']}")
        print(f"Records created: {summary['records_created']}, Existing: {summary['records_existing']}")
        for category, count in sorted(summary["counts"].items()):
            print(f"  {category}: {count}")
        print(f"\nLog in with: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print("Then POST /api/v1/reconciliation/runs to reconcile the batch.")


if __name__ == "__main__":
    asyncio.run(_main())
