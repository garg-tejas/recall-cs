# Recall.cs

Recall.cs is a full-stack CS interview prep system for OS, DBMS, and Computer Networks. It combines a hybrid RAG assistant with an adaptive quiz engine — you can ask conceptual questions backed by textbook retrieval, and practice recall on a spaced repetition schedule that adapts to your performance.

## Problem

Most interview prep workflows are disconnected:

- Static notes with no retrieval support
- Random question banks with no memory model
- No signal-driven way to prioritize what to study next

This creates two concrete gaps: you can read a lot without closing weak topic gaps, and you can answer questions once but still forget them because review timing isn't adaptive.

The engineering challenge was building a system where retrieval quality, grading reliability, and scheduling all work together without any one component becoming a bottleneck.

## Approach

The core architecture has three coupled layers:

1. **Retrieval** — hybrid BM25 + dense search with RRF fusion, intent-aware scoring, and optional cross-encoder reranking. Retrieval quality depends less on any single retriever and more on careful fusion, filtering, and reranking.
2. **Evaluation** — an offline generation pipeline that produces, grades, and validates question/answer pairs before they ever reach the quiz engine. An LLM grader assigns 0–5 quality scores with rubric-aware feedback during live sessions.
3. **Scheduling** — SM-2 spaced repetition driven by grader output, layered with a prerequisite-aware learning path that combines graph constraints (topological ordering) with personalized signals (mastery + SWOT buckets).

The backend is FastAPI + async SQLAlchemy on PostgreSQL. Frontend is React 18 + TypeScript + Vite. LLM calls go through an OpenAI-compatible client layer pointed at GLM via Z.AI.

![Architecture](assets/architecture.png)

## Iterations

**Retrieval**

Started with pure dense retrieval using `all-MiniLM-L6-v2`. Results were reasonable for factual queries but poor on definition-seeking questions — chunks about "what X is" weren't ranking above procedural chunks. Added BM25 as a sparse layer and fused scores with RRF. That improved recall significantly. The next issue was noise: reference sections, exercise chunks, and bibliography-style content were surfacing in results. Added a noise filter pass before final ranking. Last addition was intent detection — boosting definition chunks 1.5× for definition queries, penalizing negating chunks 0.25× — which had an outsized impact for a small amount of code.

**Grading pipeline**

Early grading attempts failed about 12% of the time from malformed LLM JSON output. Added retry logic with schema validation, which brought failures under 1%. This was the clearest lesson about using LLMs in pipelines: you can't treat LLM output as reliable until you've added parsing guards and fallback behavior throughout.

**Learning path**

First version was pure topological ordering of prerequisites. That gave a logical order but ignored what the user actually knew. Added per-topic mastery signals and SWOT buckets (weakness/threat/opportunity/strength) that shift priority scores on top of the topological order. Topics the user scores poorly on get a +28 deficit bonus; topics with solid mastery get +4. The combination of graph constraints and personalized signals makes the path meaningfully different per user.

**Offline generation**

Originally generated questions on-demand during sessions, which created latency spikes and meant low-quality variants sometimes reached users. Moved to an offline pipeline: generate → score → validate → seed. Only variants that pass a quality gate get persisted. This made session startup fast and kept the question pool consistently high quality.

## Key Design Choices

**Hybrid retrieval over pure vector search** — BM25 captures exact-match signals that dense retrieval misses, especially for acronyms and technical terms common in CS topics. RRF fusion with `k=60` is a stable default that doesn't require tuning per-query.

**Offline generation pipeline** — separating content creation from serving means the quiz engine never blocks on LLM calls. The pipeline runs once; the session serves from validated, pre-scored artifacts.

**SM-2 with proportional interval reset on lapse** — standard SM-2 resets interval to 1 on failure regardless of prior history. Implemented a proportional reset (`max(1, min(interval // 2, 7))`) so a card at interval 30 resets to 7, not 1. This avoids over-drilling cards that are mostly stable.

**Cross-encoder reranking as optional second stage** — adds latency but improves precision meaningfully on ambiguous queries. Made it configurable so it can be toggled off for lower-latency use cases.

