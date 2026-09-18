"""Verify duplicate/invalid handling for Excel import + Google Sheets sync.

Shared rules (classify_intake_row):
  DUPLICATE — phone or enquiry no already in batch/DB
  INVALID   — missing name, bad/missing phone, missing enquiry no, bad email
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from io import BytesIO
from pathlib import Path

import httpx
import openpyxl

BASE = "http://127.0.0.1:8000"
results: list[tuple[str, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def _sign(secret: str, raw: bytes) -> tuple[str, str]:
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return ts, sig


def _xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leads Tracker"
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main() -> None:
    from app.core.config import settings

    secret = settings.SHEETS_WEBHOOK_SECRET or ""
    check("SHEETS_WEBHOOK_SECRET configured", bool(secret), "set in .env" if secret else "missing")

    c = httpx.Client(base_url=BASE, timeout=60.0)
    r = c.get("/health")
    check("backend health", r.status_code == 200 and r.json().get("ok") is True, str(r.status_code))

    login = c.post("/api/auth/login", json={"email": "admin@crm.local", "password": "Admin123!"}).json()
    ah = {"Authorization": f"Bearer {login['access_token']}"}
    check("admin login", "access_token" in login)

    # Unique markers far above existing legacy enquiry nos (max ~500 in this DB).
    tag = uuid.uuid4().hex[:8]
    digits = "".join(ch for ch in uuid.uuid4().hex if ch.isdigit()) + "0000000000"
    base = 8_000_000 + (int(uuid.uuid4().hex[:6], 16) % 1_000_000)

    def phone_at(prefix: str, salt: int) -> str:
        body = f"{int(digits[:8]) + salt:08d}"[-8:]
        p = (prefix[:2] + body)[:10]
        if p[0] not in "6789":
            p = "9" + p[1:]
        return p

    enq_ok = base
    enq_dup = base + 1
    enq_inv = base + 2
    phone_ok = phone_at("98", 1)
    phone_dup = phone_at("97", 2)
    phone_extra = phone_at("96", 3)
    phone_inv_name = phone_at("95", 4)
    phone_inv_email = phone_at("94", 5)
    phone_no_enq = phone_at("93", 6)
    phone_excel = phone_at("92", 7)
    phone_excel_dup_enq = phone_at("90", 8)
    phone_excel_noname = phone_at("89", 9)
    phone_excel_bademail = phone_at("88", 10)
    phone_excel_noenq = phone_at("87", 11)
    phone_fix_sheets = phone_at("91", 12)
    phone_fix_excel = phone_at("86", 13)
    enq_fix_sheets = base + 50
    enq_fix_excel = base + 120

    # Seed one lead so "already in DB" duplicates can be detected
    seed_payload = {
        "sheet_id": f"qa-seed-{tag}",
        "rows": [{
            "row_id": 2,
            "external_key": f"seed-{tag}",
            "enq": enq_dup,
            "date": "2026-09-18",
            "name": f"Seed Dup {tag}",
            "phone": phone_dup,
            "email": f"seed.{tag}@example.com",
            "city": "Chennai",
            "source": "Others",
            "product": "",
        }],
    }
    raw = json.dumps(seed_payload).encode()
    ts, sig = _sign(secret, raw)
    r = c.post(
        "/api/sheets/rows",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Sheets-Timestamp": ts,
            "X-Sheets-Signature": sig,
        },
    )
    check("sheets seed valid lead", r.status_code == 200 and r.json().get("inserted") == 1, f"{r.status_code} {r.text[:200]}")

    # ---- Google Sheets: mix of valid / duplicate / invalid ----
    sheets_payload = {
        "sheet_id": f"qa-mix-{tag}",
        "rows": [
            {
                "row_id": 2, "external_key": f"ok-{tag}",
                "enq": enq_ok, "date": "2026-09-18", "name": f"Sheets OK {tag}",
                "phone": phone_ok, "email": f"ok.{tag}@example.com", "city": "Madurai",
                "source": "Others", "product": "",
            },
            {
                "row_id": 3, "external_key": f"dup-phone-{tag}",
                "enq": enq_ok + 10, "date": "2026-09-18", "name": f"Sheets DupPhone {tag}",
                "phone": phone_dup, "email": f"dupphone.{tag}@example.com", "city": "Salem",
                "source": "Others", "product": "",
            },
            {
                "row_id": 4, "external_key": f"dup-enq-{tag}",
                "enq": enq_dup, "date": "2026-09-18", "name": f"Sheets DupEnq {tag}",
                "phone": phone_extra, "email": f"dupenq.{tag}@example.com", "city": "Erode",
                "source": "Others", "product": "",
            },
            {
                "row_id": 5, "external_key": f"inv-name-{tag}",
                "enq": enq_inv, "date": "2026-09-18", "name": "",
                "phone": phone_inv_name, "email": f"invname.{tag}@example.com", "city": "Trichy",
                "source": "Others", "product": "",
            },
            {
                "row_id": 6, "external_key": f"inv-phone-{tag}",
                "enq": enq_inv + 1, "date": "2026-09-18", "name": f"Sheets BadPhone {tag}",
                "phone": "12345", "email": f"badphone.{tag}@example.com", "city": "Coimbatore",
                "source": "Others", "product": "",
            },
            {
                "row_id": 7, "external_key": f"inv-email-{tag}",
                "enq": enq_inv + 2, "date": "2026-09-18", "name": f"Sheets BadEmail {tag}",
                "phone": phone_inv_email, "email": "not-an-email", "city": "Vellore",
                "source": "Others", "product": "",
            },
            {
                "row_id": 8, "external_key": f"inv-enq-{tag}",
                "enq": "", "date": "2026-09-18", "name": f"Sheets NoEnq {tag}",
                "phone": phone_no_enq, "email": f"noenq.{tag}@example.com", "city": "Tanjore",
                "source": "Others", "product": "",
            },
        ],
    }

    raw = json.dumps(sheets_payload).encode()
    ts, sig = _sign(secret, raw)
    r = c.post(
        "/api/sheets/rows",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Sheets-Timestamp": ts,
            "X-Sheets-Signature": sig,
        },
    )
    check("sheets mixed push HTTP 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    body = r.json() if r.status_code == 200 else {}
    check("sheets inserted exactly 1 valid", body.get("inserted") == 1, str(body.get("inserted")))
    check("sheets duplicates >= 2 (phone+enq)", (body.get("duplicates") or 0) >= 2, str(body.get("duplicates")))
    check("sheets invalid >= 4 (name/phone/email/enq)", (body.get("invalid") or 0) >= 4, str(body.get("invalid")))
    reasons = {e.get("reason") for e in body.get("errors") or []}
    check("sheets errors include DUPLICATE", "DUPLICATE" in reasons, str(reasons))
    check("sheets errors include INVALID", "INVALID" in reasons, str(reasons))
    sheets_batch = body.get("batch_id")

    if sheets_batch:
        r = c.get(f"/api/import/{sheets_batch}/errors", headers=ah)
        check("sheets review via /import/{id}/errors", r.status_code == 200, str(r.status_code))
        items = (r.json() or {}).get("items") or []
        check("sheets review queue has skipped rows", len(items) >= 6, str(len(items)))
        dups = [x for x in items if x.get("reason") == "DUPLICATE"]
        invs = [x for x in items if x.get("reason") == "INVALID"]
        check("sheets review has duplicates", len(dups) >= 2, str(len(dups)))
        check("sheets review has invalids", len(invs) >= 4, str(len(invs)))

        # Correct an invalid row then promote
        inv = next((x for x in invs if "missing name" in (x.get("error") or "")), invs[0] if invs else None)
        if inv:
            r = c.patch(
                f"/api/import/errors/{inv['id']}",
                headers=ah,
                json={"name": f"Fixed Sheets {tag}", "phone": phone_fix_sheets, "enq": enq_fix_sheets, "email": f"fixed.{tag}@example.com"},
            )
            check("sheets correct invalid row", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
            ready = r.json() if r.status_code == 200 else {}
            check("sheets corrected row ready", (ready.get("error") or "") == "ready to add", str(ready.get("error")))
            r = c.post(f"/api/import/errors/{inv['id']}/promote", headers=ah, json={"force": False})
            check("sheets promote corrected row", r.status_code == 200, f"{r.status_code} {r.text[:200]}")

        # Duplicate promote without force should fail
        if dups:
            r = c.post(f"/api/import/errors/{dups[0]['id']}/promote", headers=ah, json={"force": False})
            check("sheets promote duplicate blocked", r.status_code == 400, f"{r.status_code} {r.text[:160]}")

    # Batches list includes sheets DONE batch
    r = c.get("/api/import/batches", headers=ah)
    batches = r.json() if r.status_code == 200 else []
    sheets_batches = [b for b in batches if b.get("source") == "sheets" and sheets_batch and b.get("id") == sheets_batch]
    check("sheets batch listed for admin review", bool(sheets_batches), f"found={len(sheets_batches)}")

    # ---- Excel import: same classification ----
    header = [
        "Enq no", "Date Received", "Lead Name / Full Name", "Company / Organisation",
        "Contact No.", "City", "No. of Cars", "Requirement", "Quantity", "Remarks",
        "", "", "", "Status", "", "", "Lead Source", "", "Priority", "Product / Type",
        "", "", "", "", "", "", "", "", "", "Email ID", "Alternate",
    ]
    while len(header) < 31:
        header.append("")
    header[29] = "Email ID"
    header[30] = "Alternate"

    excel_enq = enq_ok + 100
    rows = [
        header,
        [excel_enq, "2026-09-18", f"Excel OK {tag}", "Co", phone_excel, "Chennai", "1", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "", "", "", "", "", "", "", "", "", "", f"excel.ok.{tag}@example.com", ""],
        [excel_enq + 1, "2026-09-18", f"Excel DupPhone {tag}", "Co", phone_dup, "Chennai", "1", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "", "", "", "", "", "", "", "", "", "", f"excel.dup.{tag}@example.com", ""],
        [enq_dup, "2026-09-18", f"Excel DupEnq {tag}", "Co", phone_excel_dup_enq, "Chennai", "1", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "", "", "", "", "", "", "", "", "", "", f"excel.dupenq.{tag}@example.com", ""],
        [excel_enq + 2, "2026-09-18", "", "Co", phone_excel_noname, "Chennai", "1", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "", "", "", "", "", "", "", "", "", "", f"excel.noname.{tag}@example.com", ""],
        [excel_enq + 3, "2026-09-18", f"Excel BadPhone {tag}", "Co", "abc", "Chennai", "1", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "", "", "", "", "", "", "", "", "", "", f"excel.badphone.{tag}@example.com", ""],
        [excel_enq + 4, "2026-09-18", f"Excel BadEmail {tag}", "Co", phone_excel_bademail, "Chennai", "1", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "", "", "", "", "", "", "", "", "", "", "bad-email", ""],
        ["", "2026-09-18", f"Excel NoEnq {tag}", "Co", phone_excel_noenq, "Chennai", "1", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "", "", "", "", "", "", "", "", "", "", f"excel.noenq.{tag}@example.com", ""],
    ]

    xbytes = _xlsx(rows)
    files = {"file": ("qa_intake.xlsx", xbytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = c.post("/api/import/excel", headers=ah, files=files, data={"sheet": "Leads Tracker"})
    check("excel preview HTTP 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    prev = r.json() if r.status_code == 200 else {}
    check("excel valid == 1", prev.get("valid") == 1, str(prev.get("valid")))
    check("excel duplicates >= 2", (prev.get("duplicates") or 0) >= 2, str(prev.get("duplicates")))
    check("excel invalid >= 4", (prev.get("invalid") or 0) >= 4, str(prev.get("invalid")))
    check("excel duplicate_rows present", len(prev.get("duplicate_rows") or []) >= 2, str(len(prev.get("duplicate_rows") or [])))
    check("excel invalid_rows present", len(prev.get("invalid_rows") or []) >= 4, str(len(prev.get("invalid_rows") or [])))
    excel_batch = prev.get("batch_id")

    if excel_batch:
        r = c.post(f"/api/import/{excel_batch}/confirm", headers=ah)
        check("excel confirm HTTP 200", r.status_code == 200, f"{r.status_code} {r.text[:250]}")
        conf = r.json() if r.status_code == 200 else {}
        check("excel imported == 1", conf.get("imported") == 1, str(conf.get("imported")))
        check("excel confirm kept duplicates", (conf.get("duplicates") or 0) >= 2, str(conf.get("duplicates")))
        check("excel confirm kept invalid", (conf.get("invalid") or 0) >= 4, str(conf.get("invalid")))
        errs = conf.get("errors") or []
        check("excel review queue after confirm", len(errs) >= 6, str(len(errs)))
        dups = [e for e in errs if e.get("reason") == "DUPLICATE"]
        invs = [e for e in errs if e.get("reason") == "INVALID"]
        check("excel review duplicates", len(dups) >= 2, str(len(dups)))
        check("excel review invalids", len(invs) >= 4, str(len(invs)))

        inv = next((x for x in invs if "invalid email" in (x.get("error") or "")), invs[0] if invs else None)
        if inv:
            r = c.patch(
                f"/api/import/errors/{inv['id']}",
                headers=ah,
                json={"name": f"Fixed Excel {tag}", "phone": phone_fix_excel, "enq": enq_fix_excel, "email": f"fixed.excel.{tag}@example.com"},
            )
            check("excel correct invalid row", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
            r = c.post(f"/api/import/errors/{inv['id']}/promote", headers=ah, json={"force": False})
            check("excel promote corrected row", r.status_code == 200, f"{r.status_code} {r.text[:200]}")

        if dups:
            r = c.post(f"/api/import/errors/{dups[0]['id']}/promote", headers=ah, json={"force": False})
            check("excel promote duplicate blocked", r.status_code == 400, f"{r.status_code} {r.text[:160]}")

    # HMAC rejection sanity
    bad = c.post(
        "/api/sheets/rows",
        content=b'{"sheet_id":"x","rows":[{"name":"A","phone":"9840098400","enq":1}]}',
        headers={"Content-Type": "application/json", "X-Sheets-Timestamp": str(int(time.time())), "X-Sheets-Signature": "deadbeef"},
    )
    check("sheets bad signature rejected", bad.status_code == 401, str(bad.status_code))

    print("\n==== SUMMARY ====")
    fails = [x for x in results if x[0] == "FAIL"]
    print(f"Total: {len(results)}  PASS: {len(results) - len(fails)}  FAIL: {len(fails)}")
    for _, n, d in fails:
        print(f"  FAIL: {n} — {d}")
    Path(__file__).resolve().parent.parent.joinpath(".qa_intake.json").write_text(
        json.dumps({"tag": tag, "sheets_batch": sheets_batch, "excel_batch": excel_batch}, indent=2)
    )


if __name__ == "__main__":
    main()
