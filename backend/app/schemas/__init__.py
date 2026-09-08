from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class LoginIn(BaseModel):
    email: str
    password: str


class LeadCreate(BaseModel):
    customer_name: str = ""
    contact_number: str = ""
    alternate_contact: str = ""
    email: str = ""
    company_name: str = ""
    location: str = ""
    city: str = ""
    enquiry_date: Optional[date] = None
    source_id: Optional[UUID] = None
    source_name: str = ""
    product_id: Optional[UUID] = None
    product_name: str = ""
    requirement: str = ""
    quantity_raw: str = ""
    priority: str = ""
    status_name: str = "New Lead"
    primary_employee_id: Optional[UUID] = None


class LeadUpdate(BaseModel):
    customer_name: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    company_name: Optional[str] = None
    city: Optional[str] = None
    requirement: Optional[str] = None
    next_followup_at: Optional[datetime] = None


class StatusChange(BaseModel):
    new_status_id: UUID
    reason: str = ""


class AssignIn(BaseModel):
    employee_id: UUID
    role: str = "PRIMARY"


class ContactIn(BaseModel):
    method: str
    result: str = ""
    notes: str = ""


class ActivityIn(BaseModel):
    activity_type: str = "Note"
    notes: str = ""
    outcome: str = ""
    next_followup_at: Optional[datetime] = None


class VisitIn(BaseModel):
    visit_date: Optional[datetime] = None
    site_location: str = ""
    visit_status: str = "Scheduled"
    customer_feedback: str = ""
    notes: str = ""


class QuoteIn(BaseModel):
    quotation_number: str
    quotation_date: Optional[date] = None
    revision: str = "R0"
    units: Optional[float] = None
    amount_excl: Optional[float] = None
    gst: Optional[float] = None
    grand_total: Optional[float] = None
    status: str = "Draft"
    notes: str = ""
