"""Excel import: selected columns only + admin review of duplicate/invalid rows."""
import os
import re
import tempfile
from uuid import UUID

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import admin_only
from app.db.session import get_db
from app.models import (
    ImportBatch, ImportError, Lead, LeadSource, LeadStatus, LeadStatusHistory,
    Product, ProductAlias, User,
)
from app.services.lead_service import auto_assign, next_enquiry_number
from app.services.normalize import (
    PRODUCT_ALIASES, SOURCE_ALIASES, norm_key, parse_excel_date, parse_quantity,
)

router = APIRouter(prefix="/api/import", tags=["import"])
PENDING: dict[str, list[dict]] = {}

# Tracker sheet detection (order-free).
TRACKER_MARKERS = {"enq no", "date received", "lead name", "city", "lead source"}

# Excel Leads Tracker column indexes (0-based)
COL_ENQ, COL_DATE, COL_NAME, COL_COMPANY = 0, 1, 2, 3
COL_CITY, COL_CARS, COL_SOURCE, COL_PRODUCT = 5, 6, 16, 19


class ErrorUpdate(BaseModel):
    name: str | None = None
    city: str | None = None
    company: str | None = None
    cars: str | None = None
    source: str | None = None
    product: str | None = None
    enq: str | int | float | None = None
    date: str | None = None


class PromoteIn(BaseModel):
    force: bool = False


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


def _norm_source(db: Session, raw: str) -> LeadSource | None:
    text = (raw or "").strip()
    if not text:
        text = "Others"
    canon = SOURCE_ALIASES.get(norm_key(text), text)
    src = db.query(LeadSource).filter(func.lower(LeadSource.name) == canon.lower()).first()
    if src:
        return src
    return db.query(LeadSource).filter(func.lower(LeadSource.name) == "others").first()


def _norm_product(db: Session, raw: str) -> Product | None:
    if not raw or not str(raw).strip():
        return None
    k = norm_key(str(raw))
    canon = PRODUCT_ALIASES.get(k, str(raw).strip())
    p = db.query(Product).filter(func.lower(Product.name) == canon.lower()).first()
    if p:
        return p
    al = db.query(ProductAlias).filter(func.lower(ProductAlias.alias) == k).first()
    return db.get(Product, al.product_id) if al else None


def _cell(r, idx):
    return r[idx] if len(r) > idx else None


def _json_safe_rec(rec: dict) -> dict:
    out = dict(rec)
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
        "city": raw.get("city", ""),
        "company": raw.get("company", ""),
        "cars": raw.get("cars", ""),
        "source": raw.get("source", ""),
        "product": raw.get("product", ""),
        "enq": raw.get("legacy_enq", raw.get("enq")),
        "date": raw.get("date"),
        "raw": raw,
    }


def _row_issue_messages(db: Session, raw: dict) -> list[str]:
    msgs: list[str] = []
    if not str(raw.get("name") or "").strip():
        msgs.append("missing name")
    legacy = raw.get("legacy_enq")
    if legacy is None:
        legacy = parse_legacy_enq(raw.get("enq"))
    if legacy is None:
        msgs.append("missing/invalid enquiry no")
    elif db.query(Lead).filter_by(legacy_enquiry_no=legacy).first():
        msgs.append("duplicate enquiry no")
    return msgs


