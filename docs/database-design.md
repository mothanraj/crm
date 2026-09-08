# Database Design (PostgreSQL, UUIDv4 PKs)

## Conventions
- PK: `UUID DEFAULT gen_random_uuid()`, FKs indexed. `enquiry_number TEXT UNIQUE NOT NULL` (`ENQ-000001`…).
- `created_at TIMESTAMPTZ DEFAULT now()`, `updated_at` auto-touched. Soft delete: `is_active BOOL DEFAULT true`, `deleted_at NULL` on masters + leads.
- Enums as lookup tables (sources, products, statuses), never free text.

## Tables

### roles (seed: ADMIN, EMPLOYEE, MANAGER)
`id, name UNIQUE, description`

### users (= employees)
`id, name, email UNIQUE, password_hash, phone, department, role_id→roles, is_active, created_at, updated_at`
Seed: 8 Excel employees (auto `firstname@crm.local`, temp password, must reset) + admin from env. Merge `Ram kumar→Ram`.

### lead_sources (seed 11)
`id, name UNIQUE, is_active, sort_order` — Facebook/Instagram, Google Ads, India Mart, Direct Call, Referral, WhatsApp, Email Campaign, Email Enquiry, SEO, Others, Expo/Stall.

### products (seed 6) + product_aliases
`products: id, name UNIQUE, description, is_active`
`product_aliases: id, product_id→products, alias UNIQUE` (32 raw variants incl. snake_case, junk-flagged).

### lead_statuses (seed 11)
`id, name UNIQUE, is_terminal, is_lost, sort_order` — New Lead, In Followup, A - Prospect, A+ - Immediate, RNR / Not reachable, Not Interested (merged /Spam), Converted, Duplicate, Investor, Channel Partner, Approval Client.

### leads
`id, enquiry_number UNIQUE, legacy_enquiry_no INT NULL, enquiry_date DATE, customer_name, contact_number, contact_number_norm (digits, indexed), alternate_contact, email, company_name, location, city, source_id→lead_sources, product_id→products NULL, requirement TEXT, quantity_raw TEXT, quantity_num NUMERIC NULL, priority TEXT NULL (A/B/A Plus), status_id→lead_statuses, primary_employee_id→users NULL, technical_employee_id→users NULL, secondary_support_employee_id→users NULL, first_contact_at NULL, first_contact_method NULL, first_contact_result NULL, first_contact_by→users NULL, first_contact_notes TEXT, sla_deadline NULL, sla_state (PENDING/COMPLETED/OVERDUE), next_followup_at NULL, lost_reason TEXT, is_active, created_by→users, created_at, updated_at`
Indexes: `(status_id), (source_id), (product_id), (primary_employee_id), (enquiry_date), (contact_number_norm), (sla_state, sla_deadline), (next_followup_at)`.

### lead_assignments (append-only)
`id, lead_id→leads, employee_id→users, role (PRIMARY/TECHNICAL/SECONDARY), assigned_by→users, assigned_at, sla_deadline, is_current`
Index `(lead_id, assigned_at DESC), (employee_id, is_current)`. Round-robin pointer in `assignment_state (id, last_employee_id, updated_at)` single-row table.

### lead_status_history (append-only)
`id, lead_id, old_status_id NULL, new_status_id, changed_by→users, changed_at, reason`
Index `(lead_id, changed_at)`.

### lead_activities (follow-ups + timeline)
`id, lead_id, employee_id→users, activity_type (Call/WhatsApp/Email/Site Visit/Quotation/Meeting/Note/Other), activity_at, notes, outcome, next_followup_at NULL, created_at`
Index `(lead_id, activity_at DESC)`. Migration seeds J/K/L/M/AE tracker notes as `Note` rows.

### site_visits
`id, lead_id, visit_date, employee_id→users, site_location, visit_status (Scheduled/Completed/Cancelled), customer_feedback, notes`

### quotations
`id, lead_id, quotation_number UNIQUE (EEPLCP…), quotation_date, revision TEXT DEFAULT R0, units NUMERIC, amount_excl NUMERIC, gst NUMERIC, grand_total NUMERIC, status (Draft/Sent/Approved/Rejected), sent_date NULL, notes`
Index `(lead_id), (quotation_number)`.

### lead_documents (metadata only; bytes in `storage/`)
`id, lead_id, file_name, stored_path, content_type, size_bytes, document_type (Site Photo/Customer Doc/Quotation/Drawing/Requirement/Other), uploaded_by→users, uploaded_at`
Check: size ≤ 15 MB, MIME whitelist.

### notifications
`id, user_id→users (NULL = broadcast admin), lead_id NULL, kind (SLA_OVERDUE/ASSIGNMENT/FOLLOWUP_DUE/INFO), title, body, is_read, created_at`
Index `(user_id, is_read, created_at DESC)`.

### import_batches + import_errors
`import_batches: id, file_name, sheet_name, total_rows, imported, duplicates, invalid, skipped, status, created_by, created_at`
`import_errors: id, batch_id, row_number, raw JSONB, error TEXT, reason (DUPLICATE/INVALID/SKIPPED)`

### enquiry_sequence
Single-row `last_number INT` (or PG sequence) backing `ENQ-%06d` allocator with `SELECT … FOR UPDATE`.

## Relationships
- leads N:1 sources/products/statuses/users(×3). 1:N assignments/history/activities/visits/quotations/documents.
- Never store employee/source/product/status names on leads — FKs only.
- Dashboard/reports = `GROUP BY` on FKs + date_trunc; `Others` computed explicitly, never residual.
