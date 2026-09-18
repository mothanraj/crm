"""Seed roles, statuses, sources, products+aliases, and bootstrap admin only.

Employees are created by admin via the Employees portal — never auto-seeded.
"""
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import AssignmentState, EnquirySequence, Lead, LeadSource, LeadStatus, LeadStatusHistory, Product, ProductAlias, Role, User
from app.services.normalize import (
    CANONICAL_SOURCES, CANONICAL_STATUSES, CANONICAL_PRODUCTS, PRODUCT_ALIASES,
)
from app.services.pricing import PRODUCT_PRICES


def run():
    db = SessionLocal()
    try:
        for r in ["ADMIN", "EMPLOYEE", "MANAGER"]:
            if not db.query(Role).filter_by(name=r).first():
                db.add(Role(name=r, description=r))
        db.flush()
        roles = {r.name: r for r in db.query(Role).all()}
        for name, term, lost, order in CANONICAL_STATUSES:
            st = db.query(LeadStatus).filter_by(name=name).first()
            if not st:
                db.add(LeadStatus(name=name, is_terminal=term, is_lost=lost, sort_order=order))
            else:
                st.is_terminal = term
                st.is_lost = lost
                st.sort_order = order
        for i, s in enumerate(CANONICAL_SOURCES):
            if not db.query(LeadSource).filter_by(name=s).first():
                db.add(LeadSource(name=s, sort_order=i))
        for p_name in CANONICAL_PRODUCTS:
            price = PRODUCT_PRICES.get(p_name, 0)
            existing = db.query(Product).filter_by(name=p_name).first()
            if not existing:
                db.add(Product(name=p_name, price_per_car=price, is_active=True))
            else:
                existing.price_per_car = price
                existing.is_active = True
        db.flush()
        # Hide any products outside the official 7
        for p in db.query(Product).all():
            if p.name not in PRODUCT_PRICES:
                p.is_active = False
        pmap = {p.name: p for p in db.query(Product).filter_by(is_active=True).all()}
        for alias, canon in PRODUCT_ALIASES.items():
            al = db.query(ProductAlias).filter_by(alias=alias).first()
            if canon not in pmap:
                continue
            if not al:
                db.add(ProductAlias(product_id=pmap[canon].id, alias=alias))
            else:
                al.product_id = pmap[canon].id
        if not db.query(User).filter_by(email=settings.ADMIN_EMAIL).first():
            db.add(User(name=settings.ADMIN_NAME, email=settings.ADMIN_EMAIL,
                        password_hash=hash_password(settings.ADMIN_PASSWORD),
                        department="Admin", role_id=roles["ADMIN"].id))
        if not db.query(AssignmentState).first():
            db.add(AssignmentState())
        if not db.query(EnquirySequence).first():
            db.add(EnquirySequence(last_number=0))
        db.flush()
        # Backfill: leads already assigned but still "New Lead" -> "Assigned".
        try:
            new_st = db.query(LeadStatus).filter_by(name="New Lead").first()
            assigned_st = db.query(LeadStatus).filter_by(name="Assigned").first()
            if new_st is not None and assigned_st is not None:
                stale = db.query(Lead).filter(
                    Lead.primary_employee_id.is_not(None),
                    Lead.status_id == new_st.id,
                    Lead.is_active.is_(True),
                ).all()
                admin = db.query(User).filter_by(email=settings.ADMIN_EMAIL).first()
                for lead in stale:
                    old = lead.status_id
                    lead.status_id = assigned_st.id
                    db.add(LeadStatusHistory(
                        lead_id=lead.id, old_status_id=old, new_status_id=assigned_st.id,
                        changed_by=admin.id if admin else None, reason="backfill assigned",
                    ))
                if stale:
                    print(f"backfilled {len(stale)} assigned leads")
        except Exception as exc:
            print(f"backfill skipped: {exc}")
        db.commit()
        print("seeded")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
