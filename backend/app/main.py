from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin_maintenance, auth, dashboard, employees, importer, leads, sheets_sync, stream
from app.core.config import settings
from app.workers.scheduler import start, stop

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    start()
    yield
    stop()


app = FastAPI(title="Lead CRM", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(importer.router)
app.include_router(dashboard.router)
app.include_router(employees.router)
app.include_router(admin_maintenance.router)
app.include_router(sheets_sync.router)
app.include_router(stream.router)


@app.get("/health")
def health():
    return {"ok": True}
