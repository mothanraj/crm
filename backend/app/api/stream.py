"""Server-sent events for live website sync (JWT via ?token=, EventSource can't set headers)."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models import User
from app.services import live

router = APIRouter(prefix="/api/stream", tags=["stream"])


def _auth(token: str) -> bool:
    try:
        uid = decode_token(token, "access")
    except Exception:
        return False
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        return bool(u and u.is_active)
    finally:
        db.close()


@router.get("/leads")
async def stream_leads(token: str = Query("")):
    if not _auth(token):
        from fastapi import HTTPException
        raise HTTPException(401, "Invalid token")

    async def gen():
        last = live.state()["seq"]
        yield f"event: sync\ndata: {json.dumps({'seq': last})}\n\n"
        for _ in range(3600):  # ~1h, client reconnects after
            await asyncio.sleep(1)
            cur = live.state()
            if cur["seq"] != last:
                last = cur["seq"]
                yield f"event: leads\ndata: {json.dumps(cur)}\n\n"
            else:
                yield ": ping\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
