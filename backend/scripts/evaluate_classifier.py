#!/usr/bin/env python3
"""Evaluate the trained artifact on the HELD-OUT test split (seed 42).

Saves backend/ml/artifacts/problem_classifier/metrics.json with real numbers.
Usage: python3 scripts/evaluate_classifier.py
"""

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.ml.classification.config import ClassifierConfig  # noqa: E402
from app.ml.classification.dataset import (  # noqa: E402
    label_to_id,
    load_rows,
    stratified_split,
    texts_and_ids,
)
from app.ml.classification.inference import ProblemClassifier  # noqa: E402
from app.ml.classification.metrics import compute_metrics  # noqa: E402

ARTIFACT_DIR = BACKEND_ROOT / "ml" / "artifacts" / "problem_classifier"


def main() -> int:
    config = ClassifierConfig()
    rows = load_rows()
    mapping = label_to_id(config.labels)
    _, _, test_rows = stratified_split(rows, seed=config.seed)
    test_texts, test_ids = texts_and_ids(test_rows, mapping)

    clf = ProblemClassifier(ARTIFACT_DIR, config)
    preds: list[int] = []
    for text in test_texts:
        _, _, probs = clf.predict(text)
        preds.append(max(range(len(probs)), key=lambda i: probs[i]))

    metrics = compute_metrics(test_ids, preds, list(config.labels))
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"test samples: {metrics['n_samples']}")
    print(f"accuracy: {metrics['accuracy']}")
    print(f"macro F1: {metrics['macro_f1']}")
    print(f"weighted F1: {metrics['weighted_f1']}")
    print("per-class F1:")
    per_class = metrics["per_class"]
    assert isinstance(per_class, dict)
    for label in sorted(per_class):
        entry = per_class[label]
        assert isinstance(entry, dict)
        print(f"  {label}: {entry['f1']}")
    print(f"saved: {ARTIFACT_DIR / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
