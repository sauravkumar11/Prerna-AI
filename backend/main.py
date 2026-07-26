"""
main.py
=======
Entry point for the Prerna backend.

Responsibilities:
  - Create the FastAPI application
  - Configure middleware (CORS)
  - Register API routers
  - Run startup/shutdown hooks (Gemini init, tool registration)

Nothing else. No business logic, no prompts, no tool calls.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import tools  # noqa: F401 — imports every tool module, triggering @action registration

from app.api import chat_router, tts_router, health_router
from app.dependencies import init_gemini
from config.settings import HOST, PORT, RELOAD, CORS_ORIGINS
from utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────
    logger.info("Prerna backend starting up...")
    init_gemini()
    logger.info("All tools registered: %s", list(__import__("agent.registry", fromlist=["get_tool_names"]).get_tool_names()))
    yield
    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Prerna backend shutting down.")


app = FastAPI(
    title="Prerna Backend",
    description="Prerna AI Companion",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
# Keep the original URL paths (/chat, /tts) so the frontend doesn't need
# any changes.  The routers are in app/api/ but mounted without an /api/
# prefix here for backward compatibility.
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(tts_router)


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=RELOAD)
