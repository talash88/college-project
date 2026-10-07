#!/usr/bin/env python3
"""Development threshold calibration for duplicate detection (honest, small-scale).

Runs a hand-built set of positive / negative / hard-negative pairs through
the REAL embedding model and hybrid scorer, then prints the similarity
distribution. This is development calibration on a tiny set — NOT a claim of
production-grade tuning.

Usage: python3 scripts/calibrate_duplicate_thresholds.py
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.ml.duplicates.text import (  # noqa: E402
    category_support,
    final_match_score,
    format_duplicate_text,
    location_support,
    normalize_location,
)
from app.ml.skills.embeddings import get_embedding_model  # noqa: E402
from app.ml.skills.matcher import cosine  # noqa: E402

_model = None

# (label, kind, text_a, text_b) — kind in positive/negative/hard/borderline
PAIRS: list[tuple[str, str, str, str]] = [
    ("wifi-paraphrase", "positive",
     "Library WiFi disconnects every few minutes.",
     "Internet connection keeps dropping while students are sitting in the library."),
    ("cctv-paraphrase", "positive",
     "Main gate CCTV has stopped working.",
     "Security camera at the college entrance is not recording."),
    ("water-paraphrase", "positive",
     "Drinking water unit near CSE block is empty.",
     "No water is available at the CSE drinking station."),
    ("lab-wifi-paraphrase", "positive",
     "The WiFi in computer lab keeps disconnecting.",
     "Students cannot maintain an internet connection inside the computer lab."),
    ("library-wifi-vs-water", "negative",
     "Library WiFi keeps disconnecting for students.",
     "Water is leaking from the library washroom taps."),
    ("lab-projector-vs-network", "negative",
     "The computer lab projector shows no display output.",
     "There is no internet access in the computer lab."),
    ("hostel-clean-vs-electrical", "negative",
     "Hostel corridors have not been cleaned for a week.",
     "Hostel rooms face frequent power cuts every evening."),
    ("transport-vs-mess", "negative",
     "The college bus on route 3 has not arrived for two days.",
     "Mess food quality is very poor this week."),
    ("sparking-vs-leak", "negative",
     "The electrical panel is sparking near the classroom.",
     "Water is leaking from the corridor pipe."),
    ("wifi-library-vs-hostel", "borderline",
     "Library WiFi keeps disconnecting for students.",
     "Hostel WiFi is very slow at night."),
    ("library-wifi-vs-light", "hard",
     "The library reading room tube light is flickering.",
     "Library WiFi disconnects every few minutes."),
    ("gate-cctv-vs-streetlight", "hard",
     "CCTV camera near the main gate is offline.",
     "The streetlight near the main gate is not working."),
]


def score_pair(text_a, text_b, category=None):  # type: ignore[no-untyped-def]
    vectors = _model.encode([text_a, text_b], normalize_embeddings=True, show_progress_bar=False)
    sem = cosine(vectors[0].tolist(), vectors[1].tolist())
    return sem


def main() -> int:
    global _model

    _model = get_embedding_model()
    print(f"model={settings.SKILL_EMBEDDING_MODEL}")
    print(f"{'pair':28s} {'kind':10s} {'sem':>6s} {'loc':>5s} {'final':>6s}")
    for label, kind, text_a, text_b in PAIRS:
        sem = score_pair(text_a, text_b)
        loc = location_support(normalize_location(text_a, None, None), normalize_location(text_b, None, None))
        final = final_match_score(
            sem, loc, 0.0,
            semantic_weight=settings.DUPLICATE_SEMANTIC_WEIGHT,
            location_weight=settings.DUPLICATE_LOCATION_WEIGHT,
            category_weight=settings.DUPLICATE_CATEGORY_WEIGHT,
        )
        print(f"{label:28s} {kind:10s} {sem:6.3f} {loc:5.2f} {final:6.3f}")
    # Full report-style texts (title+description+location+category), as the pipeline uses.
    full_pairs: list[tuple[str, str, tuple[str, str, str, str], tuple[str, str, str, str]]] = [
        ("wifi-full-positive", "positive",
         ("Library WiFi keeps disconnecting",
          "The WiFi in the central library keeps disconnecting every few minutes and students cannot attend online classes.",
          "Central Library", "IT_NETWORK"),
         ("Internet drops inside library",
          "Students cannot maintain a stable internet connection while sitting in the library reading hall.",
          "Library Reading Hall", "IT_NETWORK")),
        ("cctv-full-positive", "positive",
         ("Main gate CCTV stopped working",
          "The main gate CCTV camera has stopped working since yesterday and nothing is being recorded.",
          "Main Gate", "SAFETY_SECURITY"),
         ("Entrance security camera not recording",
          "The security camera at the college entrance is not recording footage.",
          "College Entrance", "SAFETY_SECURITY")),
        ("library-wifi-vs-water-full", "negative",
         ("Library WiFi keeps disconnecting",
          "The WiFi in the central library keeps disconnecting every few minutes.",
          "Central Library", "IT_NETWORK"),
         ("Library washroom taps leaking",
          "Water is leaking continuously from the washroom taps on the library ground floor.",
          "Library", "WATER_SANITATION")),
        ("hostel-clean-vs-elec-full", "negative",
         ("Hostel corridors not cleaned",
          "The hostel corridors have not been cleaned for a week and garbage is piling up.",
          "Boys Hostel", "CLEANLINESS_SANITATION"),
         ("Hostel power cuts evening",
          "Hostel rooms face frequent power cuts every evening for the past week.",
          "Boys Hostel", "ELECTRICAL")),
    ]
    for label, kind, a, b in full_pairs:
        text_a = format_duplicate_text(a[0], a[1], a[2], None, None, a[3])
        text_b = format_duplicate_text(b[0], b[1], b[2], None, None, b[3])
        sem = score_pair(text_a, text_b)
        loc = location_support(normalize_location(a[2], None, None), normalize_location(b[2], None, None))
        cat = category_support(a[3], b[3])
        final = final_match_score(
            sem, loc, cat,
            semantic_weight=settings.DUPLICATE_SEMANTIC_WEIGHT,
            location_weight=settings.DUPLICATE_LOCATION_WEIGHT,
            category_weight=settings.DUPLICATE_CATEGORY_WEIGHT,
        )
        print(f"{label:28s} {kind:10s} {sem:6.3f} {loc:5.2f} {final:6.3f}")
    print(f"candidate_threshold={settings.DUPLICATE_CANDIDATE_THRESHOLD} "
          f"strong_threshold={settings.DUPLICATE_STRONG_THRESHOLD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
