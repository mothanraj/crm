"""Admin-only employee management: create, list, update, reset password."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import admin_only
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Role, User
from app.schemas import EmployeeCreate, EmployeeUpdate, PasswordReset

router = APIRouter(prefix="/api/employees", tags=["employees"])

_STAFF_ROLES = ("EMPLOYEE", "MANAGER")


def _serialize(u: User) -> dict:
    return {
        "id": str(u.id),
        "name": u.name,
        "email": u.email,
        "phone": u.phone or "",
        "department": u.department or "",
        "role": u.role.name if u.role else "EMPLOYEE",
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _staff_role(db: Session, name: str) -> Role:
    role_name = (name or "EMPLOYEE").upper().strip()
    if role_name not in _STAFF_ROLES:
        raise HTTPException(400, f"Role must be one of: {', '.join(_STAFF_ROLES)}")
    role = db.query(Role).filter_by(name=role_name).first()
    if not role:
        raise HTTPException(400, f"Role {role_name} not found")
    return role


def _require_staff(u: User) -> None:
    if not u.role or u.role.name == "ADMIN":
        raise HTTPException(400, "Cannot manage admin accounts here")


@router.get("")
def list_employees(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    rows = (
        db.query(User)
        .join(Role)
        .filter(Role.name.in_(_STAFF_ROLES))
        .order_by(User.name)
        .all()
    )
    return [_serialize(u) for u in rows]


@router.post("")
def create_employee(body: EmployeeCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    from app.services.normalize import format_phone, is_valid_email, is_valid_phone

    name = (body.name or "").strip()
    email = (body.email or "").lower().strip()
    password = body.password or ""
    phone_raw = (body.phone or "").strip()
    if not name:
        raise HTTPException(400, "Name is required")
    if not is_valid_email(email):
        raise HTTPException(400, "Enter a valid email address (e.g. name@company.com)")
    if not phone_raw:
        raise HTTPException(400, "Phone number is required")
    if not is_valid_phone(phone_raw):
        raise HTTPException(400, "Enter a valid 10-digit Indian mobile number (starts with 6–9)")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email already in use")
    phone = format_phone(phone_raw)
    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(400, "Phone number already in use")
    role = _staff_role(db, body.role)
    u = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        phone=phone,
        department=(body.department or "").strip(),
        role_id=role.id,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return _serialize(u)


@router.patch("/{uid}")
def update_employee(uid: UUID, body: EmployeeUpdate, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    from app.services.normalize import format_phone, is_valid_email, is_valid_phone

    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Employee not found")
    _require_staff(u)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "Name is required")
        u.name = name
    if body.email is not None:
        email = body.email.lower().strip()
        if not is_valid_email(email):
            raise HTTPException(400, "Enter a valid email address (e.g. name@company.com)")
        other = db.query(User).filter(User.email == email, User.id != u.id).first()
        if other:
            raise HTTPException(400, "Email already in use")
        u.email = email
    if body.phone is not None:
        phone_raw = body.phone.strip()
        if not phone_raw:
            raise HTTPException(400, "Phone number is required")
        if not is_valid_phone(phone_raw):
            raise HTTPException(400, "Enter a valid 10-digit Indian mobile number (starts with 6–9)")
        phone = format_phone(phone_raw)
        other = db.query(User).filter(User.phone == phone, User.id != u.id).first()
        if other:
            raise HTTPException(400, "Phone number already in use")
        u.phone = phone
    if body.department is not None:
        u.department = body.department.strip()
    if body.role is not None:
        u.role_id = _staff_role(db, body.role).id
    if body.is_active is not None:
        u.is_active = body.is_active
    db.commit()
    db.refresh(u)
    return _serialize(u)


@router.post("/{uid}/reset-password")
def reset_password(uid: UUID, body: PasswordReset, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Employee not found")
    _require_staff(u)
    password = body.password or ""
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    u.password_hash = hash_password(password)
    db.commit()
    return {"ok": True, "id": str(u.id), "email": u.email}
