from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, cast

from src.db.models import Card, ReviewAttempt, ReviewState, Topic
from src.skills.scheduler import SM2Scheduler, SupportsSM2State


@dataclass
class QuizSelectionConfig:
    """Configuration for how many cards to surface per session."""

    default_limit: int = 20


class QuizService:
    """
    In-memory selection logic for quiz cards.

    This service is intentionally DB-agnostic: it operates on collections
    of `Card` and `ReviewState` objects provided by the caller. API layers
    can fetch data from the database, call this service to choose cards,
    and then persist any changes.
    """

    def __init__(self, config: Optional[QuizSelectionConfig] = None) -> None:
        self.config = config or QuizSelectionConfig()
        self.scheduler = SM2Scheduler()

    def get_next_cards(
        self,
        *,
        user_id: int,
        cards: Sequence[Card],
        review_states: Iterable[ReviewState],
        topics: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
        now: Optional[dt.datetime] = None,
    ) -> List[Card]:
        """
        Select the next set of cards for a user.

        Strategy:
        - Prioritize cards with due `ReviewState` (due_at <= now).
        - Fill remaining slots with new cards (no ReviewState for this user).
        - Optionally filter by topic names (Topic.name).
        """
        if limit is None or limit <= 0:
            limit = self.config.default_limit

        now = now or dt.datetime.now(dt.timezone.utc)

        topic_filter = set(topics) if topics else None

        def _topic_name(card: Card) -> Optional[str]:
            topic: Optional[Topic] = getattr(card, "topic", None)
            if topic is None:
                return None
            return getattr(topic, "name", None)

        # Filter cards by topic if requested.
        # Accept either Topic.name (e.g. "cn") or Card.topic_key (e.g. "cn:core").
        filtered_cards: List[Card] = []
        for card in cards:
            if topic_filter is None:
                filtered_cards.append(card)
            else:
                name = _topic_name(card)
                topic_key = card.topic_key
                if name in topic_filter or (topic_key and topic_key in topic_filter):
                    filtered_cards.append(card)

        # Map of card_id -> ReviewState for this user.
        user_states = {rs.card_id: rs for rs in review_states if rs.user_id == user_id}

        # 1) Due cards: states with due_at <= now.
        due_cards: List[Card] = []
        due_entries = []
        for card in filtered_cards:
            state = user_states.get(card.id)
            if state and state.due_at is not None and state.due_at <= now:
                due_entries.append((state.due_at, card))

        # Sort due cards by due_at earliest first.
        for _, card in sorted(due_entries, key=lambda x: x[0]):
            due_cards.append(card)
            if len(due_cards) >= limit:
                return due_cards

        # 2) New cards: cards with no ReviewState for this user.
        new_cards: List[Card] = []
        for card in filtered_cards:
            if card.id not in user_states:
                new_cards.append(card)
                if len(due_cards) + len(new_cards) >= limit:
                    break

        return due_cards + new_cards

    def record_attempt(
        self,
        *,
        user_id: int,
        card: Card,
        review_state: Optional[ReviewState],
        quality: int,
        served_card_id: Optional[int] = None,
        response_time_ms: Optional[int] = None,
        now: Optional[dt.datetime] = None,
    ) -> tuple[ReviewState, ReviewAttempt]:
        """
        Record a quiz attempt and compute the next review state.

        This method is DB-agnostic: it creates or updates `ReviewState`
        and constructs a `ReviewAttempt`, but does not persist them.
        Callers are responsible for adding them to a session and committing.
        """
        if quality < 0 or quality > 5:
            raise ValueError("quality must be between 0 and 5")

        now = now or dt.datetime.now(dt.timezone.utc)

        state = review_state
        if state is None:
            state = ReviewState(
                user_id=user_id,
                card_id=card.id,
                repetitions=0,
                interval_days=0,
                ease_factor=self.scheduler.config.initial_ease_factor,
                due_at=None,
                last_reviewed_at=None,
                lapses=0,
            )

        # Update spaced-repetition state using SM-2.
        # ReviewState satisfies SupportsSM2State at runtime (Mapped[int] → int),
        # but static checkers can't see through SQLAlchemy descriptors.
        updated_state: ReviewState = self.scheduler.compute_next(  # type: ignore[assignment]
            cast(SupportsSM2State, state), quality=quality, now=now
        )

        attempt = ReviewAttempt(
            user_id=user_id,
            card_id=card.id,
            served_card_id=served_card_id,
            attempted_at=now,
            quality=quality,
            response_time_ms=response_time_ms,
        )

        return updated_state, attempt

    def get_stats(
        self,
        *,
        user_id: int,
        cards: Sequence[Card],
        review_states: Iterable[ReviewState],
        topics: Optional[Sequence[str]] = None,
        now: Optional[dt.datetime] = None,
    ) -> List[dict]:
        """
        Compute per-topic quiz statistics for a user.

        Returns a list of dicts with keys:
            topic, total, learned, due_today, overdue
        """
        now = now or dt.datetime.now(dt.timezone.utc)
        today = now.date()
        topic_filter = set(topics) if topics else None

        def _topic_name(card: Card) -> Optional[str]:
            topic: Optional[Topic] = getattr(card, "topic", None)
            if topic is None:
                return None
            return getattr(topic, "name", None)

        # Map card_id -> card and topic.
        card_by_id: dict[int, Card] = {}
        topic_for_card: dict[int, Optional[str]] = {}

        for card in cards:
            name = _topic_name(card)
            if topic_filter is not None and name not in topic_filter:
                continue
            card_by_id[card.id] = card
            topic_for_card[card.id] = name

        # Initialize counters.
        stats: dict[str, dict] = {}

        for card_id, card in card_by_id.items():
            topic_name = topic_for_card.get(card_id) or "unknown"
            if topic_name not in stats:
                stats[topic_name] = {
                    "topic": topic_name,
                    "total": 0,
                    "learned": 0,
                    "due_today": 0,
                    "overdue": 0,
                }
            stats[topic_name]["total"] += 1

        # Aggregate over review states for this user.
        for rs in review_states:
            if rs.user_id != user_id:
                continue
            if rs.card_id not in card_by_id:
                continue

            topic_name = topic_for_card.get(rs.card_id) or "unknown"
            entry = stats.setdefault(
                topic_name,
                {
                    "topic": topic_name,
                    "total": 0,
                    "learned": 0,
                    "due_today": 0,
                    "overdue": 0,
                },
            )

            if rs.repetitions > 0:
                entry["learned"] += 1

            if rs.due_at is None:
                continue

            due_date = rs.due_at.date()
            if due_date < today:
                entry["overdue"] += 1
            elif due_date == today:
                entry["due_today"] += 1

        return list(stats.values())
