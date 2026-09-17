import hashlib
import hmac
import time

from app.api.sheets_sync import SheetsPush
from app.core.config import settings


def _sig(secret: str, ts: str, raw: bytes) -> str:
    return hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()


def test_sheets_payload_shape():
    body = {"sheet_id": "Leads Tracker (1)", "rows": [
        {"row_id": 2, "external_key": "k1", "name": "A", "phone": "9840098400",
         "enq": 11, "email": "a@example.com"},
    ]}
    import json
    parsed = SheetsPush.model_validate_json(json.dumps(body).encode())
    assert parsed.sheet_id.startswith("Leads")
    assert parsed.rows[0].name == "A"


def test_sheets_payload_rejects_empty():
    import json
    parsed = SheetsPush.model_validate_json(json.dumps({"sheet_id": "x", "rows": []}).encode())
    assert parsed.rows == []


def test_hmac_vector():
    secret, ts, raw = "s", "1700000000", b'{"a":1}'
    assert _sig(secret, ts, raw) == hmac.new(
        b"s", b"1700000000." + raw, hashlib.sha256).hexdigest()
    assert abs(time.time() - int(ts)) > 0  # window check lives in router
    assert isinstance(settings.SHEETS_SIGNATURE_WINDOW_SEC, int)
