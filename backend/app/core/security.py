from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(p: str) -> str:
    return pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p, h)


def _token(sub: str, minutes: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return jwt.encode({"sub": sub, "exp": exp}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def access_token(sub: str) -> str:
    return _token(sub, settings.ACCESS_TOKEN_MINUTES)


def refresh_token(sub: str) -> str:
    return _token(sub, settings.REFRESH_TOKEN_DAYS * 24 * 60)


def decode(sub_token: str) -> str:
    return jwt.decode(sub_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])["sub"]
