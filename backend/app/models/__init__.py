"""All SQLAlchemy models (UUID PKs). Imported by Alembic env."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _ts():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _ts_updated():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text, default="")
    department: Mapped[str] = mapped_column(Text, default="")
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts_updated()
    role: Mapped[Role] = relationship()


class LeadSource(Base):
    __tablename__ = "lead_sources"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    id: Mapped[uuid.UUID] = _pk()
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    alias: Mapped[str] = mapped_column(Text, unique=True)


class LeadStatus(Base):
    __tablename__ = "lead_statuses"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[uuid.UUID] = _pk()
    enquiry_number: Mapped[str] = mapped_column(Text, unique=True)
    legacy_enquiry_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enquiry_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    customer_name: Mapped[str] = mapped_column(Text, default="")
    contact_number: Mapped[str] = mapped_column(Text, default="")
    contact_number_norm: Mapped[str] = mapped_column(Text, default="", index=True)
    alternate_contact: Mapped[str] = mapped_column(Text, default="")
    email: Mapped[str] = mapped_column(Text, default="")
    company_name: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(Text, default="")
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lead_sources.id"), nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    requirement: Mapped[str] = mapped_column(Text, default="")
    quantity_raw: Mapped[str] = mapped_column(Text, default="")
    quantity_num: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    priority: Mapped[str] = mapped_column(Text, default="")
    status_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead_statuses.id"))
    primary_employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    technical_employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    secondary_support_employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    first_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_contact_method: Mapped[str] = mapped_column(Text, default="")
    first_contact_result: Mapped[str] = mapped_column(Text, default="")
    first_contact_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    first_contact_notes: Mapped[str] = mapped_column(Text, default="")
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_state: Mapped[str] = mapped_column(Text, default="PENDING")
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overdue_digest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assignment_email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts_updated()


class LeadAssignment(Base):
    __tablename__ = "lead_assignments"
    id: Mapped[uuid.UUID] = _pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(Text, default="PRIMARY")
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime] = _ts()
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


class LeadStatusHistory(Base):
    __tablename__ = "lead_status_history"
    id: Mapped[uuid.UUID] = _pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    old_status_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lead_statuses.id"), nullable=True)
    new_status_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead_statuses.id"))
    changed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    changed_at: Mapped[datetime] = _ts()
    reason: Mapped[str] = mapped_column(Text, default="")


class LeadActivity(Base):
    __tablename__ = "lead_activities"
    id: Mapped[uuid.UUID] = _pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    activity_type: Mapped[str] = mapped_column(Text, default="Note")
    activity_at: Mapped[datetime] = _ts()
    notes: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[str] = mapped_column(Text, default="")
    next_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts()


class SiteVisit(Base):
    __tablename__ = "site_visits"
    id: Mapped[uuid.UUID] = _pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    visit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    site_location: Mapped[str] = mapped_column(Text, default="")
    visit_status: Mapped[str] = mapped_column(Text, default="Scheduled")
    customer_feedback: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class Quotation(Base):
    __tablename__ = "quotations"
    id: Mapped[uuid.UUID] = _pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    quotation_number: Mapped[str] = mapped_column(Text, unique=True)
    quotation_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    revision: Mapped[str] = mapped_column(Text, default="R0")
    units: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    amount_excl: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    gst: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    grand_total: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="Draft")
    sent_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class LeadDocument(Base):
    __tablename__ = "lead_documents"
    id: Mapped[uuid.UUID] = _pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    file_name: Mapped[str] = mapped_column(Text)
    stored_path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    document_type: Mapped[str] = mapped_column(Text, default="Other")
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = _ts()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    kind: Mapped[str] = mapped_column(Text, default="INFO")
    title: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _ts()


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[uuid.UUID] = _pk()
    file_name: Mapped[str] = mapped_column(Text)
    sheet_name: Mapped[str] = mapped_column(Text, default="")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    invalid: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(Text, default="PREVIEW")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = _ts()


class ImportError(Base):
    __tablename__ = "import_errors"
    id: Mapped[uuid.UUID] = _pk()
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="INVALID")


class AssignmentState(Base):
    __tablename__ = "assignment_state"
    id: Mapped[uuid.UUID] = _pk()
    last_employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = _ts_updated()


class EnquirySequence(Base):
    __tablename__ = "enquiry_sequence"
    id: Mapped[uuid.UUID] = _pk()
    last_number: Mapped[int] = mapped_column(Integer, default=0)
