"""Excel import: preview, confirm, review skipped rows, promote wrongly flagged to leads."""
import os
import re
import tempfile
from uuid import UUID

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import admin_only
from app.db.session import get_db
from app.models import ImportBatch, ImportError, Lead, LeadSource, LeadStatus, LeadStatusHistory, Product, User
from app.services.lead_service import auto_assign, next_enquiry_number
from app.services.normalize import PRODUCT_ALIASES, SOURCE_ALIASES, norm_key, norm_phone, parse_excel_date

router = APIRouter(prefix="/api/import", tags=["import"])
PENDING: dict[str, list[dict]] = {}

TRACKER_MARKERS = {"enq no", "date received", "lead name", "contact no", "city"}


class ErrorUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    city: str | None = None
    enq: str | int | float | None = None
    date: str | None = None


class PromoteIn(BaseModel):
    force: bool = False  # if true, drop conflicting legacy enquiry no and still create


def parse_legacy_enq(raw) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(float(str(raw).strip()))
    except (ValueError, TypeError):
        return None


def suggest_sheet(names: list[str]) -> str:
    for n in names:
        k = n.lower()
        if "tracker" in k or ("lead" in k and "dashboard" not in k and "meta" not in k):
            return n
    return names[0] if names else ""


def header_score(header: list[str]) -> int:
    normed = {re.sub(r"\s+", " ", (h or "").strip().lower()) for h in header}
    hits = 0
    for m in TRACKER_MARKERS:
        if any(m in h or h in m for h in normed if h):
            hits += 1
    return hits


def _default_status(db: Session) -> LeadStatus:
    st = db.query(LeadStatus).filter(LeadStatus.name == "New Lead").first()
    if not st:
        raise HTTPException(500, "New Lead status missing — run seed")
    return st


def _product_id(db: Session, raw) -> object | None:
    value = str(raw or '').strip()
    if not value:
        return None
    canonical = PRODUCT_ALIASES.get(norm_key(value), value)
    product = db.query(Product).filter(Product.name.ilike(canonical)).first()
    return product.id if product else None


def _source_id(db: Session, raw) -> object | None:
    value = str(raw or '').strip()
    if not value:
        return None
    canonical = SOURCE_ALIASES.get(norm_key(value), value)
    source = db.query(LeadSource).filter(LeadSource.name.ilike(canonical)).first()
    return source.id if source else None


def _json_safe_rec(rec: dict) -> dict:
    out = dict(rec)
    # Ensure JSONB-friendly values
    if "date" in out and out["date"] is not None and not isinstance(out["date"], (str, int, float, bool)):
        out["date"] = str(out["date"])
    out.pop("dup", None)
    return out


def _serialize_error(e: ImportError) -> dict:
    raw = e.raw or {}
    return {
        "id": str(e.id),
        "batch_id": str(e.batch_id),
        "row_number": e.row_number,
        "reason": e.reason,
        "error": e.error,
        "name": raw.get("name", ""),
        "phone": raw.get("phone", ""),
        "city": raw.get("city", ""),
        "enq": raw.get("legacy_enq", raw.get("enq")),
        "date": raw.get("date"),
        "raw": raw,
    }


def _create_lead_from_raw(db: Session, raw: dict, admin: User, *, force: bool = False) -> Lead:
    name = str(raw.get("name") or "").strip()
    phone = str(raw.get("phone") or "").strip()
    city = str(raw.get("city") or "").strip()
    if not name:
        raise HTTPException(400, "Name is required")
    if not phone:
        raise HTTPException(400, "Phone is required")
    phone_n = norm_phone(phone)
    if not phone_n:
        raise HTTPException(400, "Invalid phone number")
    if db.query(Lead).filter_by(contact_number_norm=phone_n).first():
        raise HTTPException(400, "Phone already exists on another lead — correct the phone first")

    legacy = raw.get("legacy_enq")
    if legacy is None:
        legacy = parse_legacy_enq(raw.get("enq"))
    if legacy is not None and db.query(Lead).filter_by(legacy_enquiry_no=legacy).first():
        if force:
            legacy = None  # keep unique CRM enquiry; drop conflicting excel enq
        else:
            raise HTTPException(
                400,
                "Enquiry number already exists. Correct it, or promote with force to create without that Excel enquiry no.",
            )

    st = _default_status(db)
    lead = Lead(
        enquiry_number=next_enquiry_number(db),
        legacy_enquiry_no=legacy,
        enquiry_date=parse_excel_date(raw.get("date")),
        customer_name=name,
        contact_number=phone,
        contact_number_norm=phone_n,
        city=city,
        company_name=str(raw.get("company") or "").strip(),
        alternate_contact=str(raw.get("alternate_contact") or "").strip(),
        email=str(raw.get("email") or "").strip(),
        requirement=str(raw.get("requirement") or "").strip(),
        quantity_raw=str(raw.get("quantity") or "").strip(),
        priority=str(raw.get("priority") or "").strip(),
        first_contact_notes=str(raw.get("remarks") or "").strip(),
        product_id=_product_id(db, raw.get("product")),
        source_id=_source_id(db, raw.get("source")),
        status_id=st.id,
        sla_state="PENDING",
        created_by=admin.id,
    )
    db.add(lead)
    db.flush()
    db.add(LeadStatusHistory(
        lead_id=lead.id, old_status_id=None, new_status_id=st.id,
        changed_by=admin.id, reason="import review promote",
    ))
    auto_assign(db, lead, admin)
    return lead


