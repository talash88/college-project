#!/usr/bin/env python3
"""Validate the campus problem classification dataset.

Reports: sample count, per-class counts, duplicate texts, invalid records,
and the stratified train/validation/test split sizes (seed 42).
Exit code 0 when valid, 1 otherwise.
"""

import json
import sys
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = BACKEND_ROOT / "ml" / "data" / "problem_classification_v1.jsonl"
SEED = 42


def main() -> int:
    if not DATA_FILE.exists():
        print(f"ERROR: dataset file missing: {DATA_FILE}")
        return 1

    rows = []
    invalid = 0
    for lineno, line in enumerate(DATA_FILE.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            print(f"ERROR line {lineno}: invalid JSON")
            invalid += 1
            continue
        text = record.get("text", "")
        label = record.get("label", "")
        if not isinstance(text, str) or not text.strip():
            print(f"ERROR line {lineno}: empty text")
            invalid += 1
            continue
        if not isinstance(label, str) or not label.strip():
            print(f"ERROR line {lineno}: empty label")
            invalid += 1
            continue
        rows.append({"text": text.strip(), "label": label.strip()})

    labels = [r["label"] for r in rows]
    counts = Counter(labels)
    normalized = [r["text"].lower() for r in rows]
    duplicates = len(normalized) - len(set(normalized))

    print(f"dataset: {DATA_FILE.name}")
    print(f"samples: {len(rows)}")
    print(f"classes: {len(counts)}")
    for label in sorted(counts):
        print(f"  {label}: {counts[label]}")
    print(f"duplicates: {duplicates}")
    print(f"invalid records: {invalid}")

    # Stratified split preview (same logic as training; seed fixed).
    try:
        from sklearn.model_selection import StratifiedShuffleSplit
    except ImportError:
        print("sklearn not installed; skipping split preview")
        return 0 if invalid == 0 and duplicates == 0 else 1

    texts = [r["text"] for r in rows]
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=0.30, random_state=SEED)
    train_idx, temp_idx = next(splitter.split(texts, labels))
    temp_labels = [labels[i] for i in temp_idx]
    splitter2 = StratifiedShuffleSplit(n_splits=1, test_size=0.50, random_state=SEED)
    val_rel, test_rel = next(splitter2.split([texts[i] for i in temp_idx], temp_labels))
    print(f"split (seed {SEED}): train={len(train_idx)} val={len(val_rel)} test={len(test_rel)}")

    ok = invalid == 0 and duplicates == 0 and len(counts) >= 2
    print("VALID" if ok else "INVALID")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
