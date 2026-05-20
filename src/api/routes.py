"""
API routes: chat, search, health, stats, conversation.
"""

from __future__ import annotations

import asyncio
import json
import queue
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.api.rate_limit import limiter
from src.auth.dependencies import get_current_active_user
from src.db.models import User
from src.generation import extract_citations
from src.orchestrator import ConversationMemory

from .models import (
    ChatRequest,
    ChatResponse,
    ChunkSummary,
    CitationOut,
    HealthResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
    StatsResponse,
)

router = APIRouter(prefix="/api", tags=["api"])


def _sse_event(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _get_state(request: Request) -> tuple[Any, Any, dict, int]:
    agent = getattr(request.app.state, "agent", None)
    retriever = getattr(request.app.state, "retriever", None)
    chunks_by_id = getattr(request.app.state, "chunks_by_id", {})
    chunks_loaded = getattr(request.app.state, "chunks_loaded", 0)
    return agent, retriever, chunks_by_id, chunks_loaded


def _get_sessions(request: Request) -> dict[tuple[int, str], ConversationMemory]:
    now = time.time()
    ttl_minutes = int(
        getattr(request.app.state, "conversation_session_ttl_minutes", 120)
    )
    max_sessions = int(getattr(request.app.state, "conversation_session_max", 2000))
    ttl_seconds = ttl_minutes * 60

    sessions = getattr(request.app.state, "sessions", None)
    last_seen = getattr(request.app.state, "session_last_seen", None)
    if sessions is None:
        request.app.state.sessions = {}
        sessions = request.app.state.sessions
    if last_seen is None:
        request.app.state.session_last_seen = {}
        last_seen = request.app.state.session_last_seen

    stale_keys = [k for k, ts in last_seen.items() if now - ts > ttl_seconds]
    for key in stale_keys:
        sessions.pop(key, None)
        last_seen.pop(key, None)

    if len(sessions) > max_sessions:
        overflow = len(sessions) - max_sessions
        oldest_keys = sorted(last_seen, key=lambda k: last_seen[k])[:overflow]
        for key in oldest_keys:
            sessions.pop(key, None)
            last_seen.pop(key, None)

    return sessions


def _touch_session(request: Request, key: tuple[int, str]) -> None:
    last_seen = getattr(request.app.state, "session_last_seen", None)
    if last_seen is None:
        request.app.state.session_last_seen = {}
        last_seen = request.app.state.session_last_seen
    last_seen[key] = time.time()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Health check — public, no auth required."""
    _, _, _, chunks_loaded = _get_state(request)
    return HealthResponse(status="ok", chunks_loaded=chunks_loaded)


@router.get("/readyz", response_model=None)
async def readyz(request: Request) -> dict | JSONResponse:
    """Readiness probe — checks chunks loaded and basic app state."""
    agent, retriever, _, chunks_loaded = _get_state(request)
    if agent is None or retriever is None or chunks_loaded == 0:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "chunks_loaded": chunks_loaded},
        )
    return {"status": "ready", "chunks_loaded": chunks_loaded}


@router.get("/stats", response_model=StatsResponse)
async def stats(
    request: Request,
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> StatsResponse:
    """Usage statistics — requires auth."""
    sessions = _get_sessions(request)
    return StatsResponse(active_conversations=len(sessions))


async def _stream_chat(
    request: Request,
    body: ChatRequest,
    agent: Any,
    chunks_by_id: dict,
    sessions: dict,
    user_id: int,
):
    conversation_id = body.conversation_id or "default"
    key = (user_id, conversation_id)
    memory = sessions.get(key)
    if memory is None:
        memory = ConversationMemory(max_turns=10)
        sessions[key] = memory
    _touch_session(request, key)
    history = memory.get_history()
    results, fallback = await asyncio.to_thread(agent.retrieve, body.query, history)
    if fallback is not None:
        yield _sse_event("token", fallback.answer)
        yield _sse_event("done", json.dumps({"citations": [], "chunks_used": []}))
        memory.add_turn(body.query, fallback.answer, fallback.sources_used)
        return
    q: queue.Queue = queue.Queue()

    def run_stream():
        full = ""
        for chunk in agent.generator.generate_stream(body.query, results):
            full += chunk
            q.put(("token", chunk))
        q.put(("done", full))

    executor = getattr(request.app.state, "llm_executor", None)
    loop = asyncio.get_running_loop()
    try:
        if executor is not None:
            await asyncio.wait_for(
                loop.run_in_executor(executor, run_stream),
                timeout=45.0,
            )
        else:
            import threading

            thread = threading.Thread(target=run_stream)
            thread.start()
            thread.join(timeout=45)
            if thread.is_alive():
                raise asyncio.TimeoutError
    except asyncio.TimeoutError:
        yield _sse_event("error", json.dumps({"detail": "LLM stream timed out"}))
        return

    full_text = ""
    while True:
        kind, payload = await loop.run_in_executor(None, q.get)
        if kind == "done":
            full_text = payload
            break
        yield _sse_event("token", json.dumps({"token": payload}))
    citations = extract_citations(full_text, results)
    sources_used = [r.chunk.id for r in results]
    chunks_used = []
    for cid in sources_used:
        chunk = chunks_by_id.get(cid)
        if chunk:
            chunks_used.append(
                {
                    "id": chunk.id,
                    "header_path": chunk.header_path,
                    "snippet": (chunk.text[:300] + "...")
                    if len(chunk.text) > 300
                    else chunk.text,
                }
            )
        else:
            chunks_used.append({"id": cid, "header_path": "", "snippet": ""})
    citations_out = [
        {"index": c.index, "chunk_id": c.chunk_id, "snippet": c.snippet}
        for c in citations
    ]
    yield _sse_event(
        "done", json.dumps({"citations": citations_out, "chunks_used": chunks_used})
    )
    memory.add_turn(body.query, full_text, sources_used)


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ChatResponse | JSONResponse:
    """Answer a question using the RAG agent (with optional conversation history). Requires auth."""
    agent, _, chunks_by_id, chunks_loaded = _get_state(request)
    if agent is None or chunks_loaded == 0:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Service unavailable: chunks not loaded or agent not initialized."
            },
        )
    sessions = _get_sessions(request)
    conversation_id = body.conversation_id or "default"
    key = (current_user.id, conversation_id)
    memory = sessions.get(key)
    if memory is None:
        memory = ConversationMemory(max_turns=10)
        sessions[key] = memory
    _touch_session(request, key)
    history = memory.get_history()
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(agent.answer, body.query, history),
            timeout=45.0,
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504, content={"detail": "LLM request timed out"}
        )
    memory.add_turn(body.query, resp.answer, resp.sources_used)
    chunks_used = []
    for cid in resp.sources_used:
        chunk = chunks_by_id.get(cid)
        if chunk:
            chunks_used.append(
                ChunkSummary(
                    id=chunk.id,
                    header_path=chunk.header_path,
                    snippet=(chunk.text[:300] + "…")
                    if len(chunk.text) > 300
                    else chunk.text,
                )
            )
        else:
            chunks_used.append(ChunkSummary(id=cid, header_path="", snippet=""))
    citations = [
        CitationOut(index=c.index, chunk_id=c.chunk_id, snippet=c.snippet)
        for c in resp.citations
    ]
    return ChatResponse(
        answer=resp.answer,
        citations=citations,
        chunks_used=chunks_used,
        confidence=0.0,
    )


@router.post("/chat/stream", response_model=None)
@limiter.limit("20/minute")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> StreamingResponse | JSONResponse:
    """Stream answer tokens via SSE; final event has citations and chunks_used. Requires auth."""
    agent, _, chunks_by_id, chunks_loaded = _get_state(request)
    if agent is None or chunks_loaded == 0:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Service unavailable: chunks not loaded or agent not initialized."
            },
        )
    sessions = _get_sessions(request)
    return StreamingResponse(
        _stream_chat(request, body, agent, chunks_by_id, sessions, current_user.id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/search", response_model=SearchResponse)
@limiter.limit("60/minute")
async def search_endpoint(
    request: Request,
    body: SearchRequest,
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> SearchResponse | JSONResponse:
    """Direct search (no generation). Requires auth."""
    _, retriever, chunks_by_id, chunks_loaded = _get_state(request)
    if retriever is None or chunks_loaded == 0:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Service unavailable: chunks not loaded or retriever not initialized."
            },
        )
    results = await asyncio.to_thread(retriever.search, body.query, body.top_k)
    hits = []
    for r in results:
        chunk = r.chunk
        hits.append(
            SearchHit(
                chunk_id=chunk.id,
                header_path=chunk.header_path,
                text=chunk.text[:500] + "…" if len(chunk.text) > 500 else chunk.text,
                score=round(r.score, 4),
            )
        )
    return SearchResponse(query=body.query, results=hits)


@router.delete("/conversation")
@limiter.limit("60/minute")
async def clear_conversation(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    conversation_id: str = "default",
) -> dict:
    """Clear conversation history for the given conversation_id. Requires auth."""
    sessions = _get_sessions(request)
    key = (current_user.id, conversation_id)
    if key in sessions:
        sessions[key].clear()
    last_seen = getattr(request.app.state, "session_last_seen", None)
    if last_seen is not None:
        last_seen.pop(key, None)
    return {"ok": True, "conversation_id": conversation_id}
