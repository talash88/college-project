"""Deterministic mentor-scoring math for Step 8 (pure, no DB).

Semantic similarity comes from the existing Sentence Transformer (computed in
the service layer); everything else here is transparent arithmetic over
UserSkill rows, category tokens, availability, and workload.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ml.recommendations.scoring import (
    RequiredSkillInput,
    SolverInput,
    SolverSkillInput,
    best_match_for_skill,
    proficiency_label,
    spare_fraction,
)

# Generic tokens ignored for category/domain overlap (too common to mean a fit).
GENERIC_TOKENS = frozenset(
    {
        "and",
        "or",
        "of",
        "the",
        "for",
        "with",
        "systems",
        "system",
        "engineering",
        "computer",
        "science",
        "department",
        "college",
        "campus",
    }
)


@dataclass(frozen=True)
class MentorSkillInput:
    skill_id: str
    name: str
    proficiency: int  # 1-5
    is_verified: bool
    category: str | None = None


@dataclass(frozen=True)
class MentorInput:
    user_id: str
    name: str
    availability: str  # AVAILABLE | LIMITED (UNAVAILABLE never reaches here)
    current_workload: int
    max_workload: int
    department: str | None = None
    designation: str | None = None
    specialization: str | None = None
    skills: tuple[MentorSkillInput, ...] = ()


@dataclass
class MentorSkillDetail:
    required_skill_id: str
    required_skill_name: str
    relevance: float
    match_kind: str  # EXACT | CATEGORY | NONE
    proficiency: int | None
    proficiency_label: str | None
    strength: float


@dataclass
class MentorScore:
    total: float
    specialization: float  # weighted contributions
    skill: float
    category: float
    availability: float
    workload: float
    semantic_similarity: float  # raw 0-1, stored separately too
    skill_details: list[MentorSkillDetail] = field(default_factory=list)


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in GENERIC_TOKENS}


def category_overlap(category: str | None, specialization: str | None, department: str | None) -> float:
    """Recall of category tokens in the mentor's domain tokens.

    Tokens match on equality or affix (so "network" matches "networks");
    generic tokens are ignored on both sides.
    """
    cat_tokens = _tokens(category.replace("_", " ") if category else None)
    mentor_tokens = _tokens(specialization) | _tokens(department)
    if not cat_tokens or not mentor_tokens:
        return 0.0
    matched = {c for c in cat_tokens if any(_token_match(c, m) for m in mentor_tokens)}
    return len(matched) / len(cat_tokens)


def _token_match(category_token: str, mentor_token: str) -> bool:
    if category_token == mentor_token:
        return True
    if len(category_token) < 3 or len(mentor_token) < 3:
        return False
    return mentor_token.startswith(category_token) or mentor_token.endswith(category_token)


def mentor_text(mentor: MentorInput) -> str:
    """Textual mentor representation for semantic matching."""
    parts = []
    if mentor.specialization:
        parts.append(f"Specialization: {mentor.specialization.strip()}")
    if mentor.skills:
        parts.append("Skills: " + ", ".join(s.name for s in mentor.skills))
    if mentor.department:
        parts.append(f"Department: {mentor.department.strip()}")
    if mentor.designation:
        parts.append(f"Designation: {mentor.designation.strip()}")
    return "\n".join(parts)


def problem_text_for_mentor(
    title: str, description: str, category: str | None, required_skill_names: list[str]
) -> str:
    """Textual problem representation for semantic matching."""
    parts = [f"Title: {title.strip()}", f"Description: {description.strip()}"]
    if category:
        parts.append(f"Category: {category.strip()}")
    if required_skill_names:
        parts.append("Required skills: " + ", ".join(required_skill_names))
    return "\n".join(parts)


def skill_match_fraction(
    mentor: MentorInput, required: tuple[RequiredSkillInput, ...]
) -> tuple[float, list[MentorSkillDetail]]:
    """Relevance-weighted best proficiency factors over the mentor's skills."""
    relevance_total = 0.0
    weighted = 0.0
    details: list[MentorSkillDetail] = []
    for req in required:
        relevance = max(0.0, min(1.0, req.relevance))
        relevance_total += relevance
        best_strength = 0.0
        best_kind = "NONE"
        best_prof: int | None = None
        # Reuse the team match rule: exact skill wins, same-category partial.
        pseudo = SolverInput(
            user_id=mentor.user_id,
            name=mentor.name,
            availability=mentor.availability,
            current_workload=mentor.current_workload,
            max_workload=mentor.max_workload,
            skills=tuple(
                SolverSkillInput(
                    skill_id=s.skill_id,
                    name=s.name,
                    proficiency=s.proficiency,
                    is_verified=s.is_verified,
                    category=s.category,
                )
                for s in mentor.skills
            ),
        )
        _strength, kind, skill = best_match_for_skill(pseudo, req)
        if skill is not None:
            # Strength carries the exact-vs-category discount (same rule as
            # team coverage), so a same-category skill never counts as much
            # as an exact one.
            best_strength = _strength
            best_kind = kind
            best_prof = skill.proficiency
        weighted += relevance * best_strength
        details.append(
            MentorSkillDetail(
                required_skill_id=req.skill_id,
                required_skill_name=req.name,
                relevance=relevance,
                match_kind=best_kind,
                proficiency=best_prof,
                proficiency_label=proficiency_label(best_prof) if best_prof else None,
                strength=round(best_strength, 4),
            )
        )
    fraction = weighted / relevance_total if relevance_total > 0 else 0.0
    return fraction, details


def score_mentor(
    mentor: MentorInput,
    required: tuple[RequiredSkillInput, ...],
    category: str | None,
    semantic_similarity: float,
    *,
    weight_specialization: float = 35.0,
    weight_skill: float = 30.0,
    weight_category: float = 15.0,
    weight_availability: float = 10.0,
    weight_workload: float = 10.0,
) -> MentorScore:
    """Score one mentor. Semantic similarity is one input (35), never the whole."""
    if not required:
        raise ValueError("Cannot score a mentor without required skills")
    semantic = max(0.0, min(1.0, semantic_similarity))
    skill_fraction, details = skill_match_fraction(mentor, required)
    category_fraction = category_overlap(category, mentor.specialization, mentor.department)
    availability = 1.0 if mentor.availability == "AVAILABLE" else 0.5
    workload = spare_fraction(mentor.current_workload, mentor.max_workload)

    specialization_c = semantic * weight_specialization
    skill_c = skill_fraction * weight_skill
    category_c = category_fraction * weight_category
    availability_c = availability * weight_availability
    workload_c = workload * weight_workload
    total = specialization_c + skill_c + category_c + availability_c + workload_c
    return MentorScore(
        total=round(total, 2),
        specialization=round(specialization_c, 2),
        skill=round(skill_c, 2),
        category=round(category_c, 2),
        availability=round(availability_c, 2),
        workload=round(workload_c, 2),
        semantic_similarity=round(semantic, 4),
        skill_details=details,
    )
