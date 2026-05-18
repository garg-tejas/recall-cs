"""
Request and response models for the RAG API.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for POST /api/chat."""

    query: str = Field(..., min_length=1, max_length=2000, description="User question")
    conversation_id: Optional[str] = Field(None, max_length=64, description="Session ID for conversation history")


class CitationOut(BaseModel):
    """Citation in API response."""

    index: int
    chunk_id: str
    snippet: str = ""


class ChunkSummary(BaseModel):
    """Summary of a chunk used in the answer."""

    id: str
    header_path: str
    snippet: str = ""


class ChatResponse(BaseModel):
    """Response for POST /api/chat."""

    answer: str
    citations: List[CitationOut] = Field(default_factory=list)
    chunks_used: List[ChunkSummary] = Field(default_factory=list)
    confidence: float = 0.0


class SearchRequest(BaseModel):
    """Request body for POST /api/search."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)


class SearchHit(BaseModel):
    """Single search result."""

    chunk_id: str
    header_path: str
    text: str
    score: float


class SearchResponse(BaseModel):
    """Response for POST /api/search."""

    query: str
    results: List[SearchHit] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Response for GET /api/health."""

    status: str = "ok"
    chunks_loaded: int = 0


class StatsResponse(BaseModel):
    """Response for GET /api/stats."""

    active_conversations: int = 0
