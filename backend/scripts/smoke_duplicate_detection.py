#!/usr/bin/env python3
"""Step 7 real smoke test: required pairs through the REAL embedding model.

Report-style texts (title+description+location+category), exactly as the
duplicate pipeline formats them. Prints measured semantic/location/category/
final scores plus the candidate verdict (semantic >= candidate threshold).
Nothing is invented: every number comes from all-MiniLM-L6-v2 + the real
hybrid scorer.
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

# (label, kind, (title, description, location, category), (...))
PAIRS = [
    ("library-wifi-vs-internet", "positive",
     ("Library WiFi disconnecting",
      "The WiFi in the central library keeps disconnecting every few minutes and students cannot attend online classes.",
      "Central Library", "IT_NETWORK"),
     ("Library internet dropping",
      "Students cannot maintain a stable internet connection while sitting in the library reading hall during study hours.",
      "Library Reading Hall", "IT_NETWORK")),
    ("main-gate-cctv-vs-entrance-cam", "positive",
     ("Main gate CCTV broken",
      "The main gate CCTV camera has stopped working since yesterday and nothing is being recorded.",
      "Main Gate", "SAFETY_SECURITY"),
     ("Entrance security camera not recording",
      "The security camera at the college entrance is not recording any footage.",
      "College Entrance", "SAFETY_SECURITY")),
    ("cse-water-vs-drinking-station", "positive",
     ("CSE water unavailable",
      "The drinking water unit near the CSE block has been empty since morning and students have no place to refill bottles.",
      "CSE Block", "WATER_SANITATION"),
     ("No water at CSE drinking station",
      "No water is available at the CSE drinking station today, and students are struggling in this heat.",
      "CSE Block", "WATER_SANITATION")),
    ("library-wifi-vs-light", "negative",
     ("Library WiFi disconnecting",
      "The WiFi in the central library keeps disconnecting every few minutes.",
      "Central Library", "IT_NETWORK"),
     ("Library light flickering",
      "The tube light in the library reading room keeps flickering and distracts students.",
      "Central Library", "ELECTRICAL")),
    ("lab-internet-vs-projector", "negative",
     ("Computer lab internet outage",
      "There is no internet access in the computer lab since morning and practicals are stuck.",
      "Computer Lab", "IT_NETWORK"),
     ("Computer lab projector broken",
      "The projector in the computer lab shows no display output during lectures.",
      "Computer Lab", "LABORATORY")),
]


def main() -> int:
    model = get_embedding_model()
    print(f"model={settings.SKILL_EMBEDDING_MODEL} "
          f"embedding_version={settings.PROBLEM_EMBEDDING_VERSION}")
    print(f"candidate_threshold={settings.DUPLICATE_CANDIDATE_THRESHOLD} "
          f"strong_threshold={settings.DUPLICATE_STRONG_THRESHOLD}")
    print(f"{'pair':32s} {'kind':10s} {'sem':>6s} {'loc':>5s} {'cat':>4s} {'final':>6s} candidate")
    for label, kind, a, b in PAIRS:
        text_a = format_duplicate_text(a[0], a[1], a[2], None, None, a[3])
        text_b = format_duplicate_text(b[0], b[1], b[2], None, None, b[3])
        vecs = model.encode([text_a, text_b], normalize_embeddings=True, show_progress_bar=False)
        sem = cosine(vecs[0].tolist(), vecs[1].tolist())
        loc = location_support(
            normalize_location(a[2], None, None), normalize_location(b[2], None, None))
        cat = category_support(a[3], b[3])
        final = final_match_score(
            sem, loc, cat,
            semantic_weight=settings.DUPLICATE_SEMANTIC_WEIGHT,
            location_weight=settings.DUPLICATE_LOCATION_WEIGHT,
            category_weight=settings.DUPLICATE_CATEGORY_WEIGHT)
        verdict = "yes" if sem >= settings.DUPLICATE_CANDIDATE_THRESHOLD else "no"
        print(f"{label:32s} {kind:10s} {sem:6.3f} {loc:5.2f} {cat:4.1f} {final:6.3f} {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
