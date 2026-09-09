# Lead Management CRM

Production-style CRM migrated from `MARKETING LEADS FUNNEL TRACKER (5) (1).xlsx`.
**PostgreSQL is the source of truth** — users, leads, and imports live in each developer’s own database, not in GitHub.

## Important: employees are local (Option A)

- Creating an employee in the Admin → **Employees** page writes to **your database only**.
- `git push` / `git pull` does **not** sync employees.
- After a fresh setup, each person logs in as **admin** and creates their own staff.

Seed creates **admin + masters only** (roles, statuses, sources, products). No Ajith/Kanchana/etc. accounts.

## Quickstart (Windows PowerShell)

### 1. Database

Create a local Postgres database and user (example):

```sql
CREATE USER crm WITH PASSWORD 'crm';
CREATE DATABASE crm OWNER crm;
```

### 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env if your Postgres URL / admin password differ
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000
```

Default admin (from `.env` / `.env.example`):

- Email: `admin@crm.local`
- Password: `Admin123!`

### 3. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 → sign in as admin → **Employees** → create staff (name, email, password, phone).

### 4. Leads

Use **Import** to load the Excel tracker. Only selected columns are imported. Duplicates/invalid rows can be reviewed, added as leads, or deleted by admin.

## Fresh machine / teammate pulled the repo

```powershell
cd backend
.\.venv\Scripts\Activate.ps1   # or create venv first
copy .env.example .env         # if you don't have .env yet
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000
```

Then create employees again in the UI. If you still see old demo names, they are leftover rows in **your** old database — delete them in Admin → Employees (deactivate) or wipe/recreate the `crm` database and re-run seed.

## Docs

See `docs/excel-analysis.md`, `docs/database-design.md`, `docs/business-rules.md`, `docs/api-documentation.md`.
