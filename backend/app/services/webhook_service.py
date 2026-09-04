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
    status: str  
    message: str


def verify_signature(raw_body: bytes, signature: str) -> bool:
    
    settings = get_settings()
    if not signature:
        return False
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _derive_event_id(payload: dict, raw_body: bytes) -> str:
    
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

    except Exception as exc:  
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
