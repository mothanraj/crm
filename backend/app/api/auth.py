from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.core.security import access_token, refresh_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import LoginIn

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not u or not u.is_active or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Invalid credentials")
    role = u.role.name if u.role else "EMPLOYEE"
    return {"access_token": access_token(str(u.id)), "refresh_token": refresh_token(str(u.id)),
            "user": {"id": str(u.id), "name": u.name, "email": u.email, "role": role}}
