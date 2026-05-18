from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    review_states: Mapped[List["ReviewState"]] = relationship(back_populates="user")
    review_attempts: Mapped[List["ReviewAttempt"]] = relationship(back_populates="user")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # os, cn, dbms for now
    name: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cards: Mapped[List["Card"]] = relationship(back_populates="topic")


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id"), nullable=False, index=True
    )

    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    difficulty: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    question_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Links back to the RAG chunk this card was generated from
    source_chunk_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )

    # Optional comma-separated tags for future filtering
    tags: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    topic_key: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    variant_of_card_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cards.id"),
        nullable=True,
        index=True,
    )
    generation_origin: Mapped[str] = mapped_column(
        String(32), nullable=False, default="seed"
    )
    provenance_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    atomic_facts: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        nullable=False,
    )

    topic: Mapped["Topic"] = relationship(back_populates="cards")
    review_states: Mapped[List["ReviewState"]] = relationship(back_populates="card")
    review_attempts: Mapped[List["ReviewAttempt"]] = relationship(
        back_populates="card",
        foreign_keys="ReviewAttempt.card_id",
    )
    served_review_attempts: Mapped[List["ReviewAttempt"]] = relationship(
        back_populates="served_card",
        foreign_keys="ReviewAttempt.served_card_id",
    )
    variant_of: Mapped[Optional["Card"]] = relationship(
        "Card",
        remote_side=[id],
        back_populates="variants",
    )
    variants: Mapped[List["Card"]] = relationship(
        "Card",
        back_populates="variant_of",
    )


class ReviewState(Base):
    __tablename__ = "review_states"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_review_state_user_card"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    card_id: Mapped[int] = mapped_column(
        ForeignKey("cards.id"), nullable=False, index=True
    )

    repetitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ease_factor: Mapped[float] = mapped_column(default=2.5, nullable=False)
    due_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reviewed_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    lapses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="review_states")
    card: Mapped["Card"] = relationship(back_populates="review_states")


class ReviewAttempt(Base):
    __tablename__ = "review_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    card_id: Mapped[int] = mapped_column(
        ForeignKey("cards.id"), nullable=False, index=True
    )
    served_card_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cards.id"),
        nullable=True,
        index=True,
    )

    attempted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        nullable=False,
    )
    quality: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-5
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship(back_populates="review_attempts")
    card: Mapped["Card"] = relationship(
        back_populates="review_attempts",
        foreign_keys=[card_id],
    )
    served_card: Mapped[Optional["Card"]] = relationship(
        back_populates="served_review_attempts",
        foreign_keys=[served_card_id],
    )


class TopicTaxonomyNode(Base):
    __tablename__ = "topic_taxonomy_nodes"
    __table_args__ = (
        UniqueConstraint("subject", "topic_key", name="uq_topic_taxonomy_subject_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    topic_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_topic_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="deterministic"
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False,
    )


class TopicPrerequisite(Base):
    __tablename__ = "topic_prerequisites"
    __table_args__ = (
        UniqueConstraint(
            "subject",
            "topic_key",
            "prerequisite_key",
            name="uq_topic_prereq_subject_topic_prereq",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    topic_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    prerequisite_key: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="deterministic"
    )
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False,
    )


class UserTopicMastery(Base):
    __tablename__ = "user_topic_mastery"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "subject", "topic_key", name="uq_user_topic_mastery"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    topic_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    due_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overdue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lapse_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recent_trend: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mastery_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_reviewed_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False,
    )


class UserTopicSWOT(Base):
    __tablename__ = "user_topic_swot"
    __table_args__ = (
        UniqueConstraint("user_id", "subject", "topic_key", name="uq_user_topic_swot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    topic_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    strength_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    weakness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    threat_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    primary_bucket: Mapped[str] = mapped_column(
        String(16), nullable=False, default="opportunity"
    )
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="rule_hybrid"
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False,
    )


class Conversation(Base):
    """A persisted chat conversation for the AI tutor."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    topic_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False,
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    """Individual message in a tutor conversation."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunks_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=dt.datetime.utcnow,
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )
