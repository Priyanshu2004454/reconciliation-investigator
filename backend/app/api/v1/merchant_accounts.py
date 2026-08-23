from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.users import MerchantAccount, User
from app.schemas.merchant import MerchantAccountCreate, MerchantAccountOut

router = APIRouter(prefix="/merchant-accounts", tags=["merchant-accounts"])


@router.post("", response_model=MerchantAccountOut, status_code=status.HTTP_201_CREATED)
async def create_merchant_account(
    payload: MerchantAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Stores only the public Razorpay key ID. RAZORPAY_KEY_SECRET always comes
    from server-side environment variables (see app.core.config) and is
    never accepted from a request body or persisted to the database.
    """
    account = MerchantAccount(
        owner_id=current_user.id,
        business_name=payload.business_name,
        razorpay_key_id=payload.razorpay_key_id,
        is_test_mode=payload.is_test_mode,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account
