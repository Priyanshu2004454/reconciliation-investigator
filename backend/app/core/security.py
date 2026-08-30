from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    # bcrypt has a hard 72-byte limit and newer bcrypt versions raise instead
    # of silently truncating — truncate ourselves so long passwords don't 500.
    truncated = plain_password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return _pwd_context.hash(truncated)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    truncated = plain_password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return _pwd_context.verify(truncated, hashed_password)


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire, "iat": datetime.utcnow()}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class InvalidTokenError(Exception):
    pass


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
