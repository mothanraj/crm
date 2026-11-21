"""Filesystem-backed background PDF export jobs.

Large report exports (e.g. the Detailed Lead Report with thousands of rows)
cannot be generated inside the HTTP request: the browser times out and the
server holds the whole PDF in memory. Jobs are queued as small JSON metadata
files under ``STORAGE_DIR/exports`` and processed by a single APScheduler job
(see app.workers.scheduler). The finished PDF is served from the same folder.

The job store is intentionally a flat set of files: the app runs as one process
(one uvicorn + one in-process scheduler) behind a single container, so no extra
DB table/migration is needed. All metadata and filenames are UUID-derived, and
worker file-renames provide atomic claiming across threads.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from app.core.config import settings

log = logging.getLogger(__name__)

QUEUED = "queued"
PROCESSING = "processing"
READY = "ready"
FAILED = "failed"
_PUBLIC_FIELDS = (
    "id", "report_type", "status", "progress", "error", "filename", "created_at",
)


def _root() -> Path:
    """Resolve the export folder relative to the process CWD (STORAGE_DIR)."""
    root = Path(settings.STORAGE_DIR) / "exports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _valid_id(job_id: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{32}", str(job_id or "")))


def _meta_path(job_id: str) -> Path:
    return _root() / f"{job_id}.json"


def _processing_path(job_id: str) -> Path:
    return _root() / f"{job_id}.processing.json"


def result_path(job_id: str) -> Path:
    return _root() / f"{job_id}.pdf"


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def _public(meta: dict) -> dict:
    return {key: meta.get(key) for key in _PUBLIC_FIELDS}


def create_job(user_id, report_type: str, params: dict | None = None) -> dict:
    job_id = uuid.uuid4().hex
    meta = {
        "id": job_id,
        "user_id": str(user_id),
        "report_type": report_type,
        "params": {str(k): str(v or "") for k, v in (params or {}).items()},
        "status": QUEUED,
        "progress": 10,
        "error": "",
        "filename": f"detailed-lead-report-{job_id[:8]}.pdf",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(_meta_path(job_id), meta)
    return _public(meta)


def get_job(job_id: str, user_id=None) -> dict | None:
    if not _valid_id(job_id):
        return None
    path = _meta_path(job_id)
    if not path.exists():
        path = _processing_path(job_id)
    if not path.exists():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if user_id is not None and str(meta.get("user_id")) != str(user_id):
        return None
    return _public(meta)


def _claim_next() -> dict | None:
    """Atomically claim one queued job by renaming its metadata file."""
    for path in sorted(_root().glob("*.json")):
        if path.name.endswith(".processing.json") or path.suffix == ".tmp":
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("status") != QUEUED:
            continue
        job_id = str(meta.get("id") or "")
        if not _valid_id(job_id):
            continue
        target = _processing_path(job_id)
        try:
            os.rename(path, target)
        except OSError:
            continue  # another worker claimed it first
        meta["status"] = PROCESSING
        meta["progress"] = 20
        _atomic_write_json(target, meta)
        return meta
    return None


def _set_progress(job_id: str, **fields) -> None:
    path = _processing_path(job_id)
    if not path.exists():
        path = _meta_path(job_id)
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    meta.update(fields)
    _atomic_write_json(_meta_path(job_id), meta)
    if path != _meta_path(job_id) and path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def _render(meta: dict, db, progress: Callable[[int], None]) -> bytes:
    """Build the PDF for a job using the same code path as the live report."""
    from app.api.dashboard import (
        _detailed_lead_filters,
        _detailed_leads_payload,
        _resolve_detailed_range,
    )
    from app.services.report_pdf import build_report_pdf

    params = meta.get("params") or {}
    start, end, resolved = _resolve_detailed_range(
        params.get("mode"), params.get("month"), params.get("week"),
        params.get("from_date"), params.get("to_date"),
        params.get("from_month"), params.get("to_month"), params.get("year"),
    )
    lead_filters = _detailed_lead_filters(
        search=params.get("search", ""),
        status=params.get("status", ""),
        source=params.get("source", ""),
        customer_review=params.get("customer_review", ""),
        sla=params.get("sla", ""),
        starred=params.get("starred", ""),
        sort=params.get("sort", ""),
    )
    progress(40)
    payload = _detailed_leads_payload(
        db, start, end, params.get("from_month"), params.get("to_month"),
        resolved, lead_filters,
    )
    progress(70)
    content = build_report_pdf(payload, "detailed")
    progress(95)
    return content


def process_pending() -> None:
    """Generate at most one queued job per tick (called by the scheduler)."""
    cleanup_old()
    meta = _claim_next()
    if not meta:
        return
    job_id = str(meta["id"])
    db = None
    try:
        from app.db.session import SessionLocal

        db = SessionLocal()
        content = _render(meta, db, lambda pct: _set_progress(job_id, progress=pct))
        target = result_path(job_id)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(content)
        os.replace(tmp, target)
        _set_progress(job_id, status=READY, progress=100, error="")
        log.info("export job %s ready (%d bytes)", job_id, len(content))
    except Exception as exc:  # noqa: BLE001 - job must not kill the scheduler
        log.exception("export job %s failed", job_id)
        _set_progress(job_id, status=FAILED, error=str(exc)[:500])
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def cleanup_old() -> None:
    """Drop jobs and files older than EXPORT_JOB_TTL_HOURS."""
    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=max(1, int(settings.EXPORT_JOB_TTL_HOURS))
    )
    for path in _root().iterdir():
        if path.suffix not in (".json", ".pdf") or not path.is_file():
            continue
        try:
            if datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) >= cutoff:
                continue
            path.unlink()
        except OSError:
            pass
