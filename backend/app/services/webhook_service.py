"""
Razorpay webhook handling (section 5).

Two guarantees this module exists to provide:
  1. Signature verification — we never trust a webhook body we can't verify
     came from Razorpay (HMAC-SHA256 over the raw request body, using the
     dashboard-configured webhook secret).
  2. Idempotency — Razorpay may deliver the same event more than once (retries
     on timeout, etc). Processing the same event_id twice must never create
     duplicate payment/settlement/refund rows.

KNOWN LIMITATION (documented per section 37): this MVP resolves incoming
webhooks to the first merchant_account row in the database rather than a
per-merchant webhook secret/routing table, since multi-merchant webhook
routing needs Razorpay's Connected Accounts (out of scope per section 30 —
"complex banking integrations" / multi-merchant is explicitly future roadmap
in section 35). Single-merchant Test Mode deployments — which is what this
buildathon MVP targets — are unaffected by this simplification.
"""

import hashlib
import hmac
import time
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit import WebhookEvent
from app.models.financial import RazorpayPayment, RazorpayOrder, RazorpayRefund, RazorpaySettlement
from app.models.users import MerchantAccount
from app.services import audit_service
from app.services.normalization import paise_to_rupees, unix_to_datetime


class WebhookSignatureError(Exception):
    pass


class WebhookProcessingResult(BaseModel):
    event_id: str
    event_type: str
    status: str  # WebhookProcessingStatus
    message: str


def verify_signature(raw_body: bytes, signature: str) -> bool:
    """
    Razorpay signs webhooks as hex(hmac_sha256(webhook_secret, raw_body)).
    Uses constant-time comparison to avoid timing attacks.
    """
    settings = get_settings()
    if not signature:
        return False
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _derive_event_id(payload: dict, raw_body: bytes) -> str:
    """
    Razorpay webhook payloads don't always carry a top-level unique event id
    depending on the event/version. Fall back to a content hash so every
    distinct delivery still gets a stable idempotency key, and identical
    redeliveries (retries) hash to the same key.
    """
    explicit_id = payload.get("id")
    if explicit_id:
        return str(explicit_id)
    return hashlib.sha256(raw_body).hexdigest()


async def _resolve_merchant_account(db: AsyncSession) -> Optional[MerchantAccount]:
    return (await db.execute(select(MerchantAccount).limit(1))).scalars().first()


