from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Card, ReviewAttempt, ReviewState, Topic
from src.skills.grader import GradeResult, grade_answer
from src.skills.path_planner import LearningPathPlanner, PathNode
from src.skills.quiz_service import QuizService
from src.skills.swot import refresh_user_swot
from src.skills.variant_generator import VariantGenerator

logger = logging.getLogger(__name__)


@dataclass
class SessionAnswerResult:
    grade: GradeResult
    updated_state: ReviewState
    answer: str
    explanation: Optional[str]
    source_chunk_id: Optional[str]
    concept_summary: str
    where_you_missed: list[str]
    should_remediate: bool
    next_card: Optional[Card]


@dataclass
class QuizSessionState:
    session_id: str
    user_id: int
    card_ids: List[int]
    cards_by_id: Dict[int, Card]
    review_states_by_card: Dict[int, ReviewState]
    due_card_ids: set[int] = field(default_factory=set)
    served_card_ids_by_index: Dict[int, int] = field(default_factory=dict)
    path_nodes: List[PathNode] = field(default_factory=list)
    cursor: int = 0
    created_at: dt.datetime = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )

    @property
    def total(self) -> int:
        return len(self.card_ids)

    @property
    def completed(self) -> bool:
        return self.cursor >= self.total

    def current_card(self) -> Optional[Card]:
        if self.completed:
            return None
        card_id = self.card_ids[self.cursor]
        return self.cards_by_id.get(card_id)


