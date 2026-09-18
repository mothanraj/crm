# API Documentation (v1, `/api`)

Auth: Bearer JWT (`POST /api/auth/login` → access+refresh). All except login/health require auth; admin routes require ADMIN. Org-wide reports require ADMIN or MANAGER. Managers are read-only on leads.

- `POST /api/auth/login` `{email,password}` → tokens + user
- `POST /api/auth/refresh` `{refresh_token}` → rotated access+refresh
- `GET /api/leads?search=&status=&source=&product=&employee=&sla=&unassigned=&customer_review=&page=&size=` → paged leads (employees see assigned only)
- `POST /api/leads` → **403** (intake is Excel/Sheets import only)
- `GET /api/leads/{id}` · `PUT /api/leads/{id}` · (no soft-delete endpoint)
- `POST /api/leads/{id}/assign` `{employee_id, role}` (admin; active EMPLOYEE only)
- `POST /api/leads/{id}/contact` (first contact) · `POST /api/leads/{id}/status` `{new_status_id, reason, customer_review?, quotation_value?, sla_state?, method?}`
- `POST /api/leads/{id}/activities` · `POST /api/leads/{id}/site-visits` · `POST /api/leads/{id}/quotations` · `POST /api/leads/{id}/documents`
- `POST /api/import/excel` (multipart) → preview · `POST /api/import/{id}/confirm` → summary
- `GET /api/dashboard` · `GET /api/dashboard/by-source` · `GET /api/dashboard/by-product`
- `GET /api/reports/*` (ADMIN/MANAGER) · product/source/employee/monthly/customer-review + exports + PDF
- `GET /api/employees` + CRUD (admin) · `GET /api/masters`
- `GET /api/notifications` · `POST /api/notifications/read-all` · `POST /api/notifications/{id}/read`
- `GET /api/stream/leads?token=` (SSE)
