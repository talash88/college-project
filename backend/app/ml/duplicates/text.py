"""Duplicate-detection text utilities (pure, deterministic).

Embedding input deliberately excludes reporter identity, ticket IDs,
timestamps, skills and scores: only the issue description matters.
Location is included but must never dominate (semantic cosine does that).
"""

import hashlib
import re

# Generic location tokens ignored for support scoring (too common to mean
# "same incident"). Informative tokens (library, hostel, lab, gate…) stay.
GENERIC_LOCATION_TOKENS = frozenset(
    {
        "campus",
        "college",
        "building",
        "block",
        "room",
        "floor",
        "hall",
        "area",
        "main",
        "new",
        "old",
        "near",
        "outside",
        "inside",
        "ground",
        "first",
        "second",
        "third",
    }
)


def format_duplicate_text(
    title: str,
    description: str,
    location_text: str | None = None,
    building: str | None = None,
    area: str | None = None,
    category: str | None = None,
) -> str:
    parts = [f"Title: {title.strip()}", f"Description: {description.strip()}"]
    location_bits = [b.strip() for b in (location_text, building, area) if b and b.strip()]
    if location_bits:
        parts.append("Location: " + ", ".join(location_bits))
    if category and category.strip():
        parts.append(f"Category: {category.strip()}")
    return "\n".join(parts)


def source_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def normalize_location(
    location_text: str | None, building: str | None, area: str | None
) -> set[str]:
    combined = " ".join(b for b in (location_text, building, area) if b)
    return {t for t in _tokens(combined) if t not in GENERIC_LOCATION_TOKENS}


def location_support(a: set[str], b: set[str]) -> float:
    """Jaccard overlap of informative location tokens, 0..1."""
    if not a and not b:
        return 0.5  # neither report names a specific place: neutral, not evidence
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def category_support(category_a: str | None, category_b: str | None) -> float:
    """1.0 on agreement, else 0.0 (never vetoes: the classifier is imperfect)."""
    if not category_a or not category_b:
        return 0.0
    return 1.0 if category_a == category_b else 0.0


def final_match_score(
    semantic: float,
    location: float,
    category: float,
    *,
    semantic_weight: float = 0.85,
    location_weight: float = 0.10,
    category_weight: float = 0.05,
) -> float:
    """Hybrid score. Semantic similarity dominates by design."""
    return round(
        semantic * semantic_weight + location * location_weight + category * category_weight,
        4,
    )
