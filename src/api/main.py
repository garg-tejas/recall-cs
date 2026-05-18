"""
FastAPI application for the RAG API.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .deps import build_agent_and_chunks, build_tutor_agent
from .routes import router
from .quiz_routes import router as quiz_router
from .tutor_routes import router as tutor_router
from src.auth.routes import router as auth_router


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load chunks and build agents on startup; clear on shutdown."""
    agent, retriever, chunks_by_id, chunks_loaded = build_agent_and_chunks()
    app.state.agent = agent
    app.state.retriever = retriever
    app.state.chunks_by_id = chunks_by_id or {}
    app.state.chunks_loaded = chunks_loaded
    app.state.sessions = {}
    app.state.quiz_sessions = {}
    app.state.tutor_agent = build_tutor_agent(retriever) if retriever else None
    yield
    app.state.sessions.clear()
    app.state.quiz_sessions.clear()


cors_origins = _get_cors_origins()

app = FastAPI(
    title="Synthetix-CS API",
    description="RAG API for technical Q&A (OS, DBMS, Computer Networks)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False if cors_origins == ["*"] else True,
)
app.include_router(router)
app.include_router(auth_router)
app.include_router(quiz_router)
app.include_router(tutor_router)
