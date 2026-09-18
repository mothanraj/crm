from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


class RefreshBody(BaseModel):
    refresh_token: str = ""

from app.core.deps import current_user
from app.core.security import TokenExpired, TokenInvalid, access_token, decode_token, refresh_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import LoginIn

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _db_down(exc: Exception) -> HTTPException:
    return HTTPException(
        503,
        "Database unreachable. Check internet/DNS and DATABASE_URL "
        "(Supabase project must be Active; prefer the pooler connection string).",
    )


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    try:
        u = db.query(User).filter(User.email == body.email.lower().strip()).first()
    except OperationalError as exc:
        raise _db_down(exc) from exc
    if not u or not u.is_active or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Invalid credentials")
    role = u.role.name if u.role else "EMPLOYEE"
    return {"access_token": access_token(str(u.id)), "refresh_token": refresh_token(str(u.id)),
            "user": {"id": str(u.id), "name": u.name, "email": u.email, "role": role}}


@router.post("/refresh")
def refresh(body: RefreshBody, db: Session = Depends(get_db)):
    try:
        uid = decode_token(body.refresh_token, "refresh")
    except (TokenExpired, TokenInvalid) as exc:
        raise HTTPException(401, str(exc)) from exc
    try:
        u = db.get(User, uid)
    except OperationalError as exc:
        raise _db_down(exc) from exc
    if not u or not u.is_active:
        raise HTTPException(401, "User inactive")
    # Rotation: every refresh mints a fresh pair.
    return {"access_token": access_token(str(u.id)), "refresh_token": refresh_token(str(u.id))}
