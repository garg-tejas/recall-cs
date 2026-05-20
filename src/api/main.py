"""
FastAPI application for the RAG API.
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import src.config

logger = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth.routes import router as auth_router
from src.skills.session_service import QuizSessionService

from .deps import build_agent_and_chunks, build_tutor_agent
from .quiz_routes import router as quiz_router
from .rate_limit import limiter
from .routes import router
from .tutor_routes import router as tutor_router


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://api.fontshare.com https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://api.fontshare.com; "
            "script-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none';"
        )
        return response


def _get_cors_origins() -> list[str]:
    """
    Parse BACKEND_CORS_ORIGINS env var into a list.

    - Comma-separated list of origins, e.g. "http://localhost:5173,https://app.example.com"
    - If unset, default to local Vite dev server.
    - If set to "*", allow all origins (no credentials).
    """
    raw = os.getenv("BACKEND_CORS_ORIGINS")
    if not raw:
        return ["http://localhost:5173"]

    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if origins == ["*"]:
        return ["*"]
    return origins


def _get_env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start server immediately; load chunks and build agents in background."""
    from src.llm.client import HF_ROUTER_API_KEY, LLM_API_KEY, LLM_BASE_URL

    if not LLM_BASE_URL or not LLM_API_KEY:
        logger.warning(
            "LLM_BASE_URL or LLM_API_KEY not set. Grading and quiz features may fail."
        )
    if not HF_ROUTER_API_KEY:
        logger.warning("HF_ROUTER_API_KEY not set. Tutor chat will be unavailable.")

    # Initialise state immediately so the app can serve /api/health right away
    app.state.agent = None
    app.state.retriever = None
    app.state.chunks_by_id = {}
    app.state.chunks_loaded = 0
    app.state.sessions = {}
    app.state.session_last_seen = {}
    app.state.quiz_sessions = {}
    app.state.tutor_agent = None
    app.state.startup_complete = False
    app.state.llm_executor = ThreadPoolExecutor(
        max_workers=8, thread_name_prefix="llm-"
    )
    app.state.session_service = QuizSessionService(chunks_by_id={})

    async def _background_init():
        try:
            loop = asyncio.get_event_loop()
            agent, retriever, chunks_by_id, chunks_loaded = await loop.run_in_executor(
                None, build_agent_and_chunks
            )
            app.state.agent = agent
            app.state.retriever = retriever
            app.state.chunks_by_id = chunks_by_id or {}
            app.state.chunks_loaded = chunks_loaded
            app.state.tutor_agent = build_tutor_agent(retriever) if retriever else None
            app.state.session_service = QuizSessionService(
                chunks_by_id=app.state.chunks_by_id
            )
            app.state.startup_complete = True
            logger.info("Background startup complete. %s chunks loaded.", chunks_loaded)
        except Exception:
            logger.exception("Background startup failed.")

    asyncio.create_task(_background_init())
    yield
    app.state.sessions.clear()
    app.state.quiz_sessions.clear()
    app.state.llm_executor.shutdown(wait=False)


cors_origins = _get_cors_origins()

app = FastAPI(
    title="Synthetix-CS API",
    description="RAG API for technical Q&A (OS, DBMS, Computer Networks)",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.conversation_session_ttl_minutes = _get_env_int(
    "CONVERSATION_SESSION_TTL_MINUTES", 120
)
app.state.conversation_session_max = _get_env_int("CONVERSATION_SESSION_MAX", 2000)
app.state.quiz_session_ttl_minutes = _get_env_int("QUIZ_SESSION_TTL_MINUTES", 180)
app.state.quiz_session_max = _get_env_int("QUIZ_SESSION_MAX", 2000)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    allow_credentials=False if cors_origins == ["*"] else True,
)
app.include_router(router)
app.include_router(auth_router)
app.include_router(quiz_router)
app.include_router(tutor_router)