**OpenAI-compatible client layer** — abstracts the LLM provider behind a standard interface. Switching from GLM to any OpenAI-compatible endpoint requires changing one config value.

## Technical Highlights

### Hybrid Retrieval Internals

- Sparse: `rank_bm25` over tokenized chunk text
- Dense: `sentence-transformers` embeddings (`all-MiniLM-L6-v2`)
- Fusion: Reciprocal Rank Fusion (`1 / (k_rrf + rank)`, default `k_rrf=60`)
- Candidate depth: `candidate_k=max(top_k*3, config.candidate_k)` (default `top_k=5`, `candidate_k=20`)
- Intent-aware scoring: definition chunks boosted 1.5× for definition queries; negating chunks penalized 0.25×; procedural/comparative intents apply smaller type-aware boosts
- Noise filtering: reference/exercise/bibliography chunks removed before final ranking
- Optional second-stage reranking: cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) with blended score

### Spaced Repetition (SM-2)

- Input: LLM grader outputs `quality` in `[0, 5]`
- Failure (`quality < 3`): repetitions reset to 0; interval proportionally reset `max(1, min(interval // 2, 7))`; lapses increment
- Success (`quality >= 3`): ease factor updated with classic SM-2 delta; floor at `min_ease_factor=1.3`; interval progression: 1 → 6 → `round(interval * EF)`
- State update writes `due_at`, `last_reviewed_at`, `interval_days`, `repetitions`, `ease_factor`, `lapses`

### Learning Path

- Priority scoring: `deficit = max(0, 100 - mastery_score)` + SWOT bucket bonus (weakness +28, threat +22, opportunity +14, strength +4)
- Ordering: prerequisite-aware topological sort, ties broken by priority, cycle fallback appends remaining nodes by priority
- Session serving ranks selected cards by `topic_key → path_rank`

### Offline Generation Pipeline

- Two-pass topic graph build: candidate extraction → edge validation (keep/drop + confidence score)
- Rule filtering removes self-loops, missing-topic edges, duplicates, and low-confidence edges
- Cycle breaking drops the lowest-confidence edge in detected cycles
- Question generation → LLM scoring → schema validation → seed script; only validated variants are persisted

## Tech Stack

- **Retrieval/LLM**: `rank-bm25`, `sentence-transformers`, OpenAI-compatible client (Z.AI/GLM)
- **Backend**: Python 3.12, FastAPI, Uvicorn, SQLAlchemy async + AsyncPG, Alembic, Pydantic v2
- **Storage**: PostgreSQL (users, cards, review state, attempts, mastery, SWOT, taxonomy, prerequisites)
- **Frontend**: React 18 + TypeScript, Vite, React Router
- **Tooling**: `uv`, Pytest

## Project Structure

```text
src/       API, auth, DB models, RAG pipeline, quiz/session logic
eval/      Question generation, scoring, validation
scripts/   Chunking, seeding, graph build/sync
frontend/  React SPA (dashboard, setup, path preview, review flow)
docs/      Architecture and setup guides
tests/     Backend test suite
```

## Quick Start

1. Configure `.env` (Postgres, OpenAI-compatible API key, JWT secret)
2. Run migrations: `uv run alembic upgrade head`
3. Generate questions: `uv run python -m eval.generation.batch_generate --subject os`
4. Seed cards: `uv run python -m scripts.seed_cards --input <validated_jsonl> --apply`
5. Sync topic graph: `uv run python -m scripts.sync_topic_dependency_graph --subject os --replace-subject`
6. Start backend: `uv run uvicorn src.api.main:app --reload`
7. Start frontend: `cd frontend && pnpm dev`

See `docs/SETUP.md` for full setup instructions.

## Daily Time Commitment

This project was built in focused bursts rather than fixed daily hours — roughly
3–4 heavy sessions per week averaging 4–6 hours each.

## Limitations

- Covers OS, DBMS, and Computer Networks only — no algorithms, systems design, or ML topics yet
- LLM grading can be inconsistent on very short or off-topic answers
- Learning path assumes acyclic prerequisite chains; circular concept dependencies fall back to priority-only ordering
- Single-user focus; no multi-user collaboration or shared study paths