def _create_lead_from_raw(db: Session, raw: dict, admin: User, *, force: bool = False) -> Lead:
    name = str(raw.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name is required")

    legacy = raw.get("legacy_enq")
    if legacy is None:
        legacy = parse_legacy_enq(raw.get("enq"))
    if legacy is None and not force:
        raise HTTPException(400, "Enquiry number is required — correct it first")
    if legacy is not None and db.query(Lead).filter_by(legacy_enquiry_no=legacy).first():
        if force:
            legacy = None
        else:
            raise HTTPException(
                400,
                "Enquiry number already exists. Correct it, or Force add to create without that Excel enquiry no.",
            )

    company = str(raw.get("company") or "").strip()
    city = str(raw.get("city") or "").strip()
    cars = str(raw.get("cars") or "").strip()
    src = _norm_source(db, str(raw.get("source") or ""))
    prod = _norm_product(db, str(raw.get("product") or ""))
    st = _default_status(db)

    lead = Lead(
        enquiry_number=next_enquiry_number(db),
        legacy_enquiry_no=legacy,
        enquiry_date=parse_excel_date(raw.get("date")),
        customer_name=name,
        company_name=company,
        contact_number="",
        contact_number_norm="",
        city=city,
        quantity_raw=cars,
        quantity_num=parse_quantity(cars),
        source_id=src.id if src else None,
        product_id=prod.id if prod else None,
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

    preview, duplicates, invalids = [], [], []
    seen_enqs: set[int] = set()
    for i, r in enumerate(rows[1:], start=2):
        if not any(r):
            continue
        date_v = _cell(r, COL_DATE)
        if date_v is not None and not isinstance(date_v, (str, int, float, bool)):
            date_v = str(date_v)
        rec = {
            "row": i,
            "enq": _cell(r, COL_ENQ),
            "date": date_v,
            "name": str(_cell(r, COL_NAME) or "").strip(),
            "company": str(_cell(r, COL_COMPANY) or "").strip(),
            "city": str(_cell(r, COL_CITY) or "").strip(),
            "cars": str(_cell(r, COL_CARS) or "").strip(),
            "source": str(_cell(r, COL_SOURCE) or "").strip(),
            "product": str(_cell(r, COL_PRODUCT) or "").strip(),
        }
        legacy = parse_legacy_enq(rec["enq"])
        rec["legacy_enq"] = legacy

        errs: list[str] = []
        dup_reasons: list[str] = []
        if not rec["name"]:
            errs.append("missing name")
        if legacy is None:
            errs.append("missing/invalid enquiry no")
        else:
            if legacy in seen_enqs or db.query(Lead).filter_by(legacy_enquiry_no=legacy).first():
                dup_reasons.append("duplicate enquiry no")

        if dup_reasons:
            rec["dup"] = True
            rec["errors"] = dup_reasons
            duplicates.append(rec)
        elif errs:
            rec["errors"] = errs
            invalids.append(rec)
        else:
            seen_enqs.add(legacy)  # type: ignore[arg-type]
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
        "valid": valid,
        "preview": [r for r in preview if not r.get("dup") and not r.get("errors")][:50],
        "duplicate_rows": duplicates,
        "invalid_rows": invalids,
        "fields": [
            "enquiry no", "received date", "name", "company/organisation (optional)",
            "city", "no. of cars", "lead source", "product/type",
        ],
        "note": "Only listed columns are imported. Admin can review duplicates/invalid and Add to leads or Delete.",
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
        legacy = rec.get("legacy_enq")
        if legacy is not None and db.query(Lead).filter_by(legacy_enquiry_no=legacy).first():
            db.add(ImportError(
                batch_id=bid, row_number=rec["row"], raw=_json_safe_rec(rec),
                error="duplicate enquiry no", reason="DUPLICATE",
            ))
            continue

        cars = str(rec.get("cars") or "")
        src = _norm_source(db, str(rec.get("source") or ""))
        prod = _norm_product(db, str(rec.get("product") or ""))
        lead = Lead(
            enquiry_number=next_enquiry_number(db),
            legacy_enquiry_no=legacy,
            enquiry_date=parse_excel_date(rec.get("date")),
            customer_name=str(rec.get("name") or ""),
            company_name=str(rec.get("company") or ""),
            contact_number="",
            contact_number_norm="",
            city=str(rec.get("city") or ""),
            quantity_raw=cars,
            quantity_num=parse_quantity(cars),
            source_id=src.id if src else None,
            product_id=prod.id if prod else None,
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
    for key in ("name", "city", "company", "cars", "source", "product", "date"):
        if key in data and data[key] is not None:
            raw[key] = str(data[key]).strip() if key != "date" else data[key]
    if "enq" in data and data["enq"] is not None:
        raw["enq"] = data["enq"]
        raw["legacy_enq"] = parse_legacy_enq(data["enq"])
    e.raw = raw
    msgs = _row_issue_messages(db, raw)
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
