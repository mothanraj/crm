"""Background export job tests (filesystem job store)."""
import json
import os
import time
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.config import settings
from app.schemas import ExportRequest
from app.services import export_jobs


@pytest.fixture()
def job_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    return tmp_path / "exports"


@pytest.fixture()
def fake_render(monkeypatch):
    """Avoid a real DB: the worker only needs an owner and a payload."""
    db = Mock()
    db.get.return_value = object()  # export owner lookup
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: db)
    monkeypatch.setattr(
        "app.api.dashboard.build_report_payload",
        lambda _db, _u, _kind, _params: {"rows": [], "count": 0, "filters": {}},
    )


def test_job_lifecycle_creates_pdf(job_root, fake_render):
    job = export_jobs.create_job(str(uuid4()), "detailed", {"mode": "month", "month": "2026-11"})
    assert job["status"] == export_jobs.QUEUED
    assert job["filename"].startswith("detailed-lead-report-")
    assert export_jobs.get_job(job["id"])["status"] == export_jobs.QUEUED

    export_jobs.process_pending()

    status = export_jobs.get_job(job["id"])
    assert status["status"] == export_jobs.READY
    assert status["progress"] == 100
    path = export_jobs.result_path(job["id"])
    assert path.is_file()
    assert path.read_bytes()[:4] == b"%PDF"


def test_job_is_private_to_owner(job_root):
    owner = str(uuid4())
    job = export_jobs.create_job(owner, "detailed", {})
    assert export_jobs.get_job(job["id"], owner) is not None
    assert export_jobs.get_job(job["id"], str(uuid4())) is None
    assert export_jobs.get_job("not-a-uuid") is None


def test_failed_job_records_error(job_root, monkeypatch):
    job = export_jobs.create_job(str(uuid4()), "detailed", {})

    def boom(meta, db, progress):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(export_jobs, "_render", boom)
    export_jobs.process_pending()

    status = export_jobs.get_job(job["id"])
    assert status["status"] == export_jobs.FAILED
    assert "render exploded" in status["error"]


def test_cleanup_removes_expired_files(job_root, monkeypatch):
    job = export_jobs.create_job(str(uuid4()), "detailed", {})
    meta = job_root / f"{job['id']}.json"
    old = time.time() - 25 * 3600
    os.utime(meta, (old, old))
    export_jobs.cleanup_old()
    assert not meta.exists()
    assert export_jobs.get_job(job["id"]) is None


@pytest.mark.parametrize("kind, prefix", [
    ("source", "lead-source-report"),
    ("product", "product-wise-report"),
    ("category", "category-wise-report"),
    ("lead_value", "lead-value-report"),
    ("quotation", "quotation-report"),
    ("monthly", "monthly-lead-volume"),
    ("detailed", "detailed-lead-report"),
    ("dashboard_history", "dashboard-history-report"),
])
def test_all_report_types_can_be_queued(job_root, kind, prefix):
    assert ExportRequest(report_type=kind).report_type == kind
    job = export_jobs.create_job(str(uuid4()), kind, {})
    assert job["report_type"] == kind
    assert job["filename"].startswith(prefix + "-")
