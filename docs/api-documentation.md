# API Documentation (v1, `/api`)

Auth: Bearer JWT (`POST /api/auth/login` → access+refresh). All except login require auth; admin routes require ADMIN.

- `POST /api/auth/login` `{email,password}` → tokens + user
- `GET /api/leads?search=&status=&source=&product=&employee=&sla=&from=&to=&page=&size=&sort=` → paged leads
- `POST /api/leads` (intake incl. auto-assign) · `GET /api/leads/{id}` · `PUT /api/leads/{id}` · `DELETE /api/leads/{id}` (soft)
- `POST /api/leads/{id}/assign` `{employee_id, role}` · `POST /api/leads/{id}/reassign` (admin)
- `POST /api/leads/{id}/contact` (first contact) · `POST /api/leads/{id}/status` `{new_status_id, reason}`
- `GET/POST /api/leads/{id}/activities` · `GET/POST /api/leads/{id}/followups` (activity w/ next date)
- `POST /api/leads/{id}/site-visits` · `GET /api/leads/{id}/site-visits`
- `POST /api/leads/{id}/quotations` · `GET /api/leads/{id}/quotations`
- `POST /api/leads/{id}/documents` (multipart) · `GET /api/leads/{id}/documents`
- `GET /api/leads/{id}/history` (status history + assignments)
- `POST /api/import/excel` (multipart) → `{batch_id, preview}` · `POST /api/import/{id}/confirm` → summary `{total, imported, duplicates, invalid, skipped, errors}`
- `GET /api/dashboard` (KPIs incl. `new_lead_display`, overdue, due-today, visits, quotes, conversion) · `GET /api/dashboard/by-source` · `GET /api/dashboard/monthly`
- `GET /api/reports/product-wise|source-wise|employee-wise|monthly` (same filters as leads)
- `GET /api/employees|/products|/lead-sources|/statuses` + CRUD (admin)
- `GET /api/notifications` · `POST /api/notifications/{id}/read`
