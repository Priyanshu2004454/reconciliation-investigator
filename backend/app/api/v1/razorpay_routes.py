from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant_account
from app.db.session import get_db
from app.models.users import MerchantAccount
from app.schemas.financial import SyncResult
from app.services import razorpay_sync_service

router = APIRouter(prefix="/razorpay", tags=["razorpay"])


@router.post("/sync", response_model=list[SyncResult])
async def sync_razorpay_data(
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetches payments, orders, refunds, and settlements from Razorpay Test Mode
    and upserts them into the database. Never fails the whole request just
    because one entity type errored — each SyncResult reports its own errors
    independently (section 24: never crash the app over one bad record).
    """
    return await razorpay_sync_service.sync_all(db, merchant.id)
