"""Local-filesystem storage; S3-compatible backend can implement the same interface."""
import os
import re
import uuid
from abc import ABC, abstractmethod

from app.core.config import settings

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".pdf", ".xlsx"}


class StorageBackend(ABC):
    @abstractmethod
    def save(self, lead_id: str, filename: str, data: bytes) -> str: ...


class LocalStorage(StorageBackend):
    def __init__(self, root: str = settings.STORAGE_DIR):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def save(self, lead_id: str, filename: str, data: bytes) -> str:
        # Lead id comes from a UUID path param, but never trust path parts.
        safe_lead = re.sub(r"[^A-Za-z0-9\-]", "_", str(lead_id or "unknown"))
        d = os.path.join(self.root, safe_lead)
        os.makedirs(d, exist_ok=True)
        base = os.path.basename(filename or "unnamed")
        base = re.sub(r"[^A-Za-z0-9_.\-]", "_", base)
        stem, dot, ext = base.rpartition(".")
        ext = f".{ext.lower()}" if dot and stem else ""
        if ext not in ALLOWED_EXTS:
            raise ValueError(f"File type not allowed. Use: {', '.join(sorted(ALLOWED_EXTS))}")
        # UUID prefix prevents overwrites and collision guessing.
        path = os.path.join(d, f"{uuid.uuid4().hex}{ext}")
        with open(path, "wb") as f:
            f.write(data)
        return path


def get_storage() -> StorageBackend:
    return LocalStorage()
