"""Deterministic team-combination search (pure).

Small college pools: exact combinations up to max team size. Larger pools:
pre-rank solvers by solo score, cap the pool, then evaluate combinations.
Complexity: sum over sizes of C(pool, size) team evaluations.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from app.ml.recommendations.scoring import (
    RequiredSkillInput,
    SolverInput,
    TeamScore,
    score_team,
    spare_fraction,
)


@dataclass
class TeamOption:
    members: tuple[SolverInput, ...]
    score: TeamScore


def _sort_key(option: TeamOption) -> tuple[float, int, float, tuple[str, ...]]:
    """Higher score, then smaller team, then lower workload, then stable UUIDs."""
    mean_load = sum(m.current_workload / max(1, m.max_workload) for m in option.members) / len(
        option.members
    )
    member_ids = tuple(sorted(m.user_id for m in option.members))
    return (-option.score.total, len(option.members), round(mean_load, 6), member_ids)


def search_teams(
    solvers: list[SolverInput],
    required: list[RequiredSkillInput],
    category: str | None,
    *,
    min_size: int = 2,
    max_size: int = 4,
    allow_solo: bool = False,
    num_options: int = 3,
    pool_size: int = 12,
    weights: dict[str, float] | None = None,
) -> list[TeamOption]:
    """Return up to num_options best team combinations, best first.

    Deterministic for identical inputs: no randomness anywhere.
    """
    weights = weights or {}
    if not solvers or not required:
        return []
    if min_size < 1 or max_size < min_size:
        raise ValueError("Invalid team size bounds")

    def solo_score(solver: SolverInput) -> float:
        return score_team(
            (solver,), tuple(required), category, **_weight_kwargs(weights)
        ).total

    ranked = sorted(
        solvers,
        key=lambda s: (
            -solo_score(s),
            s.current_workload / max(1, s.max_workload),
            s.user_id,
        ),
    )
    pool = ranked[: max(1, pool_size)]

    sizes = list(range(min_size, max_size + 1))
    if allow_solo and 1 not in sizes:
        sizes = [1, *sizes]

    options: list[TeamOption] = []
    for size in sizes:
        if size > len(pool):
            continue
        for combo in combinations(pool, size):
            team = tuple(sorted(combo, key=lambda m: m.user_id))
            team_score = score_team(team, tuple(required), category, **_weight_kwargs(weights))
            options.append(TeamOption(members=team, score=team_score))

    options.sort(key=_sort_key)
    # Distinct member sets only (combinations are distinct by construction).
    seen: set[tuple[str, ...]] = set()
    distinct: list[TeamOption] = []
    for option in options:
        key = tuple(sorted(m.user_id for m in option.members))
        if key in seen:
            continue
        seen.add(key)
        distinct.append(option)
        if len(distinct) >= num_options:
            break
    return distinct


def _weight_kwargs(weights: dict[str, float]) -> dict[str, float]:
    kwargs: dict[str, float] = {}
    mapping = {
        "coverage": "weight_coverage",
        "proficiency": "weight_proficiency",
        "availability": "weight_availability",
        "workload": "weight_workload",
        "verified": "weight_verified",
        "domain": "weight_domain",
    }
    for short, full in mapping.items():
        if short in weights:
            kwargs[full] = weights[short]
    return kwargs


def mean_spare(team: tuple[SolverInput, ...]) -> float:
    if not team:
        return 0.0
    return sum(spare_fraction(m.current_workload, m.max_workload) for m in team) / len(team)
