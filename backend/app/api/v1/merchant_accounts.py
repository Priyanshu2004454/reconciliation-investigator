from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.users import MerchantAccount, User
from app.schemas.merchant import MerchantAccountCreate, MerchantAccountOut

router = APIRouter(prefix="/merchant-accounts", tags=["merchant-accounts"])


@router.get("/me", response_model=MerchantAccountOut | None)
async def get_my_merchant_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    NEW in this phase (additive, read-only): lets the frontend check whether
    the logged-in user already has a merchant account before showing the
    "create one" form, instead of blindly POSTing and risking duplicates.
    """
    account = (
        await db.execute(select(MerchantAccount).where(MerchantAccount.owner_id == current_user.id))
    ).scalars().first()
    return account


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
