from datetime import date, datetime
from typing import Optional
from uuid import UUID

from decimal import Decimal
from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    password: str


class EmployeeCreate(BaseModel):
    name: str
    email: str
    password: str
    phone: str = ""
    department: str = "Sales"
    role: str = "EMPLOYEE"  # EMPLOYEE | MANAGER


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordReset(BaseModel):
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
    customer_review: Optional[str] = None
    product_id: Optional[UUID] = None
    quantity_raw: Optional[str] = None
    # lead_value / price_per_car / gst_amount are server-calculated — ignored if sent
    lead_value: Optional[Decimal] = None
    price_per_car: Optional[Decimal] = None
    gst_amount: Optional[Decimal] = None


class LeadValueCalcIn(BaseModel):
    product_id: Optional[UUID] = None
    number_of_cars: Optional[Decimal] = None
    quantity_raw: Optional[str] = None


class StatusChange(BaseModel):
    quotation_value: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=0)
    new_status_id: UUID
    reason: str = ""  # remarks — required when employee updates work progress
    method: str = "Call"  # used if this is also the first contact
    customer_review: str = ""
    sla_state: Optional[str] = None


class AssignIn(BaseModel):
    employee_id: UUID
    role: str = "PRIMARY"


class ReassignRequestIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class ReassignDecisionIn(BaseModel):
    note: str = ""


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
