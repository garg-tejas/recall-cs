"""
API routes: chat, search, health, stats, conversation.
"""

from __future__ import annotations

import asyncio
import json
import queue
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.auth.dependencies import get_current_active_user
from src.db.models import User
from src.generation import extract_citations
from src.orchestrator import ConversationMemory

from .models import (
    ChatRequest,
    ChatResponse,
    CitationOut,
    ChunkSummary,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SearchHit,
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
    sessions = getattr(request.app.state, "sessions", None)
    if sessions is None:
        request.app.state.sessions = {}
        sessions = request.app.state.sessions
    return sessions


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Health check — public, no auth required."""
    _, _, _, chunks_loaded = _get_state(request)
    return HealthResponse(status="ok", chunks_loaded=chunks_loaded)


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
    if executor is not None:
        await loop.run_in_executor(executor, run_stream)
    else:
        import threading
        thread = threading.Thread(target=run_stream)
        thread.start()

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
                    "snippet": (chunk.text[:300] + "...") if len(chunk.text) > 300 else chunk.text,
                }
            )
        else:
            chunks_used.append({"id": cid, "header_path": "", "snippet": ""})
    citations_out = [{"index": c.index, "chunk_id": c.chunk_id, "snippet": c.snippet} for c in citations]
    yield _sse_event("done", json.dumps({"citations": citations_out, "chunks_used": chunks_used}))
    memory.add_turn(body.query, full_text, sources_used)


@router.post("/chat", response_model=ChatResponse)
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
            content={"detail": "Service unavailable: chunks not loaded or agent not initialized."},
        )
    sessions = _get_sessions(request)
    conversation_id = body.conversation_id or "default"
    key = (current_user.id, conversation_id)
    memory = sessions.get(key)
    if memory is None:
        memory = ConversationMemory(max_turns=10)
        sessions[key] = memory
    history = memory.get_history()
    resp = await asyncio.to_thread(agent.answer, body.query, history)
    memory.add_turn(body.query, resp.answer, resp.sources_used)
    chunks_used = []
    for cid in resp.sources_used:
        chunk = chunks_by_id.get(cid)
        if chunk:
            chunks_used.append(
                ChunkSummary(
                    id=chunk.id,
                    header_path=chunk.header_path,
                    snippet=(chunk.text[:300] + "…") if len(chunk.text) > 300 else chunk.text,
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
            content={"detail": "Service unavailable: chunks not loaded or agent not initialized."},
        )
    sessions = _get_sessions(request)
    return StreamingResponse(
        _stream_chat(request, body, agent, chunks_by_id, sessions, current_user.id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/search", response_model=SearchResponse)
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
            content={"detail": "Service unavailable: chunks not loaded or retriever not initialized."},
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
    return {"ok": True, "conversation_id": conversation_id}
