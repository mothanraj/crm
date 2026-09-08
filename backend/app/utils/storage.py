"""Local-filesystem storage; S3-compatible backend can implement the same interface."""
import os
from abc import ABC, abstractmethod

from app.core.config import settings

ALLOWED = {"image/jpeg", "image/png", "application/pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "image/*"}


class StorageBackend(ABC):
    @abstractmethod
    def save(self, lead_id: str, filename: str, data: bytes) -> str: ...


class LocalStorage(StorageBackend):
    def __init__(self, root: str = settings.STORAGE_DIR):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def save(self, lead_id: str, filename: str, data: bytes) -> str:
        d = os.path.join(self.root, lead_id)
        os.makedirs(d, exist_ok=True)
        safe = filename.replace("..", "_")
        path = os.path.join(d, safe)
        with open(path, "wb") as f:
            f.write(data)
        return path


def get_storage() -> StorageBackend:
    return LocalStorage()
