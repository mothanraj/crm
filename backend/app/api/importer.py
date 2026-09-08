"""Excel import: upload → preview/validate/dedup → confirm. Never direct-insert."""
import os
import re
import tempfile
from uuid import UUID

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import admin_only
from app.db.session import get_db
from app.models import ImportBatch, ImportError, Lead, LeadActivity, LeadSource, LeadStatus, LeadStatusHistory, Product, ProductAlias, User
from app.services.lead_service import auto_assign, next_enquiry_number
from app.services.normalize import SOURCE_ALIASES, STATUS_ALIASES, norm_key, norm_phone, parse_excel_date, parse_quantity

router = APIRouter(prefix="/api/import", tags=["import"])
PENDING: dict[str, list[dict]] = {}

# Header signature of the Leads Tracker sheet (normalised, order-free).
TRACKER_MARKERS = {"enq no", "date received", "lead name", "contact no", "lead source"}


def parse_legacy_enq(raw) -> int | None:
    """Excel gives enquiry numbers as floats (1.0) or ints — handle both."""
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
    # fuzzy: marker matches if it appears inside any header cell
    hits = 0
    for m in TRACKER_MARKERS:
        if any(m in h or h in m for h in normed if h):
            hits += 1
    return hits


def _norm_source(db: Session, raw: str):
    canon = SOURCE_ALIASES.get(norm_key(raw), (raw or "").strip())
    return db.query(LeadSource).filter(func.lower(LeadSource.name) == canon.lower()).first()


def _norm_status(db: Session, raw: str):
    canon = STATUS_ALIASES.get(norm_key(raw), (raw or "").strip() or "New Lead")
    return db.query(LeadStatus).filter(func.lower(LeadStatus.name) == canon.lower()).first()


def _norm_product(db: Session, raw: str):
    from app.services.normalize import PRODUCT_ALIASES
    if not raw or not str(raw).strip():
        return None
    k = norm_key(str(raw))
    canon = PRODUCT_ALIASES.get(k, str(raw).strip())
    p = db.query(Product).filter(func.lower(Product.name) == canon.lower()).first()
    if not p:
        al = db.query(ProductAlias).filter(func.lower(ProductAlias.alias) == k).first()
        p = db.get(Product, al.product_id) if al else None
    return p


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
    # Sheet discovery mode: no sheet chosen → return sheet list + suggestion, parse nothing.
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
    preview, dup, invalid = [], 0, 0
    seen_phones = set()
    for i, r in enumerate(rows[1:], start=2):
        if not any(r):
            continue
        rec = {"row": i, "enq": r[0], "date": r[1], "name": r[2], "company": r[3],
               "phone": str(r[4] or ""), "city": r[5], "cars": r[6], "status": r[13],
               "source": r[16], "product": r[19], "owner": r[20], "email": r[29]}
        errs = []
        if not rec["name"] and not rec["phone"]:
            errs.append("missing name+phone")
        phone_n = norm_phone(rec["phone"])
        if phone_n and (db.query(Lead).filter_by(contact_number_norm=phone_n).first() or phone_n in seen_phones):
            rec["dup"] = True
            dup += 1
        legacy = parse_legacy_enq(rec["enq"])
        rec["legacy_enq"] = legacy
        if legacy is not None and db.query(Lead).filter_by(legacy_enquiry_no=legacy).first():
            rec["dup"] = True
            dup += 1
        if errs:
            rec["errors"] = errs
            invalid += 1
        if phone_n:
            seen_phones.add(phone_n)
        preview.append(rec)
    batch = ImportBatch(file_name=safe_name, sheet_name=ws.title, total_rows=len(preview),
                        duplicates=dup, invalid=invalid, status="PREVIEW", created_by=admin.id)
    db.add(batch)
    db.commit()
    PENDING[str(batch.id)] = preview
    valid = len(preview) - dup - invalid
    return {"batch_id": str(batch.id), "sheets": names, "sheet": ws.title,
            "total": len(preview), "duplicates": dup, "invalid": invalid,
            "valid": valid, "preview": preview[:50]}


@router.post("/{bid}/confirm")
def confirm(bid: UUID, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    batch = db.get(ImportBatch, bid)
    rows = PENDING.get(str(bid), [])
    if not batch or not rows:
        raise HTTPException(404, "Batch expired — re-upload")
    ok = 0
    for rec in rows:
        if rec.get("dup") or rec.get("errors"):
            db.add(ImportError(batch_id=bid, row_number=rec["row"], raw=rec,
                               error=",".join(rec.get("errors", ["duplicate"])),
                               reason="DUPLICATE" if rec.get("dup") else "INVALID"))
            continue
        src = _norm_source(db, str(rec["source"] or "Others"))
        st = _norm_status(db, str(rec["status"] or "New Lead"))
        prod = _norm_product(db, str(rec["product"] or ""))
        phone_n = norm_phone(rec["phone"])
        lead = Lead(enquiry_number=next_enquiry_number(db),
                    legacy_enquiry_no=rec.get("legacy_enq"),
                    enquiry_date=parse_excel_date(rec["date"]),
                    customer_name=str(rec["name"] or ""), company_name=str(rec["company"] or ""),
                    contact_number=str(rec["phone"] or ""), contact_number_norm=phone_n,
                    city=str(rec["city"] or ""), email=str(rec["email"] or ""),
                    quantity_raw=str(rec["cars"] or ""), quantity_num=parse_quantity(str(rec["cars"] or "")),
                    source_id=src.id if src else None, product_id=prod.id if prod else None,
                    status_id=st.id, created_by=admin.id)
        db.add(lead)
        db.flush()
        db.add(LeadStatusHistory(lead_id=lead.id, old_status_id=None, new_status_id=st.id,
                                 changed_by=admin.id, reason="excel import"))
        auto_assign(db, lead, admin)
        ok += 1
    batch.imported = ok
    batch.status = "DONE"
    db.commit()
    return {"total": batch.total_rows, "imported": ok, "duplicates": batch.duplicates,
            "invalid": batch.invalid, "skipped": batch.total_rows - ok - batch.duplicates - batch.invalid}
