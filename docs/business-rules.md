# Business Rules

1. **Source of truth**: PostgreSQL after migration. No Excel formulas in production.
2. **Enquiry numbers**: preserve `legacy_enquiry_no`; new leads get `ENQ-%06d` from `enquiry_sequence` (transaction-safe). Unique constraint.
3. **Assignment**: round-robin over `is_active` employees + workload cap (`OPEN_LEAD_LIMIT`, default 3 open leads needing first contact). Pointer in `assignment_state`. Skip inactive. Leads beyond capacity stay unassigned until capacity frees. Every assign/reassign → `lead_assignments` row + notification. Admin manual reassign allowed (active EMPLOYEE only).
4. **SLA**: `sla_deadline = assigned_at + 72h` per primary assignment. First contact (date/method/result/notes/by) → COMPLETED if ≤ deadline else OVERDUE (late contact still recorded). APScheduler every 15 min marks overdue + emits admin + employee `SLA_OVERDUE` notifications. Also computed lazily on read.
5. **Status**: append-only `lead_status_history`. Merged `Not Interested` (covers `/Spam`). Terminal: Converted, Duplicate, Not Interested. Reopening allowed with reason.
6. **New-Lead display cap**: dashboard shows `min(count,5)` + `5+` badge + `⚠ threshold` banner; click-through lists all. Never delete/hide.
7. **Dedup**: exact `legacy_enquiry_no` → duplicate; else normalized phone exact → duplicate/review; else fuzzy name+company → review queue. Admin confirms before import.
8. **RBAC**: ADMIN full; EMPLOYEE assigned-leads-only (CRUD activities/visits/quotes/docs, status updates); MANAGER read-only + reports. Org-wide `/api/reports/*` requires ADMIN or MANAGER.
9. **Files**: MIME whitelist (jpg/png/pdf/xlsx/dwg…), ≤15 MB, stored under `storage/<lead_id>/`, metadata in `lead_documents`. S3-compatible backend later via `StorageBackend` interface.
10. **Lead intake seam**: `LeadIntakeService.create_lead(source_key, payload)` — Excel/Meta/Expo now; Facebook/WhatsApp/IndiaMART later. No fake integrations.
11. **Reports**: all `GROUP BY` FKs; conversion % = converted/total; monthly via `date_trunc('month', enquiry_date)`.
