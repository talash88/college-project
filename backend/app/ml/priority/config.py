"""Explainable priority configuration (campusxolve-priority-v1).

No magic numbers in source: every weight, bucket and threshold lives here
(or in env-backed Settings) and is surfaced in API responses and docs.
"""

from dataclasses import dataclass

ALGORITHM_VERSION = "campusxolve-priority-v1"

# Component weight caps. Sum of maxima = 100, so the score is natively 0-100.
WEIGHT_SEVERITY = 30
WEIGHT_AFFECTED = 25
WEIGHT_AGE = 20
WEIGHT_CATEGORY = 15
WEIGHT_DUPLICATE = 10

# Level boundaries (upper bounds, inclusive). Defaults mirror Settings and
# may be tuned via PRIORITY_*_MAX env vars.
LEVEL_LOW_MAX = 29
LEVEL_MEDIUM_MAX = 54
LEVEL_HIGH_MAX = 79


@dataclass(frozen=True)
class RiskSignal:
    """One phrase-aware lexicon entry."""

    phrases: tuple[str, ...]
    label: str
    weight: int


# Emergency tier: direct danger. High tier: essential-service loss / crime.
# Medium tier: degradation that still disrupts campus life.
RISK_LEXICON: tuple[RiskSignal, ...] = (
    RiskSignal(
        phrases=("fire", "sparking", "short circuit", "electric shock", "gas leak"),
        label="emergency safety signal",
        weight=15,
    ),
    RiskSignal(
        phrases=(
            "exposed wire",
            "exposed wires",
            "live wire",
            "injury",
            "injured",
            "bleeding",
            "smoke",
        ),
        label="injury/electrical hazard signal",
        weight=12,
    ),
    RiskSignal(
        phrases=(
            "no drinking water",
            "no water supply",
            "power outage",
            "no power",
            "sewage overflow",
            "theft",
            "break-in",
            "ragging",
        ),
        label="essential utility / security disruption signal",
        weight=8,
    ),
    RiskSignal(
        phrases=(
            "flooding",
            "flooded",
            "outage",
            "blocked exit",
            "emergency exit",
            "stray dogs",
            "snake",
        ),
        label="facility/safety disruption signal",
        weight=8,
    ),
    RiskSignal(
        phrases=(
            "leak",
            "leaking",
            "broken",
            "damaged",
            "not working",
            "dirty",
            "unhygienic",
            "pests",
            "overflowing",
        ),
        label="degradation signal",
        weight=4,
    ),
)

# Simple negation window: these tokens shortly before a match suppress it.
NEGATION_TOKENS = frozenset({"no", "not", "never", "without", "none", "hardly", "barely", "n't"})
NEGATION_WINDOW = 3

# Category context weights (deliberately small: category is ONE signal and
# the Step 5 classifier is imperfect, especially for SAFETY_SECURITY).
CATEGORY_WEIGHTS = {
    "SAFETY_SECURITY": 12,
    "ELECTRICAL": 10,
    "WATER_SANITATION": 10,
    "IT_NETWORK": 8,
    "HOSTEL": 6,
    "TRANSPORT": 6,
    "INFRASTRUCTURE": 6,
    "LABORATORY": 5,
    "ACADEMIC": 5,
    "CLEANLINESS_SANITATION": 5,
    "LIBRARY": 3,
    "OTHER": 2,
}

# Affected-people buckets: (upper_bound_inclusive, contribution).
AFFECTED_BUCKETS: tuple[tuple[int, int], ...] = (
    (5, 5),
    (20, 10),
    (50, 15),
    (100, 20),
    (500, 23),
    (10**9, 25),
)

# Pending-age buckets in days: (upper_bound_exclusive, contribution).
AGE_BUCKETS: tuple[tuple[float, int], ...] = (
    (1.0, 2),
    (3.0, 6),
    (7.0, 10),
    (14.0, 15),
    (float("inf"), 20),
)

# Terminal report statuses freeze age (no escalation after resolution).
TERMINAL_STATUSES = frozenset({"RESOLVED", "CLOSED", "REJECTED", "DUPLICATE", "WITHDRAWN"})


@dataclass(frozen=True)
class PriorityConfig:
    weight_severity: int = WEIGHT_SEVERITY
    weight_affected: int = WEIGHT_AFFECTED
    weight_age: int = WEIGHT_AGE
    weight_category: int = WEIGHT_CATEGORY
    weight_duplicate: int = WEIGHT_DUPLICATE
    level_low_max: int = LEVEL_LOW_MAX
    level_medium_max: int = LEVEL_MEDIUM_MAX
    level_high_max: int = LEVEL_HIGH_MAX
    risk_lexicon: tuple[RiskSignal, ...] = RISK_LEXICON


def default_config() -> PriorityConfig:
    return PriorityConfig()
