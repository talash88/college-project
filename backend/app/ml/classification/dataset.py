"""Labelled data loading + stratified splits (seed 42, always)."""

import json
from pathlib import Path

from sklearn.model_selection import StratifiedShuffleSplit

from app.ml.classification.config import ClassifierConfig

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_FILE = BACKEND_ROOT / "ml" / "data" / "problem_classification_v1.jsonl"

TRAIN_FRACTION = 0.70
VAL_FRACTION = 0.15
TEST_FRACTION = 0.15


def label_to_id(labels: tuple[str, ...]) -> dict[str, int]:
    return {label: idx for idx, label in enumerate(labels)}


def load_rows(data_file: Path = DATA_FILE) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in data_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        rows.append({"text": record["text"].strip(), "label": record["label"].strip()})
    return rows


def stratified_split(
    rows: list[dict[str, str]], seed: int = 42
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Deterministic 70/15/15 stratified split. Test data is never trained on."""
    labels = [r["label"] for r in rows]
    first = StratifiedShuffleSplit(n_splits=1, test_size=1.0 - TRAIN_FRACTION, random_state=seed)
    train_idx, temp_idx = next(first.split(rows, labels))
    temp_labels = [labels[i] for i in temp_idx]
    second = StratifiedShuffleSplit(
        n_splits=1, test_size=TEST_FRACTION / (VAL_FRACTION + TEST_FRACTION), random_state=seed
    )
    val_rel, test_rel = next(second.split(temp_idx, temp_labels))
    train = [rows[i] for i in train_idx]
    val = [rows[temp_idx[i]] for i in val_rel]
    test = [rows[temp_idx[i]] for i in test_rel]
    return train, val, test


def texts_and_ids(
    rows: list[dict[str, str]], mapping: dict[str, int]
) -> tuple[list[str], list[int]]:
    return [r["text"] for r in rows], [mapping[r["label"]] for r in rows]


def default_config() -> ClassifierConfig:
    return ClassifierConfig()
