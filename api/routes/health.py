"""GET /api/health

Not one of design spec §6's 7 endpoints -- added so Task 4's own Verify
done check ("hit the hosted app's URL from a browser with no VPN, on a
different network than Jack's Mac; confirm it actually responds") has
something simple and dependency-light to check once this is deployed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from api.db import get_conn

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict:
    try:
        conn = get_conn()
        try:
            conn.execute("SELECT 1")
            db_ok = True
        finally:
            conn.close()
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "reachable" if db_ok else "unreachable",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
