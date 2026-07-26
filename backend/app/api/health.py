"""
Health router
=============
GET /health — liveness/readiness check reporting REAL subsystem status,
not just "the process is running". Used for local debugging as much as
for load balancer / Docker health probes.

Deliberately bounded scope (v1.1): reports current status of the
subsystems that are cheap and safe to check without side effects (no
network calls to Gemini, no launching Chrome just to check on it). A full
auto-restart Health Monitor watching these continuously in the background
is out of scope for this pass — see the trace.py/logger.py docstrings for
the "what's v1.1 vs. deferred" split.
"""

from __future__ import annotations

from fastapi import APIRouter

from config.settings import MEMORY_DIR, GEMINI_API_KEYS

router = APIRouter()


def _check_gemini_configured() -> dict:
    try:
        from app.dependencies import _manager
        if _manager is None:
            return {"status": "not_initialized", "keys_configured": len(GEMINI_API_KEYS)}
        return {
            "status": "ready",
            "keys_configured": len(GEMINI_API_KEYS),
            "models": _manager._models,
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _check_chrome_session() -> dict:
    try:
        from tools.chrome_session import get_chrome_session
        session = get_chrome_session()
        if session._driver is None:
            return {"status": "not_started"}
        alive = session._is_alive(session._driver)
        return {
            "status": "attached" if alive else "stale",
            "engine": session._engine["name"] if session._engine else None,
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _check_memory_dir() -> dict:
    try:
        writable = MEMORY_DIR.exists() and __import__("os").access(MEMORY_DIR, __import__("os").W_OK)
        return {"status": "ok" if writable else "not_writable", "path": str(MEMORY_DIR)}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/health")
def health():
    checks = {
        "gemini": _check_gemini_configured(),
        "chrome_session": _check_chrome_session(),
        "memory": _check_memory_dir(),
    }
    overall_ok = all(
        c.get("status") in ("ready", "ok", "attached", "not_started")
        for c in checks.values()
    )
    return {
        "status": "ok" if overall_ok else "degraded",
        "service": "prerna-backend",
        "checks": checks,
    }


@router.get("/")
def root():
    return {"message": "Prerna Backend Running"}