"""
Request and response models for the AI Tutor API.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TutorChatRequest(BaseModel):
    """Request body for POST /api/tutor/chat."""

    query: str = Field(..., min_length=1, description="User question")
    conversation_id: Optional[int] = Field(None, description="Conversation ID for history")
    subject: Optional[str] = Field(None, description="Optional subject scope (os, cn, dbms)")


class CitationOut(BaseModel):
    """Citation in tutor response."""

    index: int
    chunk_id: str
    snippet: str = ""


class ChunkSummary(BaseModel):
    """Summary of a chunk used in the answer."""

    id: str
    header_path: str
    snippet: str = ""


class TutorChatResponse(BaseModel):
    """Response for POST /api/tutor/chat."""

    answer: str
    citations: List[CitationOut] = Field(default_factory=list)
    chunks_used: List[ChunkSummary] = Field(default_factory=list)
    conversation_id: int


class ChatMessageOut(BaseModel):
    """Single chat message in a conversation."""

    id: int
    role: str
    content: str
    citations: List[CitationOut] = Field(default_factory=list)
    chunks: List[ChunkSummary] = Field(default_factory=list)
    created_at: datetime


class ConversationOut(BaseModel):
    """Conversation metadata."""

    id: int
    title: Optional[str]
    subject: Optional[str]
    topic_key: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetailOut(ConversationOut):
    """Conversation with messages."""

    messages: List[ChatMessageOut] = Field(default_factory=list)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""

    title: Optional[str] = None
    subject: Optional[str] = None
    topic_key: Optional[str] = None


class ConversationListResponse(BaseModel):
    """List of conversations."""

    conversations: List[ConversationOut] = Field(default_factory=list)
