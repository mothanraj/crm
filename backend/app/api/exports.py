"""Background report export jobs (large PDFs)."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dashboard import _require_reports
from app.core.deps import current_user
from app.db.session import get_db
from app.models import User
from app.schemas import ExportRequest
from app.services import export_jobs

router = APIRouter(prefix="/api", tags=["exports"])


@router.post("/reports/exports")
def create_export(
    body: ExportRequest,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Queue a PDF export and return a job id to poll for progress."""
    _require_reports(u)
    job = export_jobs.create_job(u.id, body.report_type, body.params)
    return {"job": job, "poll_url": f"/api/reports/exports/{job['id']}"}


@router.get("/reports/exports/{job_id}")
def export_status(
    job_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_reports(u)
    job = export_jobs.get_job(job_id, u.id)
    if job is None:
        raise HTTPException(404, "Export job not found")
    return job


@router.get("/reports/exports/{job_id}/download")
def export_download(
    job_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_reports(u)
    job = export_jobs.get_job(job_id, u.id)
    if job is None:
        raise HTTPException(404, "Export job not found")
    if job.get("status") != export_jobs.READY:
        raise HTTPException(409, f"Export is {job.get('status')}, not ready")
    path = export_jobs.result_path(job_id)
    if not path.is_file():
        raise HTTPException(410, "Export file has expired — please create it again")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=job.get("filename") or "export.pdf",
    )
