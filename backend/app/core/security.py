import uuid
from datetime import datetime, timedelta, timezone
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(p: str) -> str:
    return pwd.hash(p[:72])


def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p[:72], h)


def _token(sub: str, typ: str, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": sub, "typ": typ, "iat": now,
         "exp": now + timedelta(minutes=minutes), "jti": uuid.uuid4().hex},
        settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM,
    )


def access_token(sub: str) -> str:
    return _token(sub, "access", settings.ACCESS_TOKEN_MINUTES)


def refresh_token(sub: str) -> str:
    return _token(sub, "refresh", settings.REFRESH_TOKEN_DAYS * 24 * 60)


def decode_token(token: str, expect_typ: str = "access") -> str:
    """Returns the subject. Raises TokenExpired / TokenInvalid (both ValueError)."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError as exc:
        raise TokenExpired("Token expired — please sign in again") from exc
    except JWTError as exc:
        raise TokenInvalid("Invalid token") from exc
    if payload.get("typ") != expect_typ or not payload.get("sub"):
        raise TokenInvalid("Invalid token")
    return payload["sub"]


def decode(sub_token: str) -> str:
    return decode_token(sub_token, "access")


class TokenExpired(ValueError):
    pass


class TokenInvalid(ValueError):
    pass
