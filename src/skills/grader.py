from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.llm import create_client

logger = logging.getLogger(__name__)

# Module-level singleton to avoid recreating the LLM client on every call
_grader_client = None


def _get_grader_client():
    global _grader_client
    if _grader_client is None:
        _grader_client = create_client()
    return _grader_client


@dataclass
class GradeResult:
    score_0_5: int
    verdict: str
    missing_points: list[str]
    incorrect_points: list[str]
    concept_summary: str
    where_you_missed: list[str]
    should_remediate: bool


def _normalize_verdict(raw_verdict: str, *, score: int) -> str:
    normalized = raw_verdict.strip().lower().replace("-", "_").replace(" ", "_")
    if "partial" in normalized:
        return "partially_correct"
    if "incorrect" in normalized or "wrong" in normalized:
        return "incorrect"
    if normalized == "correct":
        return "correct"
    if score >= 5:
        return "correct"
    if score >= 3:
        return "partially_correct"
    return "incorrect"


def _extract_json(raw: str) -> str:
    """Strip markdown fences and return the inner JSON string."""
    raw = raw.strip()
    if raw.startswith("```"):
        # Remove opening fence (``` or ```json)
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    if raw.endswith("```"):
        raw = raw.rsplit("\n", 1)[0]
    return raw.strip()


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


_QUESTION_TYPE_RUBRICS: Dict[str, str] = {
    "definition": """Question type: Definition
Evaluation focus:
- Does the answer identify the core concept accurately?
- Does it mention why the concept matters (purpose/motivation)?
- Does it cover edge cases, failure implications, or trade-offs where relevant?
- Deduct for superficial one-line answers that omit practical significance.""",
    "procedural": """Question type: Procedural
Evaluation focus:
- Does the answer describe the correct sequence of steps or mechanism?
- Are edge cases and error handling mentioned where appropriate?
- Is the complexity (time/space) or practical constraints addressed?
- Deduct for listing steps without explaining why each step matters.""",
    "comparative": """Question type: Comparative
Evaluation focus:
- Does the answer clearly identify both items being compared?
- Are specific dimensions of comparison stated (performance, use-case, trade-offs)?
- Is there a clear conclusion about when to prefer each option?
- Deduct for vague or one-sided comparisons.""",
    "factual": """Question type: Factual
Evaluation focus:
- Is the stated fact correct and precise?
- Are relevant qualifications or conditions mentioned?
- Deduct for overly broad or imprecise statements that could mislead.""",
}


def _build_prompt(
    *,
    question: str,
    reference_answer: str,
    user_answer: str,
    subject: Optional[str] = None,
    context_excerpt: Optional[str] = None,
    question_type: Optional[str] = None,
    atomic_facts: Optional[list[str]] = None,
) -> str:
    subj = (
        subject
        or "computer science (operating systems, databases, or computer networks)"
    )

    parts = [
        f"You are grading a short-answer question in {subj}.",
        "",
        "You are given:",
        "- The question.",
        "- A reference answer that reflects the key ideas.",
        "- The user's answer.",
    ]
    if context_excerpt:
        parts.append("- An optional context excerpt from the source material.")

    if atomic_facts:
        parts.append("")
        parts.append("Key facts the answer should cover:")
        for fact in atomic_facts:
            parts.append(f"- {fact}")
        parts.append("")

    qtype_rubric = _QUESTION_TYPE_RUBRICS.get((question_type or "").strip().lower(), "")
    if qtype_rubric:
        parts.append(qtype_rubric)
        parts.append("")

    parts.append(
        """
Your task is to compare the user's answer to the reference answer and decide how well it captures the key ideas.

Score the answer from 0 to 5 as follows:
- 5: Completely correct. All key ideas are present and accurate.
- 4: Mostly correct. One minor idea missing or slightly inaccurate.
- 3: Partially correct. Some important ideas are missing or unclear.
- 2: Significant misunderstanding or major omissions.
- 1: Barely correct. Only a small hint of the right idea.
- 0: Entirely incorrect or off-topic.

Be strict but fair. Focus on conceptual correctness rather than exact wording.

Respond with a single JSON object with this structure:
{
  "score_0_5": <integer from 0 to 5>,
  "verdict": "correct" | "partially_correct" | "incorrect",
  "missing_points": ["..."],
  "incorrect_points": ["..."],
  "concept_summary": "<1-2 sentences max. Explain the core concept clearly if answer is partial/incorrect; use empty string when correct.>",
  "where_you_missed": ["<1-2 concise, concrete misses only when partial/incorrect>"],
  "should_remediate": <true when partial/incorrect, false when correct>
}

Rules:
- Be strict but fair. Do not nitpick minor wording differences.
- Only point out real conceptual misses; do not invent faults.
- Keep output concise and actionable. Brevity is critical — stay under ~300 tokens.

Do not include any explanation outside the JSON. The JSON must be the only content in your reply.
"""
    )

    parts.append("Question:")
    parts.append(question.strip())
    parts.append("")

    parts.append("Reference answer:")
    parts.append(reference_answer.strip())
    parts.append("")

    if context_excerpt:
        parts.append("Context excerpt:")
        parts.append(context_excerpt.strip())
        parts.append("")

    parts.append("User answer:")
    parts.append(user_answer.strip())
    parts.append("")
    parts.append("JSON:")

    return "\n".join(parts)