@router.post("/excel")
async def upload_excel(file: UploadFile = File(...), sheet: str = Form(""),
                       db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Please upload an .xlsx file")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(file.filename))
    tmp = tempfile.NamedTemporaryFile(prefix="crm_import_", suffix=".xlsx", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        wb = openpyxl.load_workbook(tmp.name, data_only=True, read_only=True)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    names = wb.sheetnames
    if sheet and sheet not in names:
        raise HTTPException(400, f"Sheet '{sheet}' not found. Available: {', '.join(names)}")
    if not sheet:
        return {"batch_id": None, "sheets": names, "suggested": suggest_sheet(names)}
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    if not rows or not any(rows[0]):
        raise HTTPException(400, f"Sheet '{sheet}' is empty")
    header = [str(c or "").strip() for c in rows[0]]
    if header_score(header) < 3:
        raise HTTPException(
            400,
            f"Sheet '{sheet}' does not look like the Leads Tracker "
            f"(found headers: {', '.join(h for h in header if h)[:120]}). "
            "Please select the tracker sheet.")

    product_index = next((idx for idx, value in enumerate(header) if "product" in value.lower() or "parking" in value.lower()), None)
    source_index = next((idx for idx, value in enumerate(header) if "source" in value.lower()), None)
    preview, duplicates, invalids = [], [], []
    seen_phones: set[str] = set()
    seen_enqs: set[int] = set()
    for i, r in enumerate(rows[1:], start=2):
        if not any(r):
            continue
        rec = {
            "row": i,
            "enq": r[0] if len(r) > 0 else None,
            "date": r[1] if len(r) > 1 else None,
            "name": str(r[2] or "").strip() if len(r) > 2 else "",
            "company": str(r[3] or "").strip() if len(r) > 3 else "",
            "phone": str(r[4] or "").strip() if len(r) > 4 else "",
            "city": str(r[5] or "").strip() if len(r) > 5 else "",
            "requirement": str(r[6] or "").strip() if len(r) > 6 else "",
            "quantity": str(r[7] or "").strip() if len(r) > 7 else "",
            "remarks": str(r[8] or "").strip() if len(r) > 8 else "",
            "priority": str(r[18] or "").strip() if len(r) > 18 else "",
            "email": str(r[29] or "").strip() if len(r) > 29 else "",
            "alternate_contact": str(r[30] or "").strip() if len(r) > 30 else "",
            "product": str(r[product_index] or "").strip() if product_index is not None and len(r) > product_index else "",
            "source": str(r[source_index] or "").strip() if source_index is not None and len(r) > source_index else "",
        }
        errs: list[str] = []
        if not rec["name"]:
            errs.append("missing name")
        if not rec["phone"]:
            errs.append("missing phone")

        phone_n = norm_phone(rec["phone"])
        legacy = parse_legacy_enq(rec["enq"])
        rec["legacy_enq"] = legacy
        rec["phone_norm"] = phone_n
        if rec["date"] is not None and not isinstance(rec["date"], (str, int, float, bool)):
            rec["date"] = str(rec["date"])

        dup_reasons: list[str] = []
        if phone_n:
            if phone_n in seen_phones or db.query(Lead).filter_by(contact_number_norm=phone_n).first():
                dup_reasons.append("duplicate phone")
        else:
            errs.append("invalid phone")
        if legacy is not None:
            if legacy in seen_enqs or db.query(Lead).filter_by(legacy_enquiry_no=legacy).first():
                dup_reasons.append("duplicate enquiry no")
        else:
            errs.append("missing/invalid enquiry no")

        if dup_reasons:
            rec["dup"] = True
            rec["errors"] = dup_reasons
            duplicates.append(rec)
        elif errs:
            rec["errors"] = errs
            invalids.append(rec)
        else:
            if phone_n:
                seen_phones.add(phone_n)
            if legacy is not None:
                seen_enqs.add(legacy)
        preview.append(rec)

    batch = ImportBatch(
        file_name=safe_name, sheet_name=ws.title, total_rows=len(preview),
        duplicates=len(duplicates), invalid=len(invalids), status="PREVIEW", created_by=admin.id,
    )
    db.add(batch)
    db.commit()
    PENDING[str(batch.id)] = preview
    valid = len(preview) - len(duplicates) - len(invalids)
    return {
        "batch_id": str(batch.id), "sheets": names, "sheet": ws.title,
        "total": len(preview), "duplicates": len(duplicates), "invalid": len(invalids),
        "valid": valid, "preview": [r for r in preview if not r.get("dup") and not r.get("errors")][:50],
        "duplicate_rows": duplicates,
        "invalid_rows": invalids,
        "fields": ["enquiry no", "received date", "name", "phone", "city"],
        "note": "Review duplicates/invalid below. After confirm you can still correct and add wrongly flagged rows as leads.",
    }


@router.post("/{bid}/confirm")
def confirm(bid: UUID, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    batch = db.get(ImportBatch, bid)
    rows = PENDING.get(str(bid), [])
    if not batch or not rows:
        raise HTTPException(404, "Batch expired — re-upload")
    st = _default_status(db)
    ok = assigned = pending = 0
    for rec in rows:
        if rec.get("dup") or rec.get("errors"):
            db.add(ImportError(
                batch_id=bid, row_number=rec["row"], raw=_json_safe_rec(rec),
                error=",".join(rec.get("errors", ["duplicate"])),
                reason="DUPLICATE" if rec.get("dup") else "INVALID",
            ))
            continue
        phone_n = rec.get("phone_norm") or norm_phone(rec["phone"])
        if db.query(Lead).filter_by(contact_number_norm=phone_n).first():
            db.add(ImportError(batch_id=bid, row_number=rec["row"], raw=_json_safe_rec(rec),
                               error="duplicate phone", reason="DUPLICATE"))
            continue
        legacy = rec.get("legacy_enq")
        if legacy is not None and db.query(Lead).filter_by(legacy_enquiry_no=legacy).first():
            db.add(ImportError(batch_id=bid, row_number=rec["row"], raw=_json_safe_rec(rec),
                               error="duplicate enquiry no", reason="DUPLICATE"))
            continue

        lead = Lead(
            enquiry_number=next_enquiry_number(db),
            legacy_enquiry_no=legacy,
            enquiry_date=parse_excel_date(rec["date"]),
            customer_name=str(rec["name"] or ""),
            company_name=str(rec.get("company") or ""),
            contact_number=str(rec["phone"] or ""),
            contact_number_norm=phone_n,
            city=str(rec["city"] or ""),
            email=str(rec.get("email") or ""),
            alternate_contact=str(rec.get("alternate_contact") or ""),
            requirement=str(rec.get("requirement") or ""),
            quantity_raw=str(rec.get("quantity") or ""),
            priority=str(rec.get("priority") or ""),
            first_contact_notes=str(rec.get("remarks") or ""),
            product_id=_product_id(db, rec.get("product")),
            source_id=_source_id(db, rec.get("source")),
            status_id=st.id,
            sla_state="PENDING",
            created_by=admin.id,
        )
        db.add(lead)
        db.flush()
        db.add(LeadStatusHistory(
            lead_id=lead.id, old_status_id=None, new_status_id=st.id,
            changed_by=admin.id, reason="excel import",
        ))
        emp = auto_assign(db, lead, admin)
        if emp:
            assigned += 1
        else:
            pending += 1
        ok += 1
    batch.imported = ok
    batch.status = "DONE"
    db.commit()
    errors = db.query(ImportError).filter_by(batch_id=bid).order_by(ImportError.row_number).all()
    return {
        "batch_id": str(bid),
        "total": batch.total_rows,
        "imported": ok,
        "assigned": assigned,
        "pending": pending,
        "duplicates": batch.duplicates,
        "invalid": batch.invalid,
        "skipped": len(errors),
        "errors": [_serialize_error(e) for e in errors],
    }


@router.get("/batches")
def list_batches(db: Session = Depends(get_db), _: User = Depends(admin_only), limit: int = 20):
    rows = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(limit).all()
    return [{
        "id": str(b.id), "file_name": b.file_name, "sheet_name": b.sheet_name,
        "status": b.status, "total_rows": b.total_rows, "imported": b.imported,
        "duplicates": b.duplicates, "invalid": b.invalid,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    } for b in rows]


@router.get("/{bid}/errors")
def list_errors(bid: UUID, reason: str = "", db: Session = Depends(get_db), _: User = Depends(admin_only)):
    q = db.query(ImportError).filter_by(batch_id=bid)
    if reason:
        q = q.filter(ImportError.reason == reason.upper())
    rows = q.order_by(ImportError.row_number).all()
    return {
        "batch_id": str(bid),
        "total": len(rows),
        "duplicates": sum(1 for e in rows if e.reason == "DUPLICATE"),
        "invalid": sum(1 for e in rows if e.reason == "INVALID"),
        "items": [_serialize_error(e) for e in rows],
    }


@router.patch("/errors/{eid}")
def update_error(eid: UUID, body: ErrorUpdate, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    e = db.get(ImportError, eid)
    if not e:
        raise HTTPException(404, "Skipped row not found")
    raw = dict(e.raw or {})
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        raw["name"] = str(data["name"]).strip()
    if "phone" in data and data["phone"] is not None:
        raw["phone"] = str(data["phone"]).strip()
        raw["phone_norm"] = norm_phone(raw["phone"])
    if "city" in data and data["city"] is not None:
        raw["city"] = str(data["city"]).strip()
    if "date" in data and data["date"] is not None:
        raw["date"] = data["date"]
    if "enq" in data and data["enq"] is not None:
        raw["enq"] = data["enq"]
        raw["legacy_enq"] = parse_legacy_enq(data["enq"])
    e.raw = raw
    # refresh error message after edit
    msgs = []
    phone_n = raw.get("phone_norm") or norm_phone(raw.get("phone", ""))
    legacy = raw.get("legacy_enq")
    if not raw.get("name"):
        msgs.append("missing name")
    if not phone_n:
        msgs.append("invalid phone")
    elif db.query(Lead).filter_by(contact_number_norm=phone_n).first():
        msgs.append("duplicate phone")
    if legacy is None:
        msgs.append("missing/invalid enquiry no")
    elif db.query(Lead).filter_by(legacy_enquiry_no=legacy).first():
        msgs.append("duplicate enquiry no")
    e.error = ", ".join(msgs) if msgs else "ready to add"
    e.reason = "DUPLICATE" if any("duplicate" in m for m in msgs) else ("INVALID" if msgs else e.reason)
    db.commit()
    db.refresh(e)
    return _serialize_error(e)


@router.post("/errors/{eid}/promote")
def promote_error(eid: UUID, body: PromoteIn | None = None, db: Session = Depends(get_db),
                  admin: User = Depends(admin_only)):
    e = db.get(ImportError, eid)
    if not e:
        raise HTTPException(404, "Skipped row not found")
    force = bool(body and body.force)
    lead = _create_lead_from_raw(db, e.raw or {}, admin, force=force)
    batch = db.get(ImportBatch, e.batch_id)
    if batch:
        batch.imported = (batch.imported or 0) + 1
        if e.reason == "DUPLICATE" and batch.duplicates:
            batch.duplicates = max(0, batch.duplicates - 1)
        if e.reason == "INVALID" and batch.invalid:
            batch.invalid = max(0, batch.invalid - 1)
    db.delete(e)
    db.commit()
    return {
        "ok": True,
        "lead_id": str(lead.id),
        "enquiry_number": lead.enquiry_number,
        "assigned": bool(lead.primary_employee_id),
    }


@router.delete("/errors/{eid}")
def dismiss_error(eid: UUID, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    e = db.get(ImportError, eid)
    if not e:
        raise HTTPException(404, "Skipped row not found")
    db.delete(e)
    db.commit()
    return {"ok": True}
