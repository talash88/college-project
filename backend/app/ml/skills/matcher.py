"""Hybrid required-skill matching: exact phrases + semantic cosine + category bonus.

score = min(max(exact?0.95, semantic_cosine) + category_bonus(0.05), 0.99)
Keep skill iff score >= threshold. At most max_results, ranked desc.
match_type: EXACT (exact won outright), SEMANTIC, HYBRID (both fired).
Called "match/relevance score" — never "AI confidence".
"""

import math
import re
from dataclasses import dataclass, field
from uuid import UUID

from app.core.config import settings
from app.ml.skills.taxonomy import CATEGORY_SKILL_BONUS, usable_phrases


@dataclass
class SkillCandidate:
    skill_id: UUID
    skill_name: str
    skill_category: str
    semantic_score: float = 0.0
    exact_phrase: str | None = None
    category_bonus: float = 0.0
    final_score: float = 0.0
    match_type: str = "SEMANTIC"
    reason: str = ""


@dataclass
class SkillMatch:
    skill_id: UUID
    skill_name: str
    skill_category: str
    score: float
    match_type: str
    reason: str
    evidence: dict[str, object] = field(default_factory=dict)


def find_exact_phrases(text: str, skill_name: str) -> str | None:
    """First usable alias/name found with word boundaries, longest first."""
    lowered = text.lower()
    for phrase in sorted(usable_phrases(skill_name), key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", lowered):
            return phrase
    return None


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def problem_match_text(title: str, description: str, category_label: str | None = None) -> str:
    parts = [f"Title: {title.strip()}", f"Description: {description.strip()}"]
    if category_label:
        parts.append(f"Category: {category_label}.")
    return "\n".join(parts)


def category_bonus(problem_category: str | None, skill_category: str) -> float:
    if problem_category and skill_category in CATEGORY_SKILL_BONUS.get(problem_category, set()):
        return 0.05
    return 0.0


def rank_candidates(
    candidates: list[SkillCandidate],
    *,
    threshold: float | None = None,
    max_results: int | None = None,
) -> list[SkillMatch]:
    """Apply hybrid formula + threshold + cap. Pure and unit-testable."""
    limit = threshold if threshold is not None else settings.SKILL_SIMILARITY_THRESHOLD
    cap = max_results if max_results is not None else settings.SKILL_MAX_RESULTS
    matches: list[SkillMatch] = []
    for cand in candidates:
        base = 0.95 if cand.exact_phrase else cand.semantic_score
        final = min(base + cand.category_bonus, 0.99)
        if final < limit:
            continue
        if cand.exact_phrase and cand.semantic_score >= limit:
            mtype = "HYBRID"
            reason = (
                f"Direct phrase match for '{cand.exact_phrase}' "
                f"(semantic similarity {cand.semantic_score:.2f})."
            )
        elif cand.exact_phrase:
            mtype = "EXACT"
            reason = f"Direct phrase/alias match for '{cand.exact_phrase}'."
        else:
            mtype = "SEMANTIC"
            reason = f"Semantic similarity {cand.semantic_score:.2f} to the report text."
        if cand.category_bonus > 0:
            reason += " Category context supports this skill."
        cand.final_score = round(final, 4)
        cand.match_type = mtype
        cand.reason = reason
        matches.append(
            SkillMatch(
                skill_id=cand.skill_id,
                skill_name=cand.skill_name,
                skill_category=cand.skill_category,
                score=cand.final_score,
                match_type=mtype,
                reason=reason,
                evidence={
                    "semantic_score": round(cand.semantic_score, 4),
                    "exact_phrase": cand.exact_phrase,
                    "category_bonus": cand.category_bonus,
                },
            )
        )
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:cap]