def grade_answer(
    *,
    question: str,
    reference_answer: str,
    user_answer: str,
    subject: Optional[str] = None,
    context_excerpt: Optional[str] = None,
    question_type: Optional[str] = None,
    atomic_facts: Optional[list[str]] = None,
) -> GradeResult:
    """
    Grade a user's answer using the configured LLM client.

    Returns a GradeResult with a 0-5 score suitable for SM-2.
    On LLM/parse failure returns verdict='grading_error' with score=-1.
    """
    prompt = _build_prompt(
        question=question,
        reference_answer=reference_answer,
        user_answer=user_answer,
        subject=subject,
        context_excerpt=context_excerpt,
        question_type=question_type,
        atomic_facts=atomic_facts,
    )

    client = _get_grader_client()
    raw = client.generate_single(
        prompt,
        max_tokens=4096,
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    score = 3
    verdict = "partially_correct"
    missing: list[str] = []
    incorrect: list[str] = []
    concept_summary = ""
    where_you_missed: list[str] = []
    should_remediate = True

    try:
        data: Dict[str, Any] = json.loads(_extract_json(raw))
        score = int(data.get("score_0_5", score))
        score = max(0, min(5, score))
        verdict = str(data.get("verdict", verdict))
        missing = _coerce_string_list(data.get("missing_points", missing))
        incorrect = _coerce_string_list(data.get("incorrect_points", incorrect))
        concept_summary = str(data.get("concept_summary", concept_summary)).strip()
        where_you_missed = _coerce_string_list(
            data.get("where_you_missed", where_you_missed)
        )
        should_value = data.get("should_remediate", should_remediate)
        if isinstance(should_value, bool):
            should_remediate = should_value
    except Exception:
        logger.warning("Grader JSON parse failed, raw=%s", raw[:200])
        return GradeResult(
            score_0_5=-1,
            verdict="grading_error",
            missing_points=[],
            incorrect_points=[],
            concept_summary="",
            where_you_missed=[],
            should_remediate=False,
        )

    verdict = _normalize_verdict(verdict, score=score)
    should_remediate = verdict != "correct"
    if not should_remediate:
        concept_summary = ""
        where_you_missed = []
    else:
        if not concept_summary:
            concept_summary = "Your answer is partly aligned, but it misses key concepts from the reference answer."
        if not where_you_missed:
            combined = [*incorrect, *missing]
            where_you_missed = combined[:3]
        if not where_you_missed:
            where_you_missed = [
                "Your answer missed key concepts needed for a complete explanation."
            ]

    return GradeResult(
        score_0_5=score,
        verdict=verdict,
        missing_points=missing,
        incorrect_points=incorrect,
        concept_summary=concept_summary,
        where_you_missed=where_you_missed,
        should_remediate=should_remediate,
    )
