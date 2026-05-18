from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class QuizCard(BaseModel):
    """Single quiz card to present to the user."""

    card_id: int
    canonical_card_id: Optional[int] = None
    is_variant: bool = False
    topic: str
    question: str
    difficulty: Optional[str] = None
    question_type: Optional[str] = None


class TopicStats(BaseModel):
    """Per-topic statistics for quiz progress."""

    topic: str
    total: int
    learned: int
    due_today: int
    overdue: int


class QuizStatsResponse(BaseModel):
    """Response body for /api/quiz/stats."""

    topics: List[TopicStats] = Field(default_factory=list)


class LearningPathNode(BaseModel):
    subject: str
    topic_key: str
    display_name: str
    mastery_score: float
    swot_bucket: str
    priority_score: float
    prerequisite_topic_keys: List[str] = Field(default_factory=list)


class SessionProgress(BaseModel):
    current_index: int = Field(
        ...,
        ge=0,
        description="Zero-based index of the current step in this session",
    )
    total: int = Field(..., ge=0, description="Total cards in the session queue")
    completed: bool


class QuizSessionStartRequest(BaseModel):
    topics: Optional[List[str]] = Field(
        default=None,
        description="Optional list of topic names/topic_keys to scope this session",
    )
    subject: Optional[str] = Field(
        default=None,
        description="Optional subject alias (os/cn/dbms)",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of cards to include in the session queue",
    )
    difficulty: Optional[str] = Field(
        default=None,
        description="Optional difficulty filter: easy, medium, or hard",
    )
    path_topics_ordered: Optional[List[str]] = Field(
        default=None,
        description="Optional ordered list of topic_keys defining learning path sequence. "
        "When provided, questions are served in this order instead of database/default order.",
    )


class QuizSessionStartResponse(BaseModel):
    session_id: str
    current_card: Optional[QuizCard] = None
    progress: SessionProgress
    path: List[LearningPathNode] = Field(default_factory=list)


class QuizSessionAnswerRequest(BaseModel):
    card_id: int
    user_answer: str = Field(..., max_length=4000)
    response_time_ms: Optional[int] = Field(default=None, ge=0)
    action: Optional[str] = Field(
        default=None,
        max_length=32,
        description="Optional action override. Use 'dont_know' to record a failed recall without LLM grading.",
    )


class QuizSessionAnswerResponse(BaseModel):
    answer: str
    explanation: Optional[str] = None
    source_chunk_id: Optional[str] = None
    show_source_context: bool = False
    model_score: Optional[int] = Field(default=None, ge=-1, le=5)
    verdict: Optional[str] = None
    should_remediate: bool = False
    concept_summary: Optional[str] = None
    where_you_missed: List[str] = Field(default_factory=list)
    next_due_at: Optional[str] = None
    interval_days: Optional[int] = None
    next_card: Optional[QuizCard] = None
    progress: SessionProgress


class QuizSessionFinishResponse(BaseModel):
    status: str
    session_id: str


class QuizSessionSkipResponse(BaseModel):
    next_card: Optional[QuizCard] = None
    progress: SessionProgress
