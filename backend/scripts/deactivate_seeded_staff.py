"""One-time: deactivate previously seeded non-admin users."""
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Role, User


def main():
    db = SessionLocal()
    try:
        rows = db.query(User).join(Role).filter(Role.name != "ADMIN").all()
        n = 0
        for u in rows:
            if u.is_active:
                u.is_active = False
                n += 1
                print(f"deactivated {u.email}")
        db.commit()
        admin = db.query(User).filter_by(email=settings.ADMIN_EMAIL.lower()).first()
        print(f"done deactivated={n} admin_ok={bool(admin)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
