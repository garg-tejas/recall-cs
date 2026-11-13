"""Dependency-free dataset loading and evaluation-readiness checks.

Drafts may be incomplete. Retrieval benchmarks need relevance labels; answer
benchmarks need reference answers. Structural validity never implies human review.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

QUESTIONS_PATH = Path(__file__).resolve().parents[2] / "data" / "questions.jsonl"
PROFILES = ("draft", "retrieval", "answer")
PLACEHOLDER = re.compile(
    r"^(?:[\[<]\s*)?(?:(?:todo|tbd|fixme)\b|"
    r"placeholder\b|insert\s+(?:ground\s+truth\s+)?answer\b|"
    r"add\s+(?:a\s+)?(?:ground\s+truth\s+)?answer\b|your\s+answer\s+here\b)",
    re.IGNORECASE,
)


class DatasetValidationError(ValueError):
    def __init__(self, issues: list[str]):
        self.issues = issues
        shown = issues[:20]
        remaining = f"\n... and {len(issues) - 20} more issues" if len(issues) > 20 else ""
        super().__init__("Dataset is not evaluation-ready:\n" + "\n".join(f"- {issue}" for issue in shown) + remaining)


def _valid_text(value, *, allow_placeholder=False):
    return (
        isinstance(value, str) and bool(value.strip())
        and (allow_placeholder or not PLACEHOLDER.match(value.strip()))
        and value.strip().lower() not in {"...", "n/a", "null", "none", "<answer>", "[answer]"}
    )


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    """Read drafts without imposing a benchmark schema or changing the data."""
    questions, issues = [], []
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise DatasetValidationError([f"{path}: cannot read questions file ({exc.strerror or type(exc).__name__})"]) from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith(("#", "//")):
            continue
        try:
            question = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(f"{path}:{line_number}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(question, dict):
            issues.append(f"{path}:{line_number}: expected a question object")
            continue
        questions.append(question)
    if issues:
        raise DatasetValidationError(issues)
    return questions


def validate_questions(questions: list[dict], *, profile="retrieval", known_chunk_ids=None) -> None:
    """Reject unusable labels before scoring; retain a separate draft workflow."""
    if profile not in PROFILES:
        raise ValueError(f"Unknown dataset profile: {profile}")
    if known_chunk_ids is not None:
        known_chunk_ids = set(known_chunk_ids)
    issues, seen = [], set()
    if not questions:
        issues.append("dataset contains no questions")
    for index, question in enumerate(questions, 1):
        label = f"row {index}"
        if not isinstance(question, dict):
            issues.append(f"{label}: expected a question object")
            continue
        question_id = question.get("id")
        if _valid_text(question_id):
            label += f" ({question_id})"
            if question_id in seen:
                issues.append(f"{label}: duplicate id; assign a unique question ID")
            seen.add(question_id)
        else:
            issues.append(f"{label}: id must be a nonempty, non-placeholder string")
        if not _valid_text(question.get("query"), allow_placeholder=profile == "draft"):
            issues.append(f"{label}: query must contain a real question")
        if "subject" in question and question["subject"] not in ("os", "dbms", "cn"):
            issues.append(f"{label}: subject must be os, dbms, or cn")
        if "question_type" in question and question["question_type"] not in ("definition", "procedural", "comparative", "factual"):
            issues.append(f"{label}: invalid question_type")
        if profile != "draft" and ("answer" in question or profile == "answer"):
            if not _valid_text(question.get("answer")):
                issues.append(f"{label}: answer is empty or a placeholder; replace it with a reviewed reference answer")
        chunk_ids = question.get("supporting_chunk_ids")
        if profile == "retrieval" and (not isinstance(chunk_ids, list) or not chunk_ids):
            issues.append(f"{label}: supporting_chunk_ids must contain manually verified relevance labels")
        elif chunk_ids is not None:
            if not isinstance(chunk_ids, list):
                issues.append(f"{label}: supporting_chunk_ids must be a list")
            else:
                valid = [cid for cid in chunk_ids if _valid_text(cid, allow_placeholder=profile == "draft")]
                if len(valid) != len(chunk_ids):
                    issues.append(f"{label}: supporting_chunk_ids contains empty, placeholder, or non-string labels")
                if len(valid) != len(set(valid)):
                    issues.append(f"{label}: duplicate supporting_chunk_ids")
                if known_chunk_ids is not None:
                    missing = sorted(set(valid) - known_chunk_ids)
                    if missing:
                        issues.append(f"{label}: supporting chunks absent from this corpus: {', '.join(missing[:5])}")
        facts = question.get("atomic_facts")
        if facts is not None and (not isinstance(facts, list) or any(not _valid_text(fact, allow_placeholder=profile == "draft") for fact in facts)):
            issues.append(f"{label}: atomic_facts must be a list of nonempty, non-placeholder facts")
    if issues:
        raise DatasetValidationError(issues)
