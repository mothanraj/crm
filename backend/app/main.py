from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, dashboard, employees, importer, leads
from app.core.config import settings
from app.workers.scheduler import start

app = FastAPI(title="Lead CRM")
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS.split(","),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(importer.router)
app.include_router(dashboard.router)
app.include_router(employees.router)


@app.on_event("startup")
def _startup():
    start()


@app.get("/health")
def health():
    return {"ok": True}
