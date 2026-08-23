import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, InvalidTokenError
from app.db.session import get_db
from app.models.users import User, MerchantAccount

_bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    user = (await db.execute(select(User).where(User.id == user_uuid))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


async def get_current_merchant_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MerchantAccount:
    """
    MVP simplification: one user -> one active merchant account (section 30 —
    multi-merchant support is explicitly future roadmap, not MVP scope).
    """
    account = (
        await db.execute(select(MerchantAccount).where(MerchantAccount.owner_id == current_user.id))
    ).scalars().first()

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No merchant account found for this user. Create one via POST /merchant-accounts first.",
        )
    return account