class QuizSessionService:
    def __init__(self, *, chunks_by_id: Optional[dict[str, Any]] = None) -> None:
        self.quiz_service = QuizService()
        self.path_planner = LearningPathPlanner()
        self.variant_generator = VariantGenerator(chunks_by_id=chunks_by_id)
        self.chunks_by_id = chunks_by_id or {}

    @staticmethod
    def _normalize_scope_values(values: Optional[Sequence[str]]) -> list[str]:
        return [
            str(value).strip().lower()
            for value in (values or [])
            if str(value).strip()
        ]

    async def start_session(
        self,
        *,
        db: AsyncSession,
        user_id: int,
        limit: int = 20,
        topics: Optional[List[str]] = None,
        subject: Optional[str] = None,
        difficulty: Optional[str] = None,
        path_topics_ordered: Optional[List[str]] = None,
    ) -> QuizSessionState:
        card_query = select(Card).join(Topic).options(selectinload(Card.topic))
        if topics:
            normalized_topics = self._normalize_scope_values(topics)
            if normalized_topics:
                # Defensive: if topics look like topic_keys (e.g. "cn:core"),
                # also extract the subject prefix ("cn") to match Topic.name.
                subject_aliases = {
                    t.split(":", 1)[0]
                    for t in normalized_topics
                    if ":" in t
                }
                all_topic_names = list(set(normalized_topics) | subject_aliases)
                card_query = card_query.where(
                    or_(
                        Topic.name.in_(all_topic_names),
                        Card.topic_key.in_(normalized_topics),
                    )
                )
        if subject:
            card_query = card_query.where(Topic.name == subject.strip().lower())
        if difficulty:
            card_query = card_query.where(Card.difficulty == difficulty)

        card_result = await db.execute(card_query)
        cards = card_result.scalars().unique().all()
        logger.info(
            "start_session: user=%s topics=%s subject=%s difficulty=%s => cards=%d",
            user_id, topics, subject, difficulty, len(cards),
        )
        if not cards:
            logger.warning("start_session: no cards found for user=%s", user_id)
            return QuizSessionState(
                session_id=str(uuid.uuid4()),
                user_id=user_id,
                card_ids=[],
                cards_by_id={},
                review_states_by_card={},
                path_nodes=[],
            )

        card_ids = [card.id for card in cards]
        state_result = await db.execute(
            select(ReviewState).where(
                ReviewState.user_id == user_id,
                ReviewState.card_id.in_(card_ids),
            )
        )
        review_states = state_result.scalars().all()

        attempts_result = await db.execute(
            select(ReviewAttempt).where(
                ReviewAttempt.user_id == user_id,
                ReviewAttempt.card_id.in_(card_ids),
            )
        )
        review_attempts = attempts_result.scalars().all()

        await refresh_user_swot(
            db=db,
            user_id=user_id,
            cards=cards,
            review_states=review_states,
            review_attempts=review_attempts,
        )
        await db.commit()

        path_nodes = await self.path_planner.build_path(
            db=db,
            user_id=user_id,
            subject=subject,
            topic_keys=[card.topic_key for card in cards if card.topic_key],
        )
        # Build path_rank: topic_key (lowercase) -> index in learning path.
        # Prefer explicit path_topics_ordered from client when provided.
        if path_topics_ordered and len(path_topics_ordered) > 0:
            path_rank = {
                tk.strip().lower(): idx
                for idx, tk in enumerate(path_topics_ordered)
                if tk and str(tk).strip()
            }
        else:
            path_rank = {
                node.topic_key.strip().lower(): idx
                for idx, node in enumerate(path_nodes)
            }

        def _card_path_rank(card: Card) -> int:
            topic_key = (card.topic_key or "").strip().lower()
            if not topic_key and card.topic:
                topic_key = (getattr(card.topic, "name", "") or "").strip().lower()
            return path_rank.get(topic_key, len(path_rank))

        selected = self.quiz_service.get_next_cards(
            user_id=user_id,
            cards=cards,
            review_states=review_states,
            topics=topics,
            limit=limit,
        )
        selected.sort(
            key=lambda card: (
                _card_path_rank(card),
                card.id,
            )
        )
        now = dt.datetime.now(dt.timezone.utc)
        due_card_ids = {
            state.card_id
            for state in review_states
            if state.due_at is not None and state.due_at <= now
        }

        logger.info(
            "start_session: user=%s selected=%d due=%d new=%d path_nodes=%d",
            user_id, len(selected), len(due_card_ids), len(selected) - len(due_card_ids), len(path_nodes),
        )
        return QuizSessionState(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            card_ids=[card.id for card in selected],
            cards_by_id={card.id: card for card in cards},
            review_states_by_card={state.card_id: state for state in review_states},
            due_card_ids=due_card_ids,
            path_nodes=path_nodes,
        )

    async def get_current_presented_card(
        self,
        *,
        db: AsyncSession,
        state: QuizSessionState,
    ) -> Optional[Card]:
        logger.info(
            "get_current_presented_card: session=%s user=%s cursor=%d total=%d completed=%s",
            state.session_id, state.user_id, state.cursor, state.total, state.completed,
        )
        if state.completed:
            logger.info("get_current_presented_card: session completed")
            return None
        current_index = state.cursor
        canonical_card = state.current_card()
        if canonical_card is None:
            logger.info(
                "get_current_presented_card: no card at cursor=%d card_ids=%s cards_by_id_keys=%s",
                current_index, state.card_ids[:5], list(state.cards_by_id.keys())[:5],
            )
            return None

        cached_served_id = state.served_card_ids_by_index.get(current_index)
        if cached_served_id is not None:
            cached = state.cards_by_id.get(cached_served_id)
            if cached is not None:
                return cached
            served_result = await db.execute(
                select(Card)
                .options(selectinload(Card.topic))
                .where(Card.id == cached_served_id)
            )
            loaded = served_result.scalar_one_or_none()
            if loaded is not None:
                state.cards_by_id[loaded.id] = loaded
                return loaded

        is_due = canonical_card.id in state.due_card_ids
        if is_due:
            served = await self.variant_generator.select_or_create_variant(
                db=db,
                user_id=state.user_id,
                canonical_card=canonical_card,
            )
            if served.topic is None and canonical_card.topic is not None:  # type: ignore[union-attr]
                served.topic = canonical_card.topic  # type: ignore[assignment]
        else:
            served = canonical_card

        state.cards_by_id[served.id] = served
        state.served_card_ids_by_index[current_index] = served.id
        logger.info("get_current_presented_card: returning card_id=%d", served.id)
        return served

    async def submit_current_answer(
        self,
        *,
        db: AsyncSession,
        state: QuizSessionState,
        card_id: int,
        user_answer: str,
        response_time_ms: Optional[int] = None,
        action: Optional[str] = None,
    ) -> SessionAnswerResult:
        canonical = state.current_card()
        if canonical is None:
            raise ValueError("Session is already complete")

        presented = await self.get_current_presented_card(db=db, state=state)
        if presented is None:
            raise ValueError("Session is already complete")
        if presented.id != card_id:
            raise ValueError("card_id does not match current session card")

        explanation = None
        if presented.source_chunk_id and presented.source_chunk_id in self.chunks_by_id:
            chunk = self.chunks_by_id[presented.source_chunk_id]
            text = str(getattr(chunk, "text", "") or "")
            if text:
                max_len = 600
                explanation = text[:max_len] + ("..." if len(text) > max_len else "")

        if action == "dont_know":
            grade = GradeResult(
                score_0_5=0,
                verdict="dont_know",
                missing_points=[],
                incorrect_points=[],
                concept_summary="You chose not to answer. Review the reference answer below.",
                where_you_missed=[],
                should_remediate=True,
            )
        else:
            subject = canonical.topic.name if canonical.topic else None  # type: ignore[union-attr]
            grade = grade_answer(
                question=presented.question,
                reference_answer=presented.answer,
                user_answer=user_answer,
                subject=subject,
                context_excerpt=explanation,
                question_type=presented.question_type,
                atomic_facts=getattr(presented, "atomic_facts", None),
            )

        # When grading fails (score_0_5 == -1), skip SM-2 update entirely:
        # record a quality of 0 so the attempt is logged, but don't penalise
        # the spaced-repetition state with a nonsensical value.
        sm2_quality = grade.score_0_5 if grade.score_0_5 >= 0 else 0

        review_state = state.review_states_by_card.get(canonical.id)
        updated_state, attempt = self.quiz_service.record_attempt(
            user_id=state.user_id,
            card=canonical,
            review_state=review_state,
            quality=sm2_quality,
            served_card_id=presented.id,
            response_time_ms=response_time_ms,
        )
        if review_state is None:
            db.add(updated_state)
        db.add(attempt)
        await db.commit()
        await db.refresh(updated_state)

        state.review_states_by_card[canonical.id] = updated_state
        state.cursor += 1
        next_card = await self.get_current_presented_card(db=db, state=state)

        return SessionAnswerResult(
            grade=grade,
            updated_state=updated_state,
            answer=presented.answer,
            explanation=explanation,
            source_chunk_id=presented.source_chunk_id,
            concept_summary=grade.concept_summary,
            where_you_missed=grade.where_you_missed,
            should_remediate=grade.should_remediate,
            next_card=next_card,
        )

    async def skip_current_card(
        self,
        *,
        db: AsyncSession,
        state: QuizSessionState,
    ) -> Optional[Card]:
        """Advance cursor without recording any attempt. Returns the next card (or None)."""
        if state.completed:
            raise ValueError("Session is already complete")
        state.cursor += 1
        return await self.get_current_presented_card(db=db, state=state)
