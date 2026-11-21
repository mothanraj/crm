"""Background export job tests (filesystem job store)."""
import json
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import export_jobs


@pytest.fixture()
def job_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    return tmp_path / "exports"


def test_job_lifecycle_creates_pdf(job_root):
    job = export_jobs.create_job("user-1", "detailed", {"mode": "month", "month": "2026-11"})
    assert job["status"] == export_jobs.QUEUED
    assert export_jobs.get_job(job["id"])["status"] == export_jobs.QUEUED

    export_jobs.process_pending()

    status = export_jobs.get_job(job["id"])
    assert status["status"] == export_jobs.READY
    assert status["progress"] == 100
    path = export_jobs.result_path(job["id"])
    assert path.is_file()
    assert path.read_bytes()[:4] == b"%PDF"


def test_job_is_private_to_owner(job_root):
    job = export_jobs.create_job("user-1", "detailed", {})
    assert export_jobs.get_job(job["id"], "user-1") is not None
    assert export_jobs.get_job(job["id"], "someone-else") is None
    assert export_jobs.get_job("not-a-uuid") is None


def test_failed_job_records_error(job_root, monkeypatch):
    job = export_jobs.create_job("user-1", "detailed", {})

    def boom(meta, db, progress):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(export_jobs, "_render", boom)
    export_jobs.process_pending()

    status = export_jobs.get_job(job["id"])
    assert status["status"] == export_jobs.FAILED
    assert "render exploded" in status["error"]


def test_cleanup_removes_expired_files(job_root, monkeypatch):
    import time

    job = export_jobs.create_job("user-1", "detailed", {})
    meta = job_root / f"{job['id']}.json"
    old = time.time() - 25 * 3600
    import os

    os.utime(meta, (old, old))
    export_jobs.cleanup_old()
    assert not meta.exists()
    assert export_jobs.get_job(job["id"]) is None
