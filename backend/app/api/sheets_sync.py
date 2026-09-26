"""Google Sheets push sync: Apps Script -> backend webhook -> DB -> live website.

Insert-only with admin review (same as Excel upload): valid rows become
leads (auto-assigned + assignment email), duplicates/invalid go to
ImportError review queue visible in ImportPage (Correct / Add to leads / Delete).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.importer import _serialize_error, _send_assignment_batches, classify_intake_row
from app.core.config import settings
from app.core.deps import admin_only
from app.db.session import get_db
from app.models import (
    ImportBatch, ImportError, Lead, LeadSource, LeadStatus,
    LeadStatusHistory, Product, ProductAlias, User,
)
from app.services import live
from app.services.lead_service import (
    assign, auto_assign, choose_next_employee, employee_by_name,
    format_enquiry_number, next_enquiry_number, remember_assignment,
)
from app.services.normalize import (
    PRODUCT_ALIASES, canonical_source, norm_key, normalize_car_count, parse_excel_date,
)
from app.services.pricing import apply_pricing_to_lead

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sheets", tags=["sheets"])
PENDING_PREFIX = "sheets:"


class SheetsRow(BaseModel):
    row_id: str | int | float | None = Field(default=None)
    external_key: str = ""
    enq: str | int | float | None = None
    date: str | int | float | None = None
    name: str = ""
    company: str = ""
    phone: str = ""
    email: str = ""
    city: str = ""
    cars: str = ""
    requirement: str = ""
    quantity: str | int | float | None = None
    remarks: str = ""
    priority: str = ""
    alternate_contact: str = ""
    source: str = ""
    product: str = ""
    employee: str = ""


class SheetsPush(BaseModel):
    sheet_id: str = "default"
    rows: list[SheetsRow] = Field(max_len=100)


def _verify_signature(raw: bytes, ts: str, sig: str) -> None:
    secret = settings.SHEETS_WEBHOOK_SECRET or ""
    if not secret:
        raise HTTPException(503, "Sheets sync not configured (SHEETS_WEBHOOK_SECRET)")
    try:
        skew = abs(time.time() - int(ts))
    except (TypeError, ValueError):
        raise HTTPException(401, "Bad timestamp")
    if skew > max(60, int(settings.SHEETS_SIGNATURE_WINDOW_SEC)):
        raise HTTPException(401, "Stale request")
    expect = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, (sig or "").lower()):
        raise HTTPException(401, "Bad signature")


def _norm_source(db: Session, raw: str) -> LeadSource | None:
    canon = canonical_source(raw)
    src = db.query(LeadSource).filter(func.lower(LeadSource.name) == canon.lower()).first()
    if src:
        return src
    return db.query(LeadSource).filter(func.lower(LeadSource.name) == "others").first()


def _norm_product(db: Session, raw: str) -> Product | None:
    if not raw or not str(raw).strip():
        return None
    k = norm_key(str(raw))
    canon = PRODUCT_ALIASES.get(k, str(raw).strip())
    p = db.query(Product).filter(
        func.lower(Product.name) == canon.lower(), Product.is_active.is_(True),
    ).first()
    if p:
        return p
    al = db.query(ProductAlias).filter(func.lower(ProductAlias.alias) == k).first()
    if not al:
        return None
    prod = db.get(Product, al.product_id)
    return prod if prod and prod.is_active else None


def _default_status(db: Session) -> LeadStatus:
    st = db.query(LeadStatus).filter(LeadStatus.name == "New Lead").first()
    if not st:
        raise HTTPException(500, "New Lead status missing — run seed")
    return st


def _parse_legacy(raw) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(float(str(raw).strip()))
    except (ValueError, TypeError):
        return None


@router.post("/rows")
async def ingest_rows(
    request: Request,
    db: Session = Depends(get_db),
    x_sheets_timestamp: str = Header(default=""),
    x_sheets_signature: str = Header(default=""),
):
    raw = await request.body()
    _verify_signature(raw, x_sheets_timestamp, x_sheets_signature)
    try:
        body = SheetsPush.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(422, f"Invalid payload: {exc}") from exc
    if not body.rows:
        raise HTTPException(422, "No rows")

    st = _default_status(db)
    batch = ImportBatch(
        file_name=f"{PENDING_PREFIX}{body.sheet_id}", sheet_name=body.sheet_id,
        total_rows=len(body.rows), duplicates=0, invalid=0,
        status="SYNC", created_by=None,
    )
    db.add(batch)
    db.flush()

    inserted: list[str] = []
    assigned_names: list[str] = []
    errors: list[dict] = []
    seen_keys: set[str] = set()
    seen_phones: set[str] = set()
    seen_enqs: set[int] = set()
    new_by_emp: dict = {}

    for i, r in enumerate(body.rows, start=2):
        key = r.external_key.strip() or f"{body.sheet_id}:{r.row_id}"
        if key in seen_keys:
            errors.append({"row": r.row_id, "reason": "DUPLICATE", "error": "duplicate row in batch"})
            db.add(ImportError(batch_id=batch.id, row_number=i,
                               raw={"sheet_row_id": str(r.row_id), "external_key": key},
                               error="duplicate row in batch", reason="DUPLICATE"))
            batch.duplicates += 1
            continue
        seen_keys.add(key)
        # Idempotency: same external key pushed before?
        if r.external_key and db.query(ImportBatch).filter(
                ImportBatch.file_name == f"{PENDING_PREFIX}{body.sheet_id}",
                ImportBatch.sheet_name == key).first():
            # Already imported — skip silently so retries do not flood the review queue.
            continue
        name = (r.name or "").strip()
        phone = (r.phone or "").strip()
        email_v = (r.email or "").strip()
        classified = classify_intake_row(
            db, name=name, phone=phone, enq=r.enq, email=email_v,
            seen_phones=seen_phones, seen_enqs=seen_enqs,
        )
        phone_n = classified["phone_norm"]
        legacy = classified["legacy_enq"]
        raw_rec = {"sheet_id": body.sheet_id, "sheet_row_id": str(r.row_id),
                   "external_key": key, "enq": r.enq, "legacy_enq": legacy,
                   "date": r.date, "name": name, "company": (r.company or "").strip(),
                   "phone": phone, "phone_norm": phone_n, "email": email_v,
                   "email_invalid": classified["email_invalid"],
                   "city": (r.city or "").strip(), "cars": (r.cars or "").strip(),
                   "requirement": (r.requirement or "").strip(),
                   "quantity": r.quantity, "remarks": (r.remarks or "").strip(),
                   "priority": (r.priority or "").strip(),
                   "alternate_contact": (r.alternate_contact or "").strip(),
                   "source": (r.source or "").strip(), "product": (r.product or "").strip()}
        if classified["dups"]:
            batch.duplicates += 1
            db.add(ImportError(batch_id=batch.id, row_number=i, raw=raw_rec,
                               error=",".join(classified["dups"]), reason="DUPLICATE"))
            errors.append({"row": r.row_id, "reason": "DUPLICATE", "error": ",".join(classified["dups"])})
            continue
        if classified["errs"]:
            batch.invalid += 1
            db.add(ImportError(batch_id=batch.id, row_number=i, raw=raw_rec,
                               error=",".join(classified["errs"]), reason="INVALID"))
            errors.append({"row": r.row_id, "reason": "INVALID", "error": ",".join(classified["errs"])})
            continue
        named = (r.employee or "").strip()
        chosen = employee_by_name(db, named) if named else None
        if named and chosen is None:
            batch.invalid += 1
            db.add(ImportError(batch_id=batch.id, row_number=i, raw=raw_rec,
                               error=f"unknown employee ({named})", reason="INVALID"))
            errors.append({"row": r.row_id, "reason": "INVALID", "error": f"unknown employee ({named})"})
            continue
        seen_phones.add(phone_n)
        if legacy is not None:
            seen_enqs.add(legacy)
        src = _norm_source(db, r.source or "")
        prod = _norm_product(db, r.product or "")
        count, car_error = normalize_car_count((r.cars or "").strip() or str(r.quantity or "").strip(), r.product or "")
        if car_error:
            batch.invalid += 1
            db.add(ImportError(batch_id=batch.id, row_number=i, raw=raw_rec,
                               error=car_error, reason="INVALID"))
            errors.append({"row": r.row_id, "reason": "INVALID", "error": car_error})
            continue
        enquiry_number = format_enquiry_number(int(legacy)) if legacy is not None else next_enquiry_number(db)
        try:
            with db.begin_nested():
                lead = Lead(
                    enquiry_number=enquiry_number,
                    legacy_enquiry_no=legacy,
                    enquiry_date=parse_excel_date(r.date),
                    customer_name=name,
                    company_name=(r.company or "").strip(),
                    contact_number=phone,
                    contact_number_norm=phone_n,
                    alternate_contact=(r.alternate_contact or "").strip(),
                    email=email_v,
                    city=(r.city or "").strip(),
                    product_raw=(r.product or "").strip(),
                    requirement=(r.requirement or "").strip(),
                    quantity_raw=str(count),
                    quantity_num=count,
                    priority=(r.priority or "").strip(),
                    first_contact_notes=(r.remarks or "").strip(),
                    source_id=src.id if src else None,
                    product_id=prod.id if prod else None,
                    status_id=st.id,
                    sla_state="PENDING",
                    created_by=None,
                )
                apply_pricing_to_lead(lead, product=prod)
                db.add(lead)
                db.flush()
                db.add(LeadStatusHistory(
                    lead_id=lead.id, old_status_id=None, new_status_id=st.id,
                    changed_by=None, reason=f"sheets sync {body.sheet_id}",
                ))
                if chosen:
                    assign(db, lead, chosen)
                    remember_assignment(db, chosen)
                    new_by_emp.setdefault(chosen.id, []).append(lead.id)
                    assigned_name = chosen.name
                else:
                    emp = auto_assign(db, lead, None, ignore_limit=True)
                    assigned_name = emp.name if emp else ""
                    if emp:
                        new_by_emp.setdefault(emp.id, []).append(lead.id)
                db.add(ImportBatch(file_name=f"{PENDING_PREFIX}{body.sheet_id}",
                                   sheet_name=key, total_rows=1, duplicates=0,
                                   invalid=0, imported=1, status="SYNCED"))
        except IntegrityError as exc:
            log.warning("sheets row insert failed row=%s: %s", i, exc.orig)
            batch.duplicates += 1
            db.add(ImportError(batch_id=batch.id, row_number=i, raw=raw_rec,
                               error="could not save row (duplicate or constraint)", reason="DUPLICATE"))
            errors.append({"row": r.row_id, "reason": "DUPLICATE", "error": "could not save row (duplicate or constraint)"})
            continue
        inserted.append(lead.enquiry_number)
        assigned_names.append(assigned_name)

    batch.imported = len(inserted)
    batch.status = "DONE"
    db.commit()
    if inserted:
        live.bump()
        # Best-effort assignment mails (fail-open, same as Excel confirm).
        try:
            from app.api.importer import _send_assignment_batches
            _send_assignment_batches(db, new_by_emp)
        except Exception as exc:
            log.error("sheets assignment mail failed: %s", exc)
    if not inserted and errors:
        # Apps Script treats HTTP 200 as synced and clears SEND. A rejected
        # enquiry must stay checked and show the duplicate or invalid reason.
        raise HTTPException(409, "; ".join(str(item.get("error") or "rejected") for item in errors)[:300])
    return {"batch_id": str(batch.id), "inserted": len(inserted),
            "enquiry_numbers": inserted, "employees": assigned_names,
            "duplicates": batch.duplicates,
            "invalid": batch.invalid, "errors": errors}


class SheetsProductCars(BaseModel):
    enquiry_number: str = ""
    product: str = ""
    cars: str = ""


@router.post("/product-cars")
async def update_product_cars(
    request: Request,
    db: Session = Depends(get_db),
    x_sheets_timestamp: str = Header(default=""),
    x_sheets_signature: str = Header(default=""),
):
    """Update product and car count on a lead that was already sent from the sheet."""
    raw = await request.body()
    _verify_signature(raw, x_sheets_timestamp, x_sheets_signature)
    body = SheetsProductCars.model_validate_json(raw)
    enquiry = (body.enquiry_number or "").strip()
    lead = db.query(Lead).filter(Lead.enquiry_number == enquiry, Lead.is_active.is_(True)).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    count, car_error = normalize_car_count(body.cars, body.product)
    if car_error:
        raise HTTPException(400, car_error)
    prod = _norm_product(db, body.product)
    lead.product_raw = (body.product or "").strip()
    lead.product_id = prod.id if prod else None
    lead.quantity_raw = str(count)
    lead.quantity_num = count
    apply_pricing_to_lead(lead, product=prod)
    db.commit()
    live.bump()
    return {
        "enquiry_number": lead.enquiry_number,
        "cars": count,
        "product": prod.name if prod else lead.product_raw,
    }


@router.post("/next-employee")
async def next_employee(
    request: Request,
    db: Session = Depends(get_db),
    x_sheets_timestamp: str = Header(default=""),
    x_sheets_signature: str = Header(default=""),
):
    """Name of the next free employee. Does not create a lead."""
    raw = await request.body()
    _verify_signature(raw, x_sheets_timestamp, x_sheets_signature)
    chosen = choose_next_employee(db, ignore_limit=True)
    return {"employee": chosen.name if chosen else ""}


@router.get("/batches/{bid}/errors")
def sheets_errors(bid: UUID, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    rows = db.query(ImportError).filter_by(batch_id=bid).order_by(ImportError.row_number).all()
    return {"batch_id": str(bid), "total": len(rows),
            "items": [_serialize_error(e) for e in rows]}
