"""Seed roles, statuses, sources, products+aliases, and bootstrap admin only.

Employees are created by admin via the Employees portal — never auto-seeded.
"""
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import AssignmentState, EnquirySequence, LeadSource, LeadStatus, Product, ProductAlias, Role, User
from app.services.normalize import (
    CANONICAL_SOURCES, CANONICAL_STATUSES, CANONICAL_PRODUCTS, PRODUCT_ALIASES,
)


def run():
    db = SessionLocal()
    try:
        for r in ["ADMIN", "EMPLOYEE", "MANAGER"]:
            if not db.query(Role).filter_by(name=r).first():
                db.add(Role(name=r, description=r))
        db.flush()
        roles = {r.name: r for r in db.query(Role).all()}
        for name, term, lost, order in CANONICAL_STATUSES:
            if not db.query(LeadStatus).filter_by(name=name).first():
                db.add(LeadStatus(name=name, is_terminal=term, is_lost=lost, sort_order=order))
        for i, s in enumerate(CANONICAL_SOURCES):
            if not db.query(LeadSource).filter_by(name=s).first():
                db.add(LeadSource(name=s, sort_order=i))
        for p in CANONICAL_PRODUCTS:
            if not db.query(Product).filter_by(name=p).first():
                db.add(Product(name=p))
        db.flush()
        pmap = {p.name: p for p in db.query(Product).all()}
        for alias, canon in PRODUCT_ALIASES.items():
            if not db.query(ProductAlias).filter_by(alias=alias).first() and canon in pmap:
                db.add(ProductAlias(product_id=pmap[canon].id, alias=alias))
        if not db.query(User).filter_by(email=settings.ADMIN_EMAIL).first():
            db.add(User(name=settings.ADMIN_NAME, email=settings.ADMIN_EMAIL,
                        password_hash=hash_password(settings.ADMIN_PASSWORD),
                        department="Admin", role_id=roles["ADMIN"].id))
        if not db.query(AssignmentState).first():
            db.add(AssignmentState())
        if not db.query(EnquirySequence).first():
            db.add(EnquirySequence(last_number=0))
        db.commit()
        print("seeded")
    finally:
        db.close()


if __name__ == "__main__":
    run()
