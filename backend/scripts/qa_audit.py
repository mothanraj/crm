"""Live API audit script — run against a local uvicorn on :8000."""
from __future__ import annotations

import json
import uuid
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
    c = httpx.Client(base_url=BASE, timeout=30.0)

    r = c.get("/health")
    check("health", r.status_code == 200 and r.json().get("ok") is True, str(r.status_code))

    r = c.post("/api/auth/login", json={"email": "admin@crm.local", "password": "wrong"})
    check("login invalid password -> 401", r.status_code == 401, str(r.status_code))

    r = c.post("/api/auth/login", json={"email": "nobody@crm.local", "password": "Admin123!"})
    check("login unknown user -> 401", r.status_code == 401, str(r.status_code))

    r = c.post("/api/auth/login", json={"email": "", "password": ""})
    check("login empty -> 401/422", r.status_code in (401, 422), str(r.status_code))

    r = c.post("/api/auth/login", json={"email": "admin@crm.local", "password": "Admin123!"})
    check("login admin", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    admin = r.json() if r.status_code == 200 else {}
    admin_tok = admin.get("access_token", "")
    admin_rt = admin.get("refresh_token", "")
    ah = {"Authorization": f"Bearer {admin_tok}"}

    r = c.get("/api/leads")
    check("leads without token -> 401/403", r.status_code in (401, 403), str(r.status_code))

    r = c.get("/api/leads", headers={"Authorization": "Bearer not.a.token"})
    check("leads bad token -> 401", r.status_code == 401, str(r.status_code))

    r = c.post("/api/auth/refresh", json={"refresh_token": admin_rt})
    check("refresh works", r.status_code == 200 and "access_token" in r.json(), str(r.status_code))
    if r.status_code == 200:
        admin_tok = r.json()["access_token"]
        admin_rt = r.json().get("refresh_token", admin_rt)
        ah = {"Authorization": f"Bearer {admin_tok}"}

    r = c.post("/api/auth/refresh", json={"refresh_token": admin_tok})
    check("access token as refresh rejected", r.status_code == 401, str(r.status_code))

    r = c.get("/api/dashboard", headers=ah)
    check("admin dashboard", r.status_code == 200, str(r.status_code))

    r = c.get("/api/masters", headers=ah)
    check("masters", r.status_code == 200, str(r.status_code))
    masters = r.json() if r.status_code == 200 else {}
    statuses = {s["name"]: s["id"] for s in masters.get("statuses", [])}
    print("  statuses:", list(statuses.keys()))

    r = c.get("/api/employees", headers=ah)
    check("list employees", r.status_code == 200, str(r.status_code))
    emps = r.json() if r.status_code == 200 else []
    print(f"  employees count: {len(emps)}")

    suffix = uuid.uuid4().hex[:8]
    emp_email = f"qa.emp.{suffix}@crm.local"
    digits = "".join(ch for ch in suffix if ch.isdigit()) + "00000000"
    phone = ("98" + digits)[:10]
    if phone[0] not in "6789":
        phone = "9" + phone[1:]

    r = c.post(
        "/api/employees",
        headers=ah,
        json={
            "name": f"QA Emp {suffix}",
            "email": emp_email,
            "password": "EmpPass1!",
            "phone": phone,
            "role": "EMPLOYEE",
        },
    )
    check("create employee", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    emp = r.json() if r.status_code == 200 else {}
    emp_id = emp.get("id")

    r = c.post(
        "/api/employees",
        headers=ah,
        json={
            "name": "Dup",
            "email": emp_email,
            "password": "EmpPass1!",
            "phone": "9123456780",
            "role": "EMPLOYEE",
        },
    )
    check("duplicate email rejected", r.status_code == 400, str(r.status_code))

    r = c.post(
        "/api/employees",
        headers=ah,
        json={
            "name": "BadPhone",
            "email": f"badphone.{suffix}@crm.local",
            "password": "EmpPass1!",
            "phone": "12345",
            "role": "EMPLOYEE",
        },
    )
    check("invalid phone rejected", r.status_code == 400, str(r.status_code))

    r = c.post(
        "/api/employees",
        headers=ah,
        json={
            "name": "BadEmail",
            "email": "not-an-email",
            "password": "EmpPass1!",
            "phone": "9123456781",
            "role": "EMPLOYEE",
        },
    )
    check("invalid email rejected", r.status_code == 400, str(r.status_code))

    r = c.post("/api/auth/login", json={"email": emp_email, "password": "EmpPass1!"})
    check("employee login", r.status_code == 200, str(r.status_code))
    emp_tok = r.json().get("access_token", "") if r.status_code == 200 else ""
    eh = {"Authorization": f"Bearer {emp_tok}"}

    r = c.get("/api/employees", headers=eh)
    check("employee blocked from /employees", r.status_code == 403, str(r.status_code))

    r = c.get("/api/import/batches", headers=eh)
    check("employee blocked from import batches", r.status_code == 403, str(r.status_code))

    r = c.post("/api/leads", headers=ah, json={"customer_name": "X", "contact_number": "9999999999"})
    check("POST /leads blocked", r.status_code == 403, str(r.status_code))

    r = c.get("/api/leads", headers=ah)
    check("admin list leads", r.status_code == 200, str(r.status_code))
    leads_payload = r.json() if r.status_code == 200 else {}
    print(f"  total leads: {leads_payload.get('total')}")

    r = c.get("/api/notifications", headers=ah)
    check("notifications list", r.status_code == 200 and isinstance(r.json(), list), str(r.status_code))
    notifs = r.json() if r.status_code == 200 else []

    nid = notifs[0]["id"] if notifs else "00000000-0000-0000-0000-000000000001"
    r = c.post(f"/api/notifications/{nid}/read", headers=ah)
    detail = ""
    try:
        detail = r.json().get("detail") if isinstance(r.json(), dict) else str(r.json())
    except Exception:
        detail = r.text[:120]
    if r.status_code == 200:
        check("mark-read endpoint implemented", True, "200")
    elif r.status_code == 404 and detail == "Not Found":
        check("mark-read endpoint implemented", False, "route missing (FastAPI Not Found)")
    elif r.status_code == 404:
        check("mark-read endpoint implemented", True, "route exists, notification missing")
    else:
        check("mark-read endpoint implemented", False, f"status={r.status_code} detail={detail}")

    r = c.get("/api/stream/leads", timeout=5.0)
    check("SSE without token -> 401/422", r.status_code in (401, 422), str(r.status_code))

    # Only peek at status line — do not wait for the infinite SSE body.
    try:
        with c.stream("GET", "/api/stream/leads", params={"token": admin_tok}, timeout=3.0) as sr:
            check("SSE with token starts", sr.status_code == 200, str(sr.status_code))
            next(sr.iter_bytes(), None)
    except Exception as exc:
        check("SSE with token starts", False, str(exc)[:120])

    fake = str(uuid.uuid4())
    if leads_payload.get("items"):
        lid = leads_payload["items"][0]["id"]
        r = c.post(f"/api/leads/{lid}/assign", headers=ah, json={"employee_id": fake, "role": "PRIMARY"})
        check("assign nonexistent employee -> 404", r.status_code == 404, str(r.status_code))

        r = c.post(f"/api/leads/{lid}/assign", headers=eh, json={"employee_id": emp_id, "role": "PRIMARY"})
        check("employee cannot assign", r.status_code == 403, str(r.status_code))

        other = next((it for it in leads_payload["items"] if it.get("primary_employee_id") != emp_id), None)
        if other:
            r = c.get(f"/api/leads/{other['id']}", headers=eh)
            check("employee IDOR blocked on get", r.status_code == 403, f"{r.status_code}")
            r = c.put(f"/api/leads/{other['id']}", headers=eh, json={"customer_name": "Hacked"})
            check("employee IDOR blocked on put", r.status_code == 403, str(r.status_code))
    else:
        check("leads exist for assign/IDOR tests", False, "no leads in DB")

    r = c.get("/api/leads", headers=ah, params={"search": "zzzznonexistentzzz"})
    check("search empty results", r.status_code == 200 and r.json().get("total") == 0, str(r.json().get("total")))

    r = c.get("/api/leads", headers=ah, params={"sla": "INVALID"})
    check("invalid sla filter -> 400", r.status_code == 400, str(r.status_code))

    r = c.get("/api/leads", headers=ah, params={"status": "not-a-uuid"})
    check("invalid status uuid -> 400", r.status_code == 400, str(r.status_code))

    r = c.get("/api/leads", headers=ah, params={"page": 1, "size": 5})
    check("pagination size=5", r.status_code == 200 and len(r.json().get("items", [])) <= 5, str(len(r.json().get("items", []))))

    r = c.get("/api/reports/monthly", headers=ah)
    check("reports monthly", r.status_code == 200, str(r.status_code))

    r = c.get("/api/reports/monthly", headers=eh)
    check("employee reports access noted", r.status_code in (200, 403), f"got {r.status_code}")

    mgr_email = f"qa.mgr.{suffix}@crm.local"
    mgr_phone = ("97" + phone[2:])[:10]
    r = c.post(
        "/api/employees",
        headers=ah,
        json={
            "name": f"QA Mgr {suffix}",
            "email": mgr_email,
            "password": "MgrPass1!",
            "phone": mgr_phone,
            "role": "MANAGER",
        },
    )
    check("create manager", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    r = c.post("/api/auth/login", json={"email": mgr_email, "password": "MgrPass1!"})
    mgr_tok = r.json().get("access_token", "") if r.status_code == 200 else ""
    mh = {"Authorization": f"Bearer {mgr_tok}"}
    r = c.get("/api/employees", headers=mh)
    check("manager blocked from employees admin", r.status_code == 403, str(r.status_code))
    r = c.get("/api/dashboard", headers=mh)
    check("manager dashboard", r.status_code == 200, str(r.status_code))

    if emp_id:
        r = c.patch(f"/api/employees/{emp_id}", headers=ah, json={"is_active": False})
        check("deactivate employee", r.status_code == 200, str(r.status_code))
        r = c.post("/api/auth/login", json={"email": emp_email, "password": "EmpPass1!"})
        check("deactivated employee cannot login", r.status_code == 401, str(r.status_code))
        c.patch(f"/api/employees/{emp_id}", headers=ah, json={"is_active": True})

    print("\n==== SUMMARY ====")
    fails = [x for x in results if x[0] == "FAIL"]
    print(f"Total: {len(results)}  PASS: {len(results) - len(fails)}  FAIL: {len(fails)}")
    for _, n, d in fails:
        print(f"  FAIL: {n} — {d}")

    CTX.write_text(
        json.dumps(
            {
                "admin_email": "admin@crm.local",
                "emp_email": emp_email,
                "emp_id": emp_id,
                "emp_pass": "EmpPass1!",
                "mgr_email": mgr_email,
                "suffix": suffix,
                "phone": phone,
                "statuses": statuses,
            },
            indent=2,
        )
    )
    print(f"saved {CTX}")


if __name__ == "__main__":
    main()
