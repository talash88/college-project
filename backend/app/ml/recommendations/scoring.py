"""Deterministic team-scoring math for Step 8 (pure, no DB, no models).

A team is evaluated as a COMBINATION, never as a ranked individual list:
per required skill only the best-matching member counts (no double counting),
relevance weights come straight from Step 6 extraction, and every component
is persisted with its breakdown so the recommendation is explainable without
any LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Proficiency 1-5 mapped transparently onto 0.2-1.0.
PROFICIENCY_FACTOR: dict[int, float] = {1: 0.20, 2: 0.40, 3: 0.60, 4: 0.80, 5: 1.00}

PROFICIENCY_LABELS: dict[int, str] = {
    1: "Beginner",
    2: "Basic",
    3: "Intermediate",
    4: "Advanced",
    5: "Expert",
}

# Same-category (non-exact) skill counts as partial support, never as much as
# an exact skill match.
CATEGORY_PARTIAL_FACTOR = 0.30

AVAILABILITY_FACTOR: dict[str, float] = {"AVAILABLE": 1.0, "LIMITED": 0.5}

# Problem categories with a genuinely meaningful department link. Every other
# category (or a missing category) is neutral: all members score 1.0, so the
# domain component never punishes anyone outside these four mappings.
CATEGORY_DEPARTMENTS: dict[str, frozenset[str]] = {
    "IT_NETWORK": frozenset({"Computer Science & Engineering", "Information Technology"}),
    "ELECTRICAL": frozenset({"Electrical", "Electronics"}),
    "WATER_SANITATION": frozenset({"Civil"}),
    "TRANSPORT": frozenset({"Mechanical"}),
}


@dataclass(frozen=True)
class RequiredSkillInput:
    skill_id: str
    name: str
    relevance: float  # Step 6 extraction score, 0-1
    category: str | None = None


@dataclass(frozen=True)
class SolverSkillInput:
    skill_id: str
    name: str
    proficiency: int  # 1-5
    is_verified: bool
    category: str | None = None


@dataclass(frozen=True)
class SolverInput:
    user_id: str
    name: str
    availability: str  # AVAILABLE | LIMITED (UNAVAILABLE never reaches here)
    current_workload: int
    max_workload: int
    department: str | None = None
    academic_year: int | None = None
    skills: tuple[SolverSkillInput, ...] = ()


@dataclass
class SkillMatchDetail:
    required_skill_id: str
    required_skill_name: str
    relevance: float
    best_member_id: str | None
    best_member_name: str | None
    match_kind: str  # EXACT | CATEGORY | NONE
    proficiency: int | None
    proficiency_label: str | None
    verified: bool
    strength: float  # 0-1 contribution factor for this skill


@dataclass
class TeamScore:
    total: float
    coverage: float  # 0-100 component contributions (already weighted)
    proficiency: float
    availability: float
    workload: float
    verified: float
    domain: float
    coverage_percent: float  # 0-100 raw coverage
    per_skill: list[SkillMatchDetail] = field(default_factory=list)
    missing_skill_names: list[str] = field(default_factory=list)


def proficiency_factor(level: int) -> float:
    """Transparent 1-5 → 0.2-1.0 mapping (clamped defensively)."""
    clamped = max(1, min(5, int(level)))
    return PROFICIENCY_FACTOR[clamped]


def proficiency_label(level: int) -> str:
    return PROFICIENCY_LABELS[max(1, min(5, int(level)))]


def spare_fraction(current: int, maximum: int) -> float:
    """Spare workload capacity 0-1. 0/3 beats 2/3."""
    if maximum <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (current / maximum)))


def availability_factor(status: str) -> float:
    return AVAILABILITY_FACTOR.get(status, 0.0)


def domain_factor(department: str | None, category: str | None) -> float:
    """1.0 when the member's department genuinely fits the problem domain,
    else neutral (1.0 for unmapped categories, 0.5 otherwise) — never zero."""
    if not category or category not in CATEGORY_DEPARTMENTS:
        return 1.0
    if department and department in CATEGORY_DEPARTMENTS[category]:
        return 1.0
    return 0.5


def best_match_for_skill(
    solver: SolverInput, required: RequiredSkillInput
) -> tuple[float, str, SolverSkillInput | None]:
    """Best (strength, kind, skill) this solver offers for one required skill.

    Exact skill_id match wins; otherwise the strongest same-category skill
    counts as partial support.
    """
    exact: SolverSkillInput | None = None
    for skill in solver.skills:
        if skill.skill_id == required.skill_id:
            if exact is None or skill.proficiency > exact.proficiency:
                exact = skill
    if exact is not None:
        return proficiency_factor(exact.proficiency), "EXACT", exact
    partial: SolverSkillInput | None = None
    if required.category:
        for skill in solver.skills:
            if skill.category == required.category:
                if partial is None or skill.proficiency > partial.proficiency:
                    partial = skill
    if partial is not None:
        return CATEGORY_PARTIAL_FACTOR * proficiency_factor(partial.proficiency), "CATEGORY", partial
    return 0.0, "NONE", None


def score_team(
    team: tuple[SolverInput, ...],
    required: tuple[RequiredSkillInput, ...],
    category: str | None,
    *,
    weight_coverage: float = 50.0,
    weight_proficiency: float = 20.0,
    weight_availability: float = 10.0,
    weight_workload: float = 10.0,
    weight_verified: float = 5.0,
    weight_domain: float = 5.0,
) -> TeamScore:
    """Score one team combination. Deterministic; raises on empty input."""
    if not team:
        raise ValueError("Cannot score an empty team")
    if not required:
        raise ValueError("Cannot score without required skills")

    per_skill: list[SkillMatchDetail] = []
    relevance_total = 0.0
    coverage_weighted = 0.0
    proficiency_sum = 0.0
    verified_sum = 0.0
    for req in required:
        relevance = max(0.0, min(1.0, req.relevance))
        relevance_total += relevance
        best_strength = 0.0
        best_member: SolverInput | None = None
        best_kind = "NONE"
        best_skill: SolverSkillInput | None = None
        for member in team:
            strength, kind, skill = best_match_for_skill(member, req)
            if strength > best_strength:
                best_strength = strength
                best_member = member
                best_kind = kind
                best_skill = skill
        coverage_weighted += relevance * best_strength
        if best_skill is not None and best_member is not None:
            proficiency_sum += proficiency_factor(best_skill.proficiency)
            if best_kind == "EXACT" and best_skill.is_verified:
                verified_sum += 1.0
            else:
                verified_sum += 0.5
            per_skill.append(
                SkillMatchDetail(
                    required_skill_id=req.skill_id,
                    required_skill_name=req.name,
                    relevance=relevance,
                    best_member_id=best_member.user_id,
                    best_member_name=best_member.name,
                    match_kind=best_kind,
                    proficiency=best_skill.proficiency,
                    proficiency_label=proficiency_label(best_skill.proficiency),
                    verified=best_skill.is_verified,
                    strength=round(best_strength, 4),
                )
            )
        else:
            per_skill.append(
                SkillMatchDetail(
                    required_skill_id=req.skill_id,
                    required_skill_name=req.name,
                    relevance=relevance,
                    best_member_id=None,
                    best_member_name=None,
                    match_kind="NONE",
                    proficiency=None,
                    proficiency_label=None,
                    verified=False,
                    strength=0.0,
                )
            )

    coverage = coverage_weighted / relevance_total if relevance_total > 0 else 0.0
    n = len(required)
    proficiency = proficiency_sum / n
    verified = verified_sum / n
    availability = sum(availability_factor(m.availability) for m in team) / len(team)
    workload = sum(spare_fraction(m.current_workload, m.max_workload) for m in team) / len(team)
    domain = sum(domain_factor(m.department, category) for m in team) / len(team)

    coverage_c = coverage * weight_coverage
    proficiency_c = proficiency * weight_proficiency
    availability_c = availability * weight_availability
    workload_c = workload * weight_workload
    verified_c = verified * weight_verified
    domain_c = domain * weight_domain
    total = coverage_c + proficiency_c + availability_c + workload_c + verified_c + domain_c

    missing = [d.required_skill_name for d in per_skill if d.strength < 0.5]
    return TeamScore(
        total=round(total, 2),
        coverage=round(coverage_c, 2),
        proficiency=round(proficiency_c, 2),
        availability=round(availability_c, 2),
        workload=round(workload_c, 2),
        verified=round(verified_c, 2),
        domain=round(domain_c, 2),
        coverage_percent=round(coverage * 100, 2),
        per_skill=per_skill,
        missing_skill_names=missing,
    )