async def _upsert_payment(db: AsyncSession, merchant_account_id, raw: dict) -> None:
    existing = (
        await db.execute(select(RazorpayPayment).where(RazorpayPayment.razorpay_payment_id == raw["id"]))
    ).scalar_one_or_none()
    fields = dict(
        merchant_account_id=merchant_account_id, razorpay_payment_id=raw["id"],
        order_id=raw.get("order_id"), amount=paise_to_rupees(raw.get("amount")),
        currency=raw.get("currency", "INR"), status=raw.get("status", "unknown"),
        method=raw.get("method"), fee=paise_to_rupees(raw.get("fee")), tax=paise_to_rupees(raw.get("tax")),
        payment_date=unix_to_datetime(raw.get("created_at")), raw_payload=raw,
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
    else:
        db.add(RazorpayPayment(**fields))


async def _upsert_order(db: AsyncSession, merchant_account_id, raw: dict) -> None:
    existing = (
        await db.execute(select(RazorpayOrder).where(RazorpayOrder.razorpay_order_id == raw["id"]))
    ).scalar_one_or_none()
    fields = dict(
        merchant_account_id=merchant_account_id, razorpay_order_id=raw["id"],
        amount=paise_to_rupees(raw.get("amount")), currency=raw.get("currency", "INR"),
        status=raw.get("status", "unknown"), receipt=raw.get("receipt"),
        order_date=unix_to_datetime(raw.get("created_at")), raw_payload=raw,
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
    else:
        db.add(RazorpayOrder(**fields))


async def _upsert_refund(db: AsyncSession, merchant_account_id, raw: dict) -> None:
    existing = (
        await db.execute(select(RazorpayRefund).where(RazorpayRefund.razorpay_refund_id == raw["id"]))
    ).scalar_one_or_none()
    fields = dict(
        merchant_account_id=merchant_account_id, razorpay_refund_id=raw["id"],
        razorpay_payment_id=raw["payment_id"], amount=paise_to_rupees(raw.get("amount")),
        status=raw.get("status", "unknown"), refund_date=unix_to_datetime(raw.get("created_at")),
        raw_payload=raw,
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
    else:
        db.add(RazorpayRefund(**fields))


async def _upsert_settlement(db: AsyncSession, merchant_account_id, raw: dict) -> None:
    existing = (
        await db.execute(
            select(RazorpaySettlement).where(RazorpaySettlement.razorpay_settlement_id == raw["id"])
        )
    ).scalar_one_or_none()
    fields = dict(
        merchant_account_id=merchant_account_id, razorpay_settlement_id=raw["id"],
        utr=raw.get("utr"), amount=paise_to_rupees(raw.get("amount")),
        fees=paise_to_rupees(raw.get("fees")), tax=paise_to_rupees(raw.get("tax")),
        status=raw.get("status", "unknown"), settlement_date=unix_to_datetime(raw.get("created_at")),
        raw_payload=raw,
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
    else:
        db.add(RazorpaySettlement(**fields))


_ENTITY_HANDLERS = {
    "payment": _upsert_payment,
    "order": _upsert_order,
    "refund": _upsert_refund,
    "settlement": _upsert_settlement,
}


async def process_webhook(db: AsyncSession, payload: dict, raw_body: bytes) -> WebhookProcessingResult:
    event_type = payload.get("event", "unknown")
    event_id = _derive_event_id(payload, raw_body)

    existing_event = (
        await db.execute(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
    ).scalar_one_or_none()

    if existing_event is not None:
        # Idempotency: same event delivered again (Razorpay retry) — never reprocess.
        return WebhookProcessingResult(
            event_id=event_id, event_type=event_type, status="DUPLICATE",
            message="Event already processed; skipped to avoid duplicate records.",
        )

    webhook_row = WebhookEvent(
        event_id=event_id, event_type=event_type, payload=payload,
        received_at=datetime.utcnow(), processing_status="RECEIVED",
    )
    db.add(webhook_row)
    await db.flush()

    entity_kind = event_type.split(".")[0] if "." in event_type else None
    handler = _ENTITY_HANDLERS.get(entity_kind)

    try:
        if handler is None:
            webhook_row.processing_status = "PROCESSED"
            webhook_row.processed_at = datetime.utcnow()
            await audit_service.log_action(
                db, actor_type="SYSTEM", action="WEBHOOK_STORED_UNHANDLED_TYPE",
                new_state={"event_id": event_id, "event_type": event_type},
            )
            await db.commit()
            return WebhookProcessingResult(
                event_id=event_id, event_type=event_type, status="PROCESSED",
                message=f"Event type '{event_type}' has no dedicated handler; stored for audit purposes only.",
            )

        merchant = await _resolve_merchant_account(db)
        if merchant is None:
            webhook_row.processing_status = "FAILED"
            webhook_row.error_message = "No merchant account configured to attribute this webhook to."
            webhook_row.processed_at = datetime.utcnow()
            await db.commit()
            return WebhookProcessingResult(
                event_id=event_id, event_type=event_type, status="FAILED",
                message="No merchant account exists yet — event stored but not applied.",
            )

        entity_payload = payload.get("payload", {}).get(entity_kind, {}).get("entity")
        if not entity_payload:
            raise ValueError(f"Malformed webhook payload — missing payload.{entity_kind}.entity")

        await handler(db, merchant.id, entity_payload)

        webhook_row.processing_status = "PROCESSED"
        webhook_row.processed_at = datetime.utcnow()
        await audit_service.log_action(
            db, actor_type="SYSTEM", action="WEBHOOK_PROCESSED",
            new_state={"event_id": event_id, "event_type": event_type, "entity_id": entity_payload.get("id")},
        )
        await db.commit()
        return WebhookProcessingResult(
            event_id=event_id, event_type=event_type, status="PROCESSED",
            message=f"Applied {event_type} to {entity_kind} {entity_payload.get('id')}.",
        )

    except Exception as exc:  # noqa: BLE001 — never let one bad webhook crash the app (section 24)
        webhook_row.processing_status = "FAILED"
        webhook_row.error_message = str(exc)
        webhook_row.processed_at = datetime.utcnow()
        await audit_service.log_action(
            db, actor_type="SYSTEM", action="WEBHOOK_FAILED",
            reason=str(exc), new_state={"event_id": event_id, "event_type": event_type},
        )
        await db.commit()
        return WebhookProcessingResult(
            event_id=event_id, event_type=event_type, status="FAILED", message=str(exc),
        )
