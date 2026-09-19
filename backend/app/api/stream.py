"""Server-sent events for live website sync (JWT via ?token=, EventSource can't set headers)."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, Request
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
async def stream_leads(request: Request, token: str = Query("")):
    if not _auth(token):
        raise HTTPException(401, "Invalid token")

    async def gen():
        last = live.state()["seq"]
        yield f"event: sync\ndata: {json.dumps({'seq': last})}\n\n"
        # Keep-alive every 15s; exit early if client disconnects. Cap ~30 min.
        for _ in range(120):
            if await request.is_disconnected():
                break
            await asyncio.sleep(15)
            if await request.is_disconnected():
                break
            cur = live.state()
            if cur["seq"] != last:
                last = cur["seq"]
                yield f"event: leads\ndata: {json.dumps(cur)}\n\n"
            else:
                yield ": ping\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
