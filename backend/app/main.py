import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import admin_maintenance, analytics, auth, dashboard, employees, importer, leads, sheets_sync, stream
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
app.include_router(analytics.router)
app.include_router(employees.router)
app.include_router(admin_maintenance.router)
app.include_router(sheets_sync.router)
app.include_router(stream.router)


@app.get("/health")
def health():
    return {"ok": True}


def _frontend_dist() -> Path | None:
    """Built React app. Set FRONTEND_DIST in production; locally use frontend/dist after npm run build."""
    candidates = []
    configured = os.environ.get("FRONTEND_DIST", "").strip()
    if configured:
        candidates.append(Path(configured))
    candidates.append(Path(__file__).resolve().parents[2] / "frontend" / "dist")
    for folder in candidates:
        if (folder / "index.html").is_file():
            return folder.resolve()
    return None


_DIST = _frontend_dist()
if _DIST is not None:
    @app.get("/", include_in_schema=False)
    def spa_index():
        return FileResponse(_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        root = _DIST
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(root / "index.html")
