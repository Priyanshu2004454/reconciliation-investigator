import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.webhook_service import process_webhook, verify_signature, WebhookProcessingResult

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/razorpay", response_model=WebhookProcessingResult)
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    No auth dependency here on purpose — Razorpay calls this directly, not
    through our JWT-protected API. The webhook signature IS the authentication.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not verify_signature(raw_body, signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload") from exc

    return await process_webhook(db, payload, raw_body)
