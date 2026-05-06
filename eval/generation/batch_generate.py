"""
Batch processing CLI for generating QA pairs from chunks using an OpenAI-compatible API (Z.AI/GLM, ModelScope, etc.).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import List, Optional

from src.llm.client import create_client
from src.rag.index import ChunkRecord, load_chunks

from .chunk_selector import select_chunks_for_generation
from .generate_qa import generate_questions_batch

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = ROOT / "eval" / "generation" / "output"


def filter_chunks_for_generation(
    chunks: List[ChunkRecord],
    subject: Optional[str] = None,
    chunk_types: Optional[List[str]] = None,
) -> List[ChunkRecord]:
    """
    Filter chunks suitable for question generation.

    Excludes exercise, references, etc. Focuses on definition, algorithm, section, protocol.
    """
    if chunk_types is None:
        chunk_types = ["definition", "algorithm", "section", "protocol"]

    filtered = []
    excluded_types = {"exercise", "references", "bibliography", "citations"}
    excluded_headers = {
        "appendix",
        "exercises",
        "review questions",
        "selected bibliography",
    }

    for chunk in chunks:
        if chunk.chunk_type in excluded_types:
            continue

        header_lower = chunk.header_path.lower()
        if any(marker in header_lower for marker in excluded_headers):
            continue

        if chunk_types and chunk.chunk_type not in chunk_types:
            continue

        if subject:
            inferred = chunk.subject or _infer_subject_simple(chunk)
            if inferred != subject:
                continue

        filtered.append(chunk)

    return filtered


def _infer_subject_simple(chunk: ChunkRecord) -> str:
    """Simple subject inference."""
    from .generate_qa import _infer_subject

    return _infer_subject(chunk)


def load_processed_chunk_ids(checkpoint_path: Path) -> set[str]:
    """Load set of chunk IDs that already have questions in the checkpoint (for resume)."""
    if not checkpoint_path.exists():
        return set()
    seen: set[str] = set()
    with checkpoint_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                q = json.loads(line)
                cid = q.get("source_chunk_id")
                if cid:
                    seen.add(cid)
            except json.JSONDecodeError:
                continue
    return seen


def load_existing_questions(checkpoint_path: Path) -> List[dict]:
    """Load all questions from checkpoint (for appending new batch)."""
    if not checkpoint_path.exists():
        return []
    existing: List[dict] = []
    with checkpoint_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    existing.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return existing


def save_checkpoint(checkpoint_path: Path, all_questions: List[dict]) -> None:
    """Write full question list to checkpoint (overwrite)."""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("w", encoding="utf-8") as f:
        f.write("// Generated questions checkpoint\n")
        for q in all_questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"  Checkpoint saved: {len(all_questions)} total questions")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate QA pairs from textbook chunks (Z.AI/GLM, ModelScope, or other OpenAI-compatible API)."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (default: LLM_MODEL or MODELSCOPE_MODEL env var, e.g. glm-4.7-flash)",
    )
    parser.add_argument(
        "--modelscope-token",
        type=str,
        default=None,
        help="API key (or set LLM_API_KEY / MODELSCOPE_API_TOKEN env var)",
    )
    parser.add_argument(
        "--subject",
        choices=["os", "dbms", "cn"],
        help="Filter chunks by subject",
    )
    parser.add_argument(
        "--questions-per-chunk",
        type=int,
        default=2,
        help="Number of questions to generate per chunk (default: 2)",
    )
    parser.add_argument(
        "--chunk-types",
        nargs="+",
        default=["definition", "algorithm", "section", "protocol"],
        help="Chunk types to include (default: definition algorithm section protocol)",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Maximum number of chunks to process (for testing)",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=OUTPUT_DIR / "generated_questions.jsonl",
        help="Checkpoint file path",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Number of chunks to process before saving checkpoint (default: 5 to avoid concurrency limits)",
    )
    parser.add_argument(
        "--batch-delay",
        type=float,
        default=0,
        help="Seconds to wait between batches (default: 0; use e.g. 45 for strict rate limits)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=85,
        help="Minimum quality score (0-100) to keep questions (default: 85)",
    )
    parser.add_argument(
        "--quality-mode",
        choices=["deterministic", "llm_hybrid", "llm_only"],
        default="llm_only",
        help=(
            "Quality filtering mode: deterministic (fast), llm_hybrid (balanced), "
            "llm_only (strict LLM gate)"
        ),
    )
    parser.add_argument(
        "--no-llm-rewrite",
        action="store_true",
        help="Disable LLM rewrite of borderline questions during review",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Start from scratch: delete existing checkpoint if present (no resume)",
    )

    args = parser.parse_args()

    if args.reset and args.checkpoint.exists():
        args.checkpoint.unlink()
        print(f"Reset: removed existing checkpoint {args.checkpoint}")

    print("Loading chunks...")
    all_chunks = load_chunks(subject=args.subject)

    print(f"Filtering chunks...")
    filtered_chunks = filter_chunks_for_generation(
        all_chunks,
        subject=args.subject,
        chunk_types=args.chunk_types,
    )

    if not filtered_chunks:
        print("No chunks to process. Adjust filters.")
        return

    # Resume: skip chunks already in checkpoint (unless --reset)
    processed_ids: set[str] = set()
    if not args.reset and args.checkpoint.exists():
        processed_ids = load_processed_chunk_ids(args.checkpoint)
        if processed_ids:
            before = len(filtered_chunks)
            filtered_chunks = [c for c in filtered_chunks if c.id not in processed_ids]
            print(
                f"Resuming: {len(processed_ids)} chunks already in checkpoint, {len(filtered_chunks)} remaining"
            )
            if not filtered_chunks:
                print("Nothing left to process. Use --reset to start over.")
                return

    # Apply scoring and topic-diverse selection.
    target_count = args.max_chunks or len(filtered_chunks)
    print(
        f"Scoring {len(filtered_chunks)} chunks for QA potential and selecting "
        f"{target_count} with topic diversity..."
    )
    filtered_chunks = select_chunks_for_generation(
        filtered_chunks,
        target_count=target_count,
    )

    total_to_process = len(filtered_chunks)
    print(f"Chunks to process this run: {total_to_process}")
    print(f"Expected new questions: ~{total_to_process * args.questions_per_chunk}")

    print("\nInitializing LLM client...")
    try:
        llm_client = create_client(
            model_name=args.model,
            modelscope_token=args.modelscope_token,
        )
        calls_per_chunk = 1 + (
            1 if args.quality_mode in {"llm_hybrid", "llm_only"} else 0
        )
        print(f"Using model: {llm_client.model_name} ({llm_client.base_url})")
        print(
            "Estimated calls: "
            f"~{len(filtered_chunks) * calls_per_chunk} "
            f"({calls_per_chunk} call(s) per chunk with quality_mode={args.quality_mode})"
        )
    except Exception as e:
        print(f"Error initializing client: {e}")
        print("\nMake sure openai is installed: uv pip install openai")
        print("\nSet API key (Z.AI/GLM): LLM_BASE_URL, LLM_API_KEY, LLM_MODEL in .env")
        print("  Or ModelScope: MODELSCOPE_API_TOKEN (and optionally MODELSCOPE_MODEL)")
        return

    print("\nGenerating questions...")
    print("=" * 60)
    print(f"Quality mode: {args.quality_mode} (min score {args.min_score})")
    if args.quality_mode in {"llm_hybrid", "llm_only"}:
        print(f"LLM rewrite: {'disabled' if args.no_llm_rewrite else 'enabled'}")

    all_questions: List[dict] = (
        load_existing_questions(args.checkpoint)
        if (args.checkpoint.exists() and not args.reset)
        else []
    )
    processed_this_run = 0

    for i in range(0, len(filtered_chunks), args.batch_size):
        batch = filtered_chunks[i : i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(filtered_chunks) + args.batch_size - 1) // args.batch_size

        print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} chunks)...")

        try:
            batch_questions = generate_questions_batch(
                batch,
                llm_client,
                questions_per_chunk=args.questions_per_chunk,
                min_score=args.min_score,
                quality_mode=args.quality_mode,
                llm_allow_rewrite=not args.no_llm_rewrite,
            )
            all_questions.extend(batch_questions)
            processed_this_run += len(batch)

            print(
                f"  Generated {len(batch_questions)} questions from {len(batch)} chunks"
            )
            if len(batch_questions) == 0:
                print(
                    f"  Warning: No questions generated. Check LLM responses and parsing logic."
                )

            save_checkpoint(args.checkpoint, all_questions)

            # Delay between batches to avoid rate limits
            if i + args.batch_size < len(filtered_chunks):
                delay = args.batch_delay
                print(f"  Waiting {delay:.1f}s before next batch...")
                time.sleep(delay)

        except KeyboardInterrupt:
            print("\n  Paused by user (Ctrl+C). Run the same command again to resume.")
            save_checkpoint(args.checkpoint, all_questions)
            return
        except Exception as e:
            print(f"  Error processing batch: {e}")
            print("  Continuing with next batch...")
            continue

    print("\n" + "=" * 60)
    print(f"Generation complete!")
    print(f"  Processed this run: {processed_this_run} chunks")
    print(f"  Total questions in checkpoint: {len(all_questions)}")
    print(f"  Output: {args.checkpoint}")

    if all_questions:
        print("\nNext steps:")
        print("  1. Review generated questions:")
        print(f"     cat {args.checkpoint}")
        print("  2. Validate and filter:")
        print("     uv run python -m eval.generation.validate_qa", args.checkpoint)
        print("  3. Import into questions.jsonl:")
        print(
            "     uv run python -m eval.dataset.build_questions import-from-llm",
            args.checkpoint,
        )


if __name__ == "__main__":
    main()
