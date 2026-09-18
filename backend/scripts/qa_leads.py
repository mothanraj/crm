"""Lead lifecycle API tests: assign, contact, status, follow-up, SLA, history."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
CTX = Path(__file__).resolve().parent.parent / ".qa_ctx.json"
results: list[tuple[str, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> None:
    ctx = json.loads(CTX.read_text())
    c = httpx.Client(base_url=BASE, timeout=30.0)

    admin = c.post("/api/auth/login", json={"email": "admin@crm.local", "password": "Admin123!"}).json()
    ah = {"Authorization": f"Bearer {admin['access_token']}"}

    # Ensure employee active
    emp_id = ctx["emp_id"]
    c.patch(f"/api/employees/{emp_id}", headers=ah, json={"is_active": True})
    emp = c.post("/api/auth/login", json={"email": ctx["emp_email"], "password": ctx["emp_pass"]}).json()
    eh = {"Authorization": f"Bearer {emp['access_token']}"}

    # Prefer an unassigned, non-converted lead; otherwise any non-converted lead.
    leads = c.get("/api/leads", headers=ah, params={"size": 50}).json()["items"]
    masters = c.get("/api/masters", headers=ah).json()
    statuses = {s["name"]: s["id"] for s in masters["statuses"]}
    converted_id = statuses.get("Converted")
    target = next((l for l in leads if l.get("primary_employee_id") is None and l.get("status_id") != converted_id), None)
    if not target:
        target = next((l for l in leads if l.get("status_id") != converted_id), None)
    if not target:
        target = leads[0] if leads else None
    check("have a lead for lifecycle", target is not None, str(len(leads)))
    if not target:
        return
    lid = target["id"]
    print(f"  using lead {target.get('enquiry_number')} id={lid}")

    # Assign to QA employee
    r = c.post(f"/api/leads/{lid}/assign", headers=ah, json={"employee_id": emp_id, "role": "PRIMARY"})
    check("admin assign lead", r.status_code == 200, f"{r.status_code} {r.text[:120]}")

    r = c.get(f"/api/leads/{lid}", headers=ah)
    lead = r.json()
    check("assigned employee set", lead.get("primary_employee_id") == emp_id, str(lead.get("primary_employee_id")))
    check("sla pending after assign", lead.get("sla_state") in ("PENDING", "OVERDUE"), str(lead.get("sla_state")))
    check("sla deadline set", bool(lead.get("sla_deadline")), str(lead.get("sla_deadline")))
    check("first contact cleared on assign", lead.get("first_contact_at") in (None, ""), str(lead.get("first_contact_at")))

    # Status should flip New Lead -> Assigned if it was New Lead
    # Employee can see it
    r = c.get(f"/api/leads/{lid}", headers=eh)
    check("assigned employee can view lead", r.status_code == 200, str(r.status_code))

    # Employee list only own leads
    r = c.get("/api/leads", headers=eh, params={"size": 100})
    emp_items = r.json().get("items", [])
    check("employee list only own", all(i.get("primary_employee_id") == emp_id for i in emp_items), f"count={len(emp_items)}")

    # Status without remarks rejected
    r = c.post(
        f"/api/leads/{lid}/status",
        headers=eh,
        json={"new_status_id": statuses["In Followup"], "reason": ""},
    )
    check("status without remarks -> 400", r.status_code == 400, str(r.status_code))

    # Invalid customer review
    r = c.post(
        f"/api/leads/{lid}/status",
        headers=eh,
        json={
            "new_status_id": statuses["In Followup"],
            "reason": "Called customer",
            "customer_review": "INVALID",
        },
    )
    check("invalid customer_review -> 400", r.status_code == 400, str(r.status_code))

    # Valid status change (also first contact)
    r = c.post(
        f"/api/leads/{lid}/status",
        headers=eh,
        json={
            "new_status_id": statuses["In Followup"],
            "reason": "Spoke with customer about requirement",
            "customer_review": "A (3-6 months)",
            "method": "Call",
        },
    )
    check("status change In Followup", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    body = r.json() if r.status_code == 200 else {}
    check("first contact completes SLA", body.get("sla_state") == "COMPLETED", str(body.get("sla_state")))

    r = c.get(f"/api/leads/{lid}", headers=eh)
    lead = r.json()
    check("first_contact_at set", bool(lead.get("first_contact_at")), str(lead.get("first_contact_at")))
    check("employee_remarks saved", "Spoke with customer" in (lead.get("employee_remarks") or ""), str(lead.get("employee_remarks"))[:80])
    check("customer_review saved", lead.get("customer_review") == "A (3-6 months)", str(lead.get("customer_review")))
    check("history present", len(lead.get("history") or []) >= 1, str(len(lead.get("history") or [])))
    check("work progress activity", any(a.get("type") == "Work Progress" for a in lead.get("activities") or []), str(lead.get("activities")))

    # Follow-up via activities
    follow_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = c.post(
        f"/api/leads/{lid}/activities",
        headers=eh,
        json={"activity_type": "Follow-up", "notes": "Call again in 2 days", "next_followup_at": follow_at},
    )
    check("create follow-up activity", r.status_code == 200, f"{r.status_code} {r.text[:100]}")
    r = c.get(f"/api/leads/{lid}", headers=eh)
    lead = r.json()
    check("next_followup_at set", bool(lead.get("next_followup_at")), str(lead.get("next_followup_at")))

    # Quotation status requires value optionally
    r = c.post(
        f"/api/leads/{lid}/status",
        headers=eh,
        json={
            "new_status_id": statuses["Quotation sent"],
            "reason": "Sent quotation by email",
            "customer_review": "A+ (Immediate)",
            "quotation_value": "150000.50",
        },
    )
    check("quotation status with value", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    r = c.get(f"/api/leads/{lid}", headers=eh)
    lead = r.json()
    check("quotation_value saved", lead.get("quotation_value") in ("150000.50", "150000.5"), str(lead.get("quotation_value")))

    # Convert
    r = c.post(
        f"/api/leads/{lid}/status",
        headers=eh,
        json={
            "new_status_id": statuses["Converted"],
            "reason": "Deal closed",
            "customer_review": "A+ (Immediate)",
            "sla_state": "COMPLETED",
        },
    )
    check("convert lead", r.status_code == 200, f"{r.status_code} {r.text[:120]}")

    # Employee cannot edit converted completed lead
    r = c.put(f"/api/leads/{lid}", headers=eh, json={"customer_name": "Should Fail"})
    check("employee cannot edit converted", r.status_code == 403, str(r.status_code))
    r = c.post(
        f"/api/leads/{lid}/status",
        headers=eh,
        json={"new_status_id": statuses["In Followup"], "reason": "reopen attempt"},
    )
    check("employee cannot reopen converted", r.status_code == 403, str(r.status_code))

    # Admin can still update
    r = c.put(f"/api/leads/{lid}", headers=ah, json={"city": "Chennai"})
    check("admin can update converted lead", r.status_code == 200, str(r.status_code))

    # Assign to inactive employee should fail (after we deactivate)
    # Create second employee briefly
    # Use existing manager as invalid assignment target for PRIMARY? Managers aren't in eligible list but assign() doesn't check.
    mgr_login = c.post("/api/auth/login", json={"email": ctx["mgr_email"], "password": "MgrPass1!"}).json()
    mgr_id = None
    # get manager id from employees list
    for e in c.get("/api/employees", headers=ah).json():
        if e["email"] == ctx["mgr_email"]:
            mgr_id = e["id"]
            break
    if mgr_id:
        # Pick another lead
        other = next((l for l in c.get("/api/leads", headers=ah, params={"size": 50}).json()["items"] if l["id"] != lid), None)
        if other:
            r = c.post(f"/api/leads/{other['id']}/assign", headers=ah, json={"employee_id": mgr_id, "role": "PRIMARY"})
            # Currently may succeed — document as bug if so
            check(
                "assign to MANAGER rejected (expect 400)",
                r.status_code == 400,
                f"got {r.status_code} — assign() does not validate EMPLOYEE role" if r.status_code == 200 else str(r.status_code),
            )

    # Inactive employee assign
    c.patch(f"/api/employees/{emp_id}", headers=ah, json={"is_active": False})
    other2 = next((l for l in c.get("/api/leads", headers=ah, params={"size": 50}).json()["items"] if l["id"] != lid), None)
    if other2:
        r = c.post(f"/api/leads/{other2['id']}/assign", headers=ah, json={"employee_id": emp_id, "role": "PRIMARY"})
        check(
            "assign to inactive employee rejected",
            r.status_code == 400,
            f"got {r.status_code}" if r.status_code != 400 else "400",
        )
    c.patch(f"/api/employees/{emp_id}", headers=ah, json={"is_active": True})

    # Contact endpoint on a fresh assigned lead if available
    # Dashboard numbers sanity
    dash = c.get("/api/dashboard", headers=ah).json()
    check("dashboard has total", isinstance(dash.get("total"), int) and dash["total"] >= 1, str(dash.get("total")))
    check("dashboard funnel present", isinstance(dash.get("funnel"), dict), str(dash.get("funnel")))

    # Manager write attempt on lead
    mh = {"Authorization": f"Bearer {mgr_login['access_token']}"}
    r = c.put(f"/api/leads/{lid}", headers=mh, json={"city": "ManagerHack"})
    check(
        "manager write blocked (expect 403)",
        r.status_code == 403,
        f"got {r.status_code} — managers may have write access contrary to business rules" if r.status_code == 200 else str(r.status_code),
    )

    # Employee report access — business rule: employee assigned-only, reports for manager
    r = c.get("/api/reports/employee-wise", headers=eh)
    check(
        "employee blocked from employee-wise report",
        r.status_code == 403,
        f"got {r.status_code}",
    )

    print("\n==== SUMMARY ====")
    fails = [x for x in results if x[0] == "FAIL"]
    print(f"Total: {len(results)}  PASS: {len(results) - len(fails)}  FAIL: {len(fails)}")
    for _, n, d in fails:
        print(f"  FAIL: {n} — {d}")


if __name__ == "__main__":
    main()
