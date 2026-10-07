"""Honest evaluation metrics (never invented)."""

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)


def compute_metrics(y_true: list[int], y_pred: list[int], labels: list[str]) -> dict[str, Any]:
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=list(range(len(labels))), zero_division=0
    )
    per_class = {
        labels[i]: {
            "precision": round(float(precision[i]), 4),
            "recall": round(float(recall[i]), 4),
            "f1": round(float(f1[i]), 4),
        }
        for i in range(len(labels))
    }
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_precision": round(float(np.mean(precision)), 4),
        "macro_recall": round(float(np.mean(recall)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "weighted_f1": round(
            float(f1_score(y_true, y_pred, average="weighted", zero_division=0)), 4
        ),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(
            y_true, y_pred, labels=list(range(len(labels)))
        ).tolist(),
        "n_samples": len(y_true),
    }
