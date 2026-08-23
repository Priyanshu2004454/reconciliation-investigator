"""
Orchestrates: razorpay_service (fetch raw data) -> normalization (convert units)
-> upsert into Postgres. Idempotent — re-running a sync updates existing rows
by their unique razorpay_*_id rather than creating duplicates.
"""

import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial import RazorpayPayment, RazorpayOrder, RazorpayRefund, RazorpaySettlement
from app.schemas.financial import SyncResult
from app.services import razorpay_service
from app.services.normalization import paise_to_rupees, unix_to_datetime


async def sync_payments(db: AsyncSession, merchant_account_id: uuid.UUID) -> SyncResult:
    start = time.monotonic()
    errors: list[str] = []
    created = updated = skipped = 0

    try:
        raw_payments = razorpay_service.fetch_payments()
    except Exception as exc:  # noqa: BLE001
        return SyncResult(source="RAZORPAY_PAYMENT", fetched=0, created=0, updated=0, skipped=0,
                           errors=[str(exc)], duration_ms=int((time.monotonic() - start) * 1000))

    for raw in raw_payments:
        try:
            existing = (
                await db.execute(select(RazorpayPayment).where(RazorpayPayment.razorpay_payment_id == raw["id"]))
            ).scalar_one_or_none()

            fields = dict(
                merchant_account_id=merchant_account_id,
                razorpay_payment_id=raw["id"],
                order_id=raw.get("order_id"),
                amount=paise_to_rupees(raw.get("amount")),
                currency=raw.get("currency", "INR"),
                status=raw.get("status", "unknown"),
                method=raw.get("method"),
                fee=paise_to_rupees(raw.get("fee")),
                tax=paise_to_rupees(raw.get("tax")),
                payment_date=unix_to_datetime(raw.get("created_at")),
                raw_payload=raw,
            )
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(RazorpayPayment(**fields))
                created += 1
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            errors.append(f"payment {raw.get('id', '?')}: {exc}")

    await db.commit()
    return SyncResult(
        source="RAZORPAY_PAYMENT", fetched=len(raw_payments), created=created, updated=updated,
        skipped=skipped, errors=errors, duration_ms=int((time.monotonic() - start) * 1000),
    )


async def sync_orders(db: AsyncSession, merchant_account_id: uuid.UUID) -> SyncResult:
    start = time.monotonic()
    errors: list[str] = []
    created = updated = skipped = 0

    try:
        raw_orders = razorpay_service.fetch_orders()
    except Exception as exc:  # noqa: BLE001
        return SyncResult(source="RAZORPAY_ORDER", fetched=0, created=0, updated=0, skipped=0,
                           errors=[str(exc)], duration_ms=int((time.monotonic() - start) * 1000))

    for raw in raw_orders:
        try:
            existing = (
                await db.execute(select(RazorpayOrder).where(RazorpayOrder.razorpay_order_id == raw["id"]))
            ).scalar_one_or_none()

            fields = dict(
                merchant_account_id=merchant_account_id,
                razorpay_order_id=raw["id"],
                amount=paise_to_rupees(raw.get("amount")),
                currency=raw.get("currency", "INR"),
                status=raw.get("status", "unknown"),
                receipt=raw.get("receipt"),
                order_date=unix_to_datetime(raw.get("created_at")),
                raw_payload=raw,
            )
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(RazorpayOrder(**fields))
                created += 1
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            errors.append(f"order {raw.get('id', '?')}: {exc}")

    await db.commit()
    return SyncResult(
        source="RAZORPAY_ORDER", fetched=len(raw_orders), created=created, updated=updated,
        skipped=skipped, errors=errors, duration_ms=int((time.monotonic() - start) * 1000),
    )


async def sync_refunds(db: AsyncSession, merchant_account_id: uuid.UUID) -> SyncResult:
    start = time.monotonic()
    errors: list[str] = []
    created = updated = skipped = 0

    try:
        raw_refunds = razorpay_service.fetch_refunds()
    except Exception as exc:  # noqa: BLE001
        return SyncResult(source="RAZORPAY_REFUND", fetched=0, created=0, updated=0, skipped=0,
                           errors=[str(exc)], duration_ms=int((time.monotonic() - start) * 1000))

    for raw in raw_refunds:
        try:
            existing = (
                await db.execute(select(RazorpayRefund).where(RazorpayRefund.razorpay_refund_id == raw["id"]))
            ).scalar_one_or_none()

            fields = dict(
                merchant_account_id=merchant_account_id,
                razorpay_refund_id=raw["id"],
                razorpay_payment_id=raw["payment_id"],
                amount=paise_to_rupees(raw.get("amount")),
                status=raw.get("status", "unknown"),
                refund_date=unix_to_datetime(raw.get("created_at")),
                raw_payload=raw,
            )
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(RazorpayRefund(**fields))
                created += 1
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            errors.append(f"refund {raw.get('id', '?')}: {exc}")

    await db.commit()
    return SyncResult(
        source="RAZORPAY_REFUND", fetched=len(raw_refunds), created=created, updated=updated,
        skipped=skipped, errors=errors, duration_ms=int((time.monotonic() - start) * 1000),
    )


async def sync_settlements(db: AsyncSession, merchant_account_id: uuid.UUID) -> SyncResult:
    start = time.monotonic()
    errors: list[str] = []
    created = updated = skipped = 0

    try:
        raw_settlements = razorpay_service.fetch_settlements()
    except Exception as exc:  # noqa: BLE001
        return SyncResult(source="RAZORPAY_SETTLEMENT", fetched=0, created=0, updated=0, skipped=0,
                           errors=[str(exc)], duration_ms=int((time.monotonic() - start) * 1000))

    for raw in raw_settlements:
        try:
            existing = (
                await db.execute(
                    select(RazorpaySettlement).where(RazorpaySettlement.razorpay_settlement_id == raw["id"])
                )
            ).scalar_one_or_none()

            fields = dict(
                merchant_account_id=merchant_account_id,
                razorpay_settlement_id=raw["id"],
                utr=raw.get("utr"),
                amount=paise_to_rupees(raw.get("amount")),
                fees=paise_to_rupees(raw.get("fees")),
                tax=paise_to_rupees(raw.get("tax")),
                status=raw.get("status", "unknown"),
                settlement_date=unix_to_datetime(raw.get("created_at")),
                raw_payload=raw,
            )
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(RazorpaySettlement(**fields))
                created += 1
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            errors.append(f"settlement {raw.get('id', '?')}: {exc}")

    await db.commit()
    return SyncResult(
        source="RAZORPAY_SETTLEMENT", fetched=len(raw_settlements), created=created, updated=updated,
        skipped=skipped, errors=errors, duration_ms=int((time.monotonic() - start) * 1000),
    )


async def sync_all(db: AsyncSession, merchant_account_id: uuid.UUID) -> list[SyncResult]:
    """Order matters: payments/orders before settlements/refunds isn't strictly
    required since each is independent, but running payments first means the
    dashboard has something to show even if a later fetch fails partway."""
    return [
        await sync_payments(db, merchant_account_id),
        await sync_orders(db, merchant_account_id),
        await sync_refunds(db, merchant_account_id),
        await sync_settlements(db, merchant_account_id),
    ]
