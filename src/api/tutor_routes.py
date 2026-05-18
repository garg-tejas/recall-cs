"""
AI Tutor API routes: conversation CRUD + streaming/non-streaming chat.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.tutor_models import (
    ChatMessageOut,
    ChunkSummary,
    CitationOut,
    ConversationDetailOut,
    ConversationListResponse,
    ConversationOut,
    CreateConversationRequest,
    TutorChatRequest,
    TutorChatResponse,
)
from src.auth.dependencies import get_current_active_user
from src.db.models import ChatMessage, Conversation, User
from src.db.session import get_db

router = APIRouter(prefix="/api/tutor", tags=["tutor"])


def _sse_event(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


# ------------------------------------------------------------------
# Conversation CRUD
# ------------------------------------------------------------------

@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ConversationListResponse:
    """List all conversations for the current user."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(desc(Conversation.updated_at))
    )
    conversations = result.scalars().all()

    out = []
    for conv in conversations:
        msg_count = len(conv.messages) if conv.messages else 0
        out.append(
            ConversationOut(
                id=conv.id,
                title=conv.title,
                subject=conv.subject,
                topic_key=conv.topic_key,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=msg_count,
            )
        )
    return ConversationListResponse(conversations=out)


@router.post("/conversations", response_model=ConversationDetailOut)
async def create_conversation(
    payload: CreateConversationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ConversationDetailOut:
    """Create a new conversation."""
    conv = Conversation(
        user_id=current_user.id,
        title=payload.title,
        subject=payload.subject,
        topic_key=payload.topic_key,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationDetailOut(
        id=conv.id,
        title=conv.title,
        subject=conv.subject,
        topic_key=conv.topic_key,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
        messages=[],
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ConversationDetailOut:
    """Get a single conversation with all messages."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages_out = []
    for msg in conv.messages or []:
        citations = json.loads(msg.citations_json) if msg.citations_json else []
        chunks = json.loads(msg.chunks_json) if msg.chunks_json else []
        messages_out.append(
            ChatMessageOut(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                citations=[CitationOut(**c) for c in citations],
                chunks=[ChunkSummary(**c) for c in chunks],
                created_at=msg.created_at,
            )
        )

    return ConversationDetailOut(
        id=conv.id,
        title=conv.title,
        subject=conv.subject,
        topic_key=conv.topic_key,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=len(messages_out),
        messages=messages_out,
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    """Delete a conversation and all its messages."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.delete(conv)
    await db.commit()
    return {"ok": True}


# ------------------------------------------------------------------
# Chat helpers
# ------------------------------------------------------------------

async def _load_conversation_history(
    db: AsyncSession, user_id: int, conversation_id: int | None
) -> tuple[Conversation | None, list[dict]]:
    """Load conversation and return (conv, history_list)."""
    if conversation_id is None:
        return None, []

    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        return None, []

    history = []
    for msg in conv.messages or []:
        history.append({"role": msg.role, "content": msg.content})
    return conv, history


async def _save_message(
    db: AsyncSession,
    conversation_id: int,
    role: str,
    content: str,
    citations: list[dict] | None = None,
    chunks: list[dict] | None = None,
) -> None:
    """Persist a chat message."""
    msg = ChatMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations_json=json.dumps(citations) if citations else None,
        chunks_json=json.dumps(chunks) if chunks else None,
    )
    db.add(msg)
    await db.commit()


# ------------------------------------------------------------------
# Non-streaming chat
# ------------------------------------------------------------------

@router.post("/chat", response_model=TutorChatResponse)
async def tutor_chat(
    body: TutorChatRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TutorChatResponse | JSONResponse:
    """Answer a question using the tutor RAG agent (with optional conversation history)."""
    tutor_agent = getattr(request.app.state, "tutor_agent", None)
    chunks_by_id = getattr(request.app.state, "chunks_by_id", {})
    chunks_loaded = getattr(request.app.state, "chunks_loaded", 0)

    if tutor_agent is None or chunks_loaded == 0:
        return JSONResponse(
            status_code=503,
            content={"detail": "Tutor service unavailable."},
        )

    conv, history = await _load_conversation_history(
        db, current_user.id, body.conversation_id
    )

    # Scope retrieval to subject if set on conversation or request
    subject = body.subject or (conv.subject if conv else None)

    resp = await asyncio.to_thread(tutor_agent.answer, body.query, history, subject=subject)

    # Create conversation if none exists
    if conv is None:
        title = body.query[:60] + ("..." if len(body.query) > 60 else "")
        conv = Conversation(
            user_id=current_user.id,
            title=title,
            subject=subject,
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    # Save user question
    await _save_message(db, conv.id, "user", body.query)

    # Save assistant response with citations/chunks
    citations_out = [
        CitationOut(index=c.index, chunk_id=c.chunk_id, snippet=c.snippet)
        for c in resp.citations
    ]
    chunks_used = []
    for cid in resp.sources_used:
        chunk = chunks_by_id.get(cid)
        if chunk:
            chunks_used.append(
                ChunkSummary(
                    id=chunk.id,
                    header_path=chunk.header_path,
                    snippet=(chunk.text[:300] + "...") if len(chunk.text) > 300 else chunk.text,
                )
            )
        else:
            chunks_used.append(ChunkSummary(id=cid, header_path="", snippet=""))

    await _save_message(
        db,
        conv.id,
        "assistant",
        resp.answer,
        citations=[c.model_dump() for c in citations_out],
        chunks=[c.model_dump() for c in chunks_used],
    )

    return TutorChatResponse(
        answer=resp.answer,
        citations=citations_out,
        chunks_used=chunks_used,
        conversation_id=conv.id,
    )


# ------------------------------------------------------------------
# Streaming chat (SSE)
# ------------------------------------------------------------------

async def _stream_tutor_chat(
    request: Request,
    body: TutorChatRequest,
    db: AsyncSession,
    current_user: User,
):
    """Stream tutor answer tokens via SSE."""
    tutor_agent = getattr(request.app.state, "tutor_agent", None)
    chunks_by_id = getattr(request.app.state, "chunks_by_id", {})

    if tutor_agent is None:
        yield _sse_event("error", json.dumps({"detail": "Tutor service unavailable."}))
        return

    conv, history = await _load_conversation_history(
        db, current_user.id, body.conversation_id
    )
    subject = body.subject or (conv.subject if conv else None)

    # Retrieve results first (blocking)
    results, fallback = await asyncio.to_thread(tutor_agent.retrieve, body.query, history, subject=subject)
    if fallback is not None:
        yield _sse_event("token", json.dumps({"token": fallback.answer}))
        yield _sse_event("done", json.dumps({"citations": [], "chunks_used": [], "conversation_id": conv.id if conv else None}))
        return

    # Create conversation if needed
    if conv is None:
        title = body.query[:60] + ("..." if len(body.query) > 60 else "")
        conv = Conversation(
            user_id=current_user.id,
            title=title,
            subject=subject,
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    # Save user question
    await _save_message(db, conv.id, "user", body.query)

    # Stream generation using bounded thread pool
    q: queue.Queue = queue.Queue()

    def run_stream():
        full = ""
        for chunk in tutor_agent.generator.generate_stream(body.query, results):
            full += chunk
            q.put(("token", chunk))
        q.put(("done", full))

    loop = asyncio.get_running_loop()
    executor = getattr(request.app.state, "llm_executor", None)
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

    # Build citations and chunks
    from src.generation import extract_citations
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

    # Save assistant response
    await _save_message(
        db,
        conv.id,
        "assistant",
        full_text,
        citations=citations_out,
        chunks=chunks_used,
    )

    yield _sse_event(
        "done",
        json.dumps({
            "citations": citations_out,
            "chunks_used": chunks_used,
            "conversation_id": conv.id,
        }),
    )


@router.post("/chat/stream", response_model=None)
async def tutor_chat_stream(
    body: TutorChatRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> StreamingResponse | JSONResponse:
    """Stream tutor answer tokens via SSE; final event has citations and chunks_used."""
    return StreamingResponse(
        _stream_tutor_chat(request, body, db, current_user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
