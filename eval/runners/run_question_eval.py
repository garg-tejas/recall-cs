"""
Evaluation runner for questions.jsonl dataset.

Computes retrieval metrics (Precision@k, Recall@k, MRR) and prepares
structure for future model inference evaluation.

Usage:
    uv run python -m eval.runners.run_question_eval
    uv run python -m eval.runners.run_question_eval --subject os
    uv run python -m eval.runners.run_question_eval --top-k 10
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, TYPE_CHECKING

from eval.dataset.validation import (
    DatasetValidationError, QUESTIONS_PATH, load_questions, validate_questions,
)
if TYPE_CHECKING:
    from src.rag import HybridSearcher

ROOT = Path(__file__).resolve().parents[2]


def compute_retrieval_metrics(
    retrieved_chunk_ids: List[str],
    ground_truth_chunk_ids: List[str],
    k: int = 5,
) -> Dict[str, float]:
    """
    Compute retrieval metrics for a single question.
    
    Returns:
        {
            "precision@k": float,
            "recall@k": float,
            "mrr": float,
        }
    """
    if k < 1:
        raise ValueError("k must be positive")
    validate_questions([{"id": "metric_input", "query": "Retrieval labels", "supporting_chunk_ids": ground_truth_chunk_ids}])
    if len(retrieved_chunk_ids) != len(set(retrieved_chunk_ids)):
        raise ValueError("Retrieved chunk IDs must be unique before computing retrieval metrics")
    
    ground_truth_set = set(ground_truth_chunk_ids)
    top_k_retrieved = retrieved_chunk_ids[:k]
    
    # Precision@k: fraction of retrieved that are relevant
    relevant_retrieved = sum(1 for cid in top_k_retrieved if cid in ground_truth_set)
    precision = relevant_retrieved / len(top_k_retrieved) if top_k_retrieved else 0.0
    
    # Recall@k: fraction of ground truth that were retrieved
    recall = relevant_retrieved / len(ground_truth_set) if ground_truth_set else 0.0
    
    # MRR: reciprocal rank of first relevant result
    mrr = 0.0
    for rank, cid in enumerate(retrieved_chunk_ids, 1):
        if cid in ground_truth_set:
            mrr = 1.0 / rank
            break
    
    return {
        f"precision@{k}": precision,
        f"recall@{k}": recall,
        "mrr": mrr,
    }


def evaluate_question(
    question: Dict,
    searcher: HybridSearcher,
    top_k: int = 5,
) -> Dict:
    """Evaluate a single question and return metrics."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    validate_questions([question], profile="retrieval")
    query = question["query"]
    ground_truth_chunk_ids = question.get("supporting_chunk_ids", [])
    
    # Run retrieval
    results = searcher.search_raw(query, top_k=top_k * 2)  # Get more for better recall
    retrieved_chunk_ids = [chunk.id for chunk, _score in results[:top_k * 2]]
    
    # Compute metrics
    metrics = compute_retrieval_metrics(
        retrieved_chunk_ids, ground_truth_chunk_ids, k=top_k
    )
    
    return {
        "question_id": question["id"],
        "query": query,
        "retrieved_count": len(retrieved_chunk_ids),
        "ground_truth_count": len(ground_truth_chunk_ids),
        "metrics": metrics,
        "retrieved_chunk_ids": retrieved_chunk_ids[:top_k],
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate questions dataset with retrieval metrics."
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Top-k for precision/recall metrics (default: 5)",
    )
    parser.add_argument(
        "--subject",
        choices=["os", "dbms", "cn"],
        help="Filter questions by subject",
    )
    parser.add_argument(
        "--questions-file",
        type=Path,
        default=QUESTIONS_PATH,
        help="Path to questions.jsonl file",
    )

    parser.add_argument("--validate-only", action="store_true", help="Check structural evaluation readiness without loading retrieval models")
    args = parser.parse_args(argv)
    if args.top_k < 1:
        parser.error("--top-k must be positive")

    # Load questions
    try:
        questions = load_questions(args.questions_file)
    except DatasetValidationError as exc:
        parser.error(str(exc))

    # Filter by subject if requested
    if args.subject:
        questions = [q for q in questions if q.get("subject") == args.subject]

    try:
        validate_questions(questions, profile="retrieval")
    except DatasetValidationError as exc:
        parser.error(str(exc))
    if args.validate_only:
        print(f"Validated {len(questions)} retrieval questions structurally. Human review and corpus label checks are still required.")
        return

    print(f"Evaluating {len(questions)} questions (top_k={args.top_k})...")
    print("=" * 60)

    # Load searcher
    from src.rag import HybridSearcher, load_chunks

    chunks = load_chunks()
    try:
        validate_questions(questions, profile="retrieval", known_chunk_ids={chunk.id for chunk in chunks})
    except DatasetValidationError as exc:
        parser.error(str(exc))
    searcher = HybridSearcher.from_chunks(chunks, use_reranker=True)

    # Evaluate each question
    all_results = []
    for question in questions:
        result = evaluate_question(question, searcher, top_k=args.top_k)
        all_results.append(result)

        # Print per-question results
        print(f"\n[{result['question_id']}] {result['query']}")
        print(f"  Retrieved: {result['retrieved_count']} chunks")
        print(f"  Ground truth: {result['ground_truth_count']} chunks")
        if result['ground_truth_count'] > 0:
            print(f"  Precision@{args.top_k}: {result['metrics'][f'precision@{args.top_k}']:.3f}")
            print(f"  Recall@{args.top_k}: {result['metrics'][f'recall@{args.top_k}']:.3f}")
            print(f"  MRR: {result['metrics']['mrr']:.3f}")
        else:
            print("  (No ground truth chunks linked - skipping metrics)")

    # Aggregate metrics
    questions_with_gt = [r for r in all_results if r["ground_truth_count"] > 0]
    if questions_with_gt:
        avg_precision = sum(
            r["metrics"][f"precision@{args.top_k}"] for r in questions_with_gt
        ) / len(questions_with_gt)
        avg_recall = sum(
            r["metrics"][f"recall@{args.top_k}"] for r in questions_with_gt
        ) / len(questions_with_gt)
        avg_mrr = sum(r["metrics"]["mrr"] for r in questions_with_gt) / len(
            questions_with_gt
        )

        print("\n" + "=" * 60)
        print("AGGREGATED METRICS")
        print("=" * 60)
        print(f"Questions evaluated: {len(questions_with_gt)}/{len(all_results)}")
        print(f"Avg Precision@{args.top_k}: {avg_precision:.3f}")
        print(f"Avg Recall@{args.top_k}: {avg_recall:.3f}")
        print(f"Avg MRR: {avg_mrr:.3f}")
    else:
        print("\nNo questions with ground truth chunks found.")
        print("Link chunks using: uv run python -m eval.dataset.build_questions link <question_id>")


if __name__ == "__main__":
    main()
