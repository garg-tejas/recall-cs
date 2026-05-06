"""
Utility script for seeding quiz cards from validated QA data.

Two modes:
- Default (dry-run): summarize the validated questions file
  (counts by difficulty, question_type, and source_subject), no DB writes.
- Apply mode (--apply): create topics and cards in the PostgreSQL
  database using the validated questions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
import re
from typing import Dict, List

from sqlalchemy import select

from src.db.models import Card, Topic
from src.db.session import AsyncSessionLocal


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, *, max_len: int = 80) -> str:
    cleaned = _NON_ALNUM_RE.sub("-", text.strip().lower()).strip("-")
    if not cleaned:
        return "general"
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len].rstrip("-")


def infer_topic_key(question: Dict) -> str:
    explicit = question.get("topic_key")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()

    subject = str(question.get("subject") or question.get("source_subject") or "unknown").strip().lower()
    header = str(question.get("source_header") or "").strip()
    if header:
        tail = header.split(">")[-1].strip()
        return f"{subject}:{_slugify(tail)}"
    return f"{subject}:core"


def load_questions(path: Path) -> List[Dict]:
    questions: List[Dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            try:
                questions.append(json.loads(line))
            except json.JSONDecodeError:
                # Ignore malformed lines in dry-run mode
                continue
    return questions


def summarize_questions(questions: List[Dict]) -> None:
    total = len(questions)
    print(f"Loaded {total} questions")
    if total == 0:
        return

    by_difficulty: Counter = Counter()
    by_qtype: Counter = Counter()
    by_subject: Counter = Counter()

    for q in questions:
        by_difficulty[q.get("difficulty", "unknown")] += 1
        by_qtype[q.get("question_type", "unknown")] += 1
        subj = q.get("subject") or q.get("source_subject") or "unknown"
        by_subject[subj] += 1

    print("\nBy difficulty:")
    for diff, count in sorted(by_difficulty.items(), key=lambda x: x[0]):
        pct = (count / total) * 100
        print(f"  {diff:10s}: {count:5d} ({pct:5.1f}%)")

    print("\nBy question_type:")
    for qtype, count in sorted(by_qtype.items(), key=lambda x: x[0]):
        pct = (count / total) * 100
        print(f"  {qtype:12s}: {count:5d} ({pct:5.1f}%)")

    print("\nBy subject:")
    for subj, count in sorted(by_subject.items(), key=lambda x: x[0]):
        pct = (count / total) * 100
        print(f"  {subj:10s}: {count:5d} ({pct:5.1f}%)")


async def apply_seed(questions: List[Dict]) -> None:
    """
    Create topics and cards in the database from validated questions.
    """
    if not questions:
        print("No questions to seed.")
        return

    async with AsyncSessionLocal() as session:
        # 1) Ensure topics exist for each source_subject.
        subjects = sorted(
            {q.get("subject") or q.get("source_subject") for q in questions if q.get("subject") or q.get("source_subject")}
        )
        print(f"\nDetected subjects: {subjects or ['(none)']}")

        if subjects:
            result = await session.execute(
                select(Topic).where(Topic.name.in_(subjects))
            )
            existing_topics = {t.name: t for t in result.scalars().all()}

            created_topics = []
            for name in subjects:
                if name not in existing_topics:
                    topic = Topic(name=name, description=None)
                    session.add(topic)
                    created_topics.append(topic)

            if created_topics:
                await session.commit()
                for t in created_topics:
                    await session.refresh(t)
                existing_topics.update({t.name: t for t in created_topics})

            print(f"Topics in DB: {sorted(existing_topics.keys())}")
        else:
            existing_topics = {}
            print("No subject or source_subject found in questions; skipping topic creation.")

        # 2) Seed cards.
        inserted = 0
        skipped_existing = 0
        skipped_incomplete = 0

        for q in questions:
            subject = q.get("subject") or q.get("source_subject")
            if not subject:
                skipped_incomplete += 1
                continue

            topic = existing_topics.get(subject)
            if topic is None:
                # Should be rare if subjects were detected above.
                skipped_incomplete += 1
                continue

            question = q.get("query")
            answer = q.get("answer")
            if not question or not answer:
                skipped_incomplete += 1
                continue

            source_chunk_id = q.get("source_chunk_id")

            # Check for an existing card with same question + source_chunk_id.
            stmt = select(Card.id).where(
                Card.question == question,
                Card.source_chunk_id == source_chunk_id,
            )
            result = await session.execute(stmt)
            existing_id = result.scalar_one_or_none()
            if existing_id is not None:
                skipped_existing += 1
                continue

            card = Card(
                topic_id=topic.id,
                question=question,
                answer=answer,
                difficulty=q.get("difficulty"),
                question_type=q.get("question_type"),
                source_chunk_id=source_chunk_id,
                tags=None,
                topic_key=infer_topic_key(q),
                generation_origin="seed",
                provenance_json={
                    "source": "validated_seed",
                    "source_header": q.get("source_header"),
                    "source_subject": q.get("subject") or q.get("source_subject"),
                    "quality_score": q.get("quality_score"),
                },
                atomic_facts=q.get("atomic_facts"),
            )
            session.add(card)
            inserted += 1

            # Flush periodically to keep memory usage reasonable.
            if inserted % 500 == 0:
                await session.flush()

        if inserted > 0:
            await session.commit()

    print("\nSeeding complete.")
    print(f"  Inserted cards:        {inserted}")
    print(f"  Skipped existing:      {skipped_existing}")
    print(f"  Skipped incomplete:    {skipped_incomplete}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize or seed quiz cards from a validated QA JSONL file.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("eval/generation/output/generated_questions.validated.jsonl"),
        help="Path to validated questions JSONL file",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to the database (create topics and cards). Without this flag, runs in dry-run mode.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}")
        return

    print(f"Loading validated questions from {args.input}...")
    questions = load_questions(args.input)
    summarize_questions(questions)

    if not args.apply:
        print("\nDry run complete. No database changes were made.")
        return

    print("\nApply mode enabled: seeding topics and cards into the database...")
    asyncio.run(apply_seed(questions))


if __name__ == "__main__":
    main()
