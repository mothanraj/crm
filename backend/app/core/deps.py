from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode
from app.db.session import get_db
from app.models import User

bearer = HTTPBearer()


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        uid = decode(creds.credentials)
    except Exception:
        raise HTTPException(401, "Invalid token")
    u = db.get(User, uid)
    if not u or not u.is_active:
        raise HTTPException(401, "User inactive")
    return u


def admin_only(u: User = Depends(current_user)) -> User:
    from app.models import Role
    # role loaded lazily; check via db in routers instead — keep simple name check through relationship
    if not u.role or u.role.name != "ADMIN":
        raise HTTPException(403, "Admin only")
    return u
