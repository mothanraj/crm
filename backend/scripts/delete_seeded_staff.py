"""Delete previously seeded non-admin employees and clear FK references."""
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import (
    AssignmentState,
    ImportBatch,
    Lead,
    LeadActivity,
    LeadAssignment,
    LeadDocument,
    LeadStatusHistory,
    Notification,
    Role,
    SiteVisit,
    User,
)


def main():
    db = SessionLocal()
    try:
        staff = db.query(User).join(Role).filter(Role.name != "ADMIN").all()
        if not staff:
            print("no non-admin users to delete")
            return
        ids = [u.id for u in staff]
        emails = [u.email for u in staff]
        print(f"deleting {len(ids)} users: {emails}")

        # Nullable FKs → NULL
        db.query(AssignmentState).filter(AssignmentState.last_employee_id.in_(ids)).update(
            {AssignmentState.last_employee_id: None}, synchronize_session=False
        )
        db.query(ImportBatch).filter(ImportBatch.created_by.in_(ids)).update(
            {ImportBatch.created_by: None}, synchronize_session=False
        )
        db.query(Lead).filter(Lead.created_by.in_(ids)).update(
            {Lead.created_by: None}, synchronize_session=False
        )
        db.query(Lead).filter(Lead.first_contact_by.in_(ids)).update(
            {Lead.first_contact_by: None}, synchronize_session=False
        )
        db.query(Lead).filter(Lead.primary_employee_id.in_(ids)).update(
            {Lead.primary_employee_id: None}, synchronize_session=False
        )
        db.query(Lead).filter(Lead.technical_employee_id.in_(ids)).update(
            {Lead.technical_employee_id: None}, synchronize_session=False
        )
        db.query(Lead).filter(Lead.secondary_support_employee_id.in_(ids)).update(
            {Lead.secondary_support_employee_id: None}, synchronize_session=False
        )
        db.query(LeadActivity).filter(LeadActivity.employee_id.in_(ids)).update(
            {LeadActivity.employee_id: None}, synchronize_session=False
        )
        db.query(LeadDocument).filter(LeadDocument.uploaded_by.in_(ids)).update(
            {LeadDocument.uploaded_by: None}, synchronize_session=False
        )
        db.query(LeadStatusHistory).filter(LeadStatusHistory.changed_by.in_(ids)).update(
            {LeadStatusHistory.changed_by: None}, synchronize_session=False
        )
        db.query(SiteVisit).filter(SiteVisit.employee_id.in_(ids)).update(
            {SiteVisit.employee_id: None}, synchronize_session=False
        )
        db.query(LeadAssignment).filter(LeadAssignment.assigned_by.in_(ids)).update(
            {LeadAssignment.assigned_by: None}, synchronize_session=False
        )

        # Required / owned rows → delete
        db.query(LeadAssignment).filter(LeadAssignment.employee_id.in_(ids)).delete(synchronize_session=False)
        db.query(Notification).filter(Notification.user_id.in_(ids)).delete(synchronize_session=False)

        for u in staff:
            db.delete(u)
        db.commit()

        left = db.query(User).join(Role).filter(Role.name != "ADMIN").count()
        admin = db.query(User).filter_by(email=settings.ADMIN_EMAIL.lower()).first()
        print(f"done remaining_staff={left} admin_ok={bool(admin)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
