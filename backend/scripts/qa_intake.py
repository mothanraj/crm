"""Verify duplicate/invalid handling for Excel import + manual Create Lead.

Shared rules (classify_intake_row):
  DUPLICATE — phone or enquiry no already in batch/DB
  INVALID   — bad phone / missing phone+email / bad email when phone missing
"""
from __future__ import annotations

import json
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
    c = httpx.Client(base_url=BASE, timeout=60.0)
    r = c.get("/health")
    check("backend health", r.status_code == 200 and r.json().get("ok") is True, str(r.status_code))

    login = c.post("/api/auth/login", json={"email": "admin@crm.local", "password": "Admin123!"}).json()
    ah = {"Authorization": f"Bearer {login['access_token']}"}
    check("admin login", "access_token" in login)

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
    phone_dup = phone_at("97", 2)
    phone_excel = phone_at("92", 7)
    phone_excel_dup_enq = phone_at("90", 8)
    phone_excel_noname = phone_at("89", 9)
    phone_excel_bademail = phone_at("88", 10)
    phone_excel_noenq = phone_at("87", 11)
    phone_fix_excel = phone_at("86", 13)
    enq_fix_excel = base + 120

    # Seed one lead so "already in DB" duplicates can be detected
    r = c.post(
        "/api/leads",
        headers=ah,
        json={
            "enquiry_number": str(enq_dup),
            "enquiry_date": "2026-09-18",
            "customer_name": f"Seed Dup {tag}",
            "contact_number": phone_dup,
            "email": f"seed.{tag}@example.com",
            "city": "Chennai",
            "source_name": "Others",
            "product_name": "Puzzle Parking",
            "number_of_cars": "2",
        },
    )
    check("create-lead seed valid lead", r.status_code == 200, f"{r.status_code} {r.text[:200]}")

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
        [excel_enq, "2026-09-18", f"Excel OK {tag}", "Co", phone_excel, "Chennai", "2", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "Puzzle Parking", "", "", "", "", "", "", "", "", "", f"excel.ok.{tag}@example.com", ""],
        [excel_enq + 1, "2026-09-18", f"Excel DupPhone {tag}", "Co", phone_dup, "Chennai", "2", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "Puzzle Parking", "", "", "", "", "", "", "", "", "", f"excel.dup.{tag}@example.com", ""],
        [enq_dup, "2026-09-18", f"Excel DupEnq {tag}", "Co", phone_excel_dup_enq, "Chennai", "2", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "Puzzle Parking", "", "", "", "", "", "", "", "", "", f"excel.dupenq.{tag}@example.com", ""],
        [excel_enq + 2, "2026-09-18", "", "Co", phone_excel_noname, "Chennai", "2", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "Puzzle Parking", "", "", "", "", "", "", "", "", "", f"excel.noname.{tag}@example.com", ""],
        [excel_enq + 3, "2026-09-18", f"Excel BadPhone {tag}", "Co", "abc", "Chennai", "2", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "Puzzle Parking", "", "", "", "", "", "", "", "", "", f"excel.badphone.{tag}@example.com", ""],
        [excel_enq + 4, "2026-09-18", f"Excel BadEmail {tag}", "Co", phone_excel_bademail, "Chennai", "2", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "Puzzle Parking", "", "", "", "", "", "", "", "", "", "bad-email", ""],
        ["", "2026-09-18", f"Excel NoEnq {tag}", "Co", phone_excel_noenq, "Chennai", "2", "", "", "",
         "", "", "", "", "", "", "Others", "", "", "Puzzle Parking", "", "", "", "", "", "", "", "", "", f"excel.noenq.{tag}@example.com", ""],
    ]

    xbytes = _xlsx(rows)
    files = {"file": ("qa_intake.xlsx", xbytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = c.post("/api/import/excel", headers=ah, files=files, data={"sheet": "Leads Tracker"})
    check("excel preview HTTP 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    prev = r.json() if r.status_code == 200 else {}
    check("excel valid >= 1", (prev.get("valid") or 0) >= 1, str(prev.get("valid")))
    check("excel duplicates >= 2", (prev.get("duplicates") or 0) >= 2, str(prev.get("duplicates")))
    check("excel invalid >= 2", (prev.get("invalid") or 0) >= 2, str(prev.get("invalid")))
    excel_batch = prev.get("batch_id")

    if excel_batch:
        r = c.post(f"/api/import/{excel_batch}/confirm", headers=ah)
        check("excel confirm HTTP 200", r.status_code == 200, f"{r.status_code} {r.text[:250]}")
        conf = r.json() if r.status_code == 200 else {}
        check("excel imported >= 1", (conf.get("imported") or 0) >= 1, str(conf.get("imported")))
        errs = conf.get("errors") or []
        dups = [e for e in errs if e.get("reason") == "DUPLICATE"]
        invs = [e for e in errs if e.get("reason") == "INVALID"]
        check("excel review duplicates", len(dups) >= 1, str(len(dups)))
        check("excel review invalids", len(invs) >= 1, str(len(invs)))

        inv = next((x for x in invs if "invalid email" in (x.get("error") or "") or "missing" in (x.get("error") or "")), invs[0] if invs else None)
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

    # Sheets webhook must be gone
    gone = c.post("/api/sheets/rows", json={"sheet_id": "x", "rows": []})
    check("sheets endpoint removed", gone.status_code in (404, 405), str(gone.status_code))

    print("\n==== SUMMARY ====")
    fails = [x for x in results if x[0] == "FAIL"]
    print(f"Total: {len(results)}  PASS: {len(results) - len(fails)}  FAIL: {len(fails)}")
    for _, n, d in fails:
        print(f"  FAIL: {n} — {d}")
    Path(__file__).resolve().parent.parent.joinpath(".qa_intake.json").write_text(
        json.dumps({"tag": tag, "excel_batch": excel_batch}, indent=2)
    )


if __name__ == "__main__":
    main()
