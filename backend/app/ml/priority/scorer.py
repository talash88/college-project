"""Deterministic, explainable priority scorer (pure functions, no DB, no ML).

Score = severity + affected + age + category + duplicate (Step 7: real
admin-confirmed cluster count), each with raw value, contribution and a
human-readable reason.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.ml.priority.config import (
    AFFECTED_BUCKETS,
    AGE_BUCKETS,
    CATEGORY_WEIGHTS,
    NEGATION_TOKENS,
    NEGATION_WINDOW,
    TERMINAL_STATUSES,
    PriorityConfig,
    default_config,
)


@dataclass
class ComponentScore:
    component: str
    raw_value: object
    contribution: int
    max_contribution: int
    reason: str


@dataclass
class PriorityResult:
    score: int
    level: str
    components: list[ComponentScore] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def level_for_score(score: int, config: PriorityConfig | None = None) -> str:
    cfg = config or default_config()
    if score <= cfg.level_low_max:
        return "LOW"
    if score <= cfg.level_medium_max:
        return "MEDIUM"
    if score <= cfg.level_high_max:
        return "HIGH"
    return "CRITICAL"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _is_negated(tokens: list[str], match_start: int) -> bool:
    """True if a negation token appears within the window before the match."""
    window = tokens[max(0, match_start - NEGATION_WINDOW) : match_start]
    return any(tok in NEGATION_TOKENS or tok.endswith("n't") for tok in window)


def _find_signals(text: str, config: PriorityConfig) -> list[tuple[str, str, int]]:
    """Return (matched_phrase, signal_label, weight) for non-negated hits."""
    lowered = text.lower()
    tokens = _tokenize(text)
    hits: list[tuple[str, str, int]] = []
    for signal in config.risk_lexicon:
        for phrase in signal.phrases:
            start = 0
            matched = False
            while True:
                idx = lowered.find(phrase, start)
                if idx < 0:
                    break
                token_index = len(_tokenize(lowered[:idx]))
                if not _is_negated(tokens, token_index):
                    matched = True
                    break
                start = idx + len(phrase)
            if matched:
                hits.append((phrase, signal.label, signal.weight))
                break  # one hit per lexicon entry avoids double counting
    return hits


def score_severity(
    title: str, description: str, config: PriorityConfig | None = None
) -> ComponentScore:
    cfg = config or default_config()
    text = f"{title}\n{description}"
    hits = _find_signals(text, cfg)
    contribution = min(sum(w for _, _, w in hits), cfg.weight_severity)
    if not hits:
        reason = "No elevated risk phrases detected in the report text."
    else:
        parts = ", ".join(f'"{phrase}" ({label})' for phrase, label, _ in hits)
        reason = f"Risk signals detected: {parts}."
    return ComponentScore(
        component="severity",
        raw_value=[phrase for phrase, _, _ in hits],
        contribution=contribution,
        max_contribution=cfg.weight_severity,
        reason=reason,
    )


def score_affected(count: int | None, config: PriorityConfig | None = None) -> ComponentScore:
    cfg = config or default_config()
    if count is None:
        return ComponentScore(
            component="affected_people",
            raw_value=None,
            contribution=0,
            max_contribution=cfg.weight_affected,
            reason="Number of affected people was not provided.",
        )
    contribution = next(c for bound, c in AFFECTED_BUCKETS if count <= bound)
    return ComponentScore(
        component="affected_people",
        raw_value=count,
        contribution=contribution,
        max_contribution=cfg.weight_affected,
        reason=f"Approximately {count} {'person is' if count == 1 else 'people are'} affected.",
    )


def score_age(
    submitted_at: datetime,
    status: str,
    now: datetime | None = None,
    config: PriorityConfig | None = None,
) -> ComponentScore:
    cfg = config or default_config()
    moment = now or datetime.now(UTC)
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    age_days = max(0.0, (moment - submitted_at).total_seconds() / 86400.0)
    if status in TERMINAL_STATUSES:
        return ComponentScore(
            component="pending_age",
            raw_value=round(age_days, 2),
            contribution=0,
            max_contribution=cfg.weight_age,
            reason="Report is resolved/closed; age contribution frozen.",
        )
    contribution = next(c for bound, c in AGE_BUCKETS if age_days < bound)
    if age_days < 1:
        reason = "Reported less than a day ago."
    elif age_days < 2:
        reason = "Unresolved for about 1 day."
    else:
        reason = f"Unresolved for about {int(age_days)} days."
    return ComponentScore(
        component="pending_age",
        raw_value=round(age_days, 2),
        contribution=contribution,
        max_contribution=cfg.weight_age,
        reason=reason,
    )


def score_category(
    final_category: str | None,
    predicted_category: str | None,
    config: PriorityConfig | None = None,
) -> ComponentScore:
    cfg = config or default_config()
    category = final_category or predicted_category
    if not category:
        return ComponentScore(
            component="category_context",
            raw_value=None,
            contribution=0,
            max_contribution=cfg.weight_category,
            reason="No classification available yet; category contributes nothing.",
        )
    weight = CATEGORY_WEIGHTS.get(category, 0)
    source = "admin-reviewed" if final_category else "AI-predicted"
    return ComponentScore(
        component="category_context",
        raw_value=category,
        contribution=min(weight, cfg.weight_category),
        max_contribution=cfg.weight_category,
        reason=f"{source} category {category} adds contextual urgency (capped, never dominant).",
    )


def duplicate_contribution(count: int) -> int:
    """Monotonic mapping of ADMIN-CONFIRMED additional cluster reports."""
    if count <= 0:
        return 0
    if count == 1:
        return 2
    if count <= 3:
        return 4
    if count <= 6:
        return 6
    if count <= 10:
        return 8
    return 10


def score_duplicate(
    count: int = 0, config: PriorityConfig | None = None
) -> ComponentScore:
    cfg = config or default_config()
    contribution = min(duplicate_contribution(count), cfg.weight_duplicate)
    if count <= 0:
        reason = "No confirmed duplicates; contribution is 0."
    elif count == 1:
        reason = "1 additional confirmed report refers to the same underlying issue."
    else:
        reason = f"{count} additional confirmed reports refer to the same underlying issue."
    return ComponentScore(
        component="duplicate_impact",
        raw_value=count,
        contribution=contribution,
        max_contribution=cfg.weight_duplicate,
        reason=reason,
    )


def calculate_priority(
    *,
    title: str,
    description: str,
    affected_people_count: int | None,
    submitted_at: datetime,
    status: str,
    final_category: str | None = None,
    predicted_category: str | None = None,
    duplicate_count: int = 0,
    now: datetime | None = None,
    config: PriorityConfig | None = None,
) -> PriorityResult:
    cfg = config or default_config()
    components = [
        score_severity(title, description, cfg),
        score_affected(affected_people_count, cfg),
        score_age(submitted_at, status, now, cfg),
        score_category(final_category, predicted_category, cfg),
        score_duplicate(duplicate_count, cfg),
    ]
    score = max(0, min(100, sum(c.contribution for c in components)))
    reasons = [f"+ {c.contribution}: {c.reason}" for c in components if c.contribution > 0] or [
        "No urgency signals; baseline report."
    ]
    return PriorityResult(
        score=score, level=level_for_score(score, cfg), components=components, reasons=reasons
    )
