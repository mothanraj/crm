# Lead Management CRM

Production-style CRM migrated from `MARKETING LEADS FUNNEL TRACKER (5) (1).xlsx`.
PostgreSQL is the source of truth after migration.

## Quickstart

```powershell
# backend
cd backend
python -m venv .venv; .\.venv\Scripts\Activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload

# frontend
cd frontend
npm install
npm run dev
```

See `docs/excel-analysis.md`, `docs/database-design.md`, `docs/business-rules.md`, `docs/api-documentation.md`.
