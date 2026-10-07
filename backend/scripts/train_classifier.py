#!/usr/bin/env python3
"""Fine-tune DistilBERT on the campus complaint dataset.

Reproducible: fixed seed, stratified split, best-val checkpoint.
Saves: model + tokenizer + label_map.json + config.json + metadata.json +
val metrics. Test metrics come from scripts/evaluate_classifier.py.

Usage: python3 scripts/train_classifier.py [--epochs 8] [--seed 42]
"""

import argparse
import datetime
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
from app.ml.classification.metrics import compute_metrics  # noqa: E402
from app.ml.classification.model import build_tokenizer  # noqa: E402
from app.ml.classification.trainer import evaluate, train  # noqa: E402

ARTIFACT_DIR = BACKEND_ROOT / "ml" / "artifacts" / "problem_classifier"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=str, default=str(ARTIFACT_DIR))
    args = parser.parse_args()

    config = ClassifierConfig(train_epochs=args.epochs, seed=args.seed)
    rows = load_rows()
    mapping = label_to_id(config.labels)
    unknown = {r["label"] for r in rows} - set(config.labels)
    if unknown:
        print(f"ERROR: labels outside taxonomy: {sorted(unknown)}")
        return 1
    train_rows, val_rows, test_rows = stratified_split(rows, seed=config.seed)
    train_texts, train_ids = texts_and_ids(train_rows, mapping)
    val_texts, val_ids = texts_and_ids(val_rows, mapping)
    print(f"train={len(train_rows)} val={len(val_rows)} test={len(test_rows)} (test held out)")
    print(f"base={config.base_model} epochs={config.train_epochs} seed={config.seed}")

    output = Path(args.output)
    summary = train(config, train_texts, train_ids, val_texts, val_ids, output)

    # Final validation metrics on the saved (best) checkpoint.
    from torch.utils.data import DataLoader
    from transformers import AutoModelForSequenceClassification  # noqa: E402

    from app.ml.classification.model import select_device  # noqa: E402
    from app.ml.classification.trainer import TextDataset  # noqa: E402

    device = select_device()
    tokenizer = build_tokenizer(config.base_model)
    saved = AutoModelForSequenceClassification.from_pretrained(str(output)).to(device)
    val_loader = DataLoader(
        TextDataset(val_texts, val_ids, tokenizer, config.max_length),
        batch_size=config.eval_batch_size,
    )
    truth, preds = evaluate(saved, val_loader, device)
    val_metrics = compute_metrics(truth, preds, list(config.labels))

    (output / "label_map.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    (output / "train_config.json").write_text(
        json.dumps(
            {
                "base_model": config.base_model,
                "model_version": config.model_version,
                "dataset_version": config.dataset_version,
                "seed": config.seed,
                "max_length": config.max_length,
                "train_epochs": config.train_epochs,
                "train_batch_size": config.train_batch_size,
                "learning_rate": config.learning_rate,
                "weight_decay": config.weight_decay,
                "warmup_ratio": config.warmup_ratio,
                "confidence_threshold": config.confidence_threshold,
                "labels": list(config.labels),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (output / "metadata.json").write_text(
        json.dumps(
            {
                "model_name": "campusxolve-problem-classifier",
                "model_version": config.model_version,
                "base_model": config.base_model,
                "trained_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "dataset_version": config.dataset_version,
                "dataset_file": "ml/data/problem_classification_v1.jsonl",
                "train_samples": len(train_rows),
                "val_samples": len(val_rows),
                "test_samples": len(test_rows),
                "seed": config.seed,
                "device": summary["device"],
                "training_seconds": summary["seconds"],
                "history": summary["history"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (output / "metrics_val.json").write_text(json.dumps(val_metrics, indent=2), encoding="utf-8")
    print(f"val accuracy={val_metrics['accuracy']} macro_f1={val_metrics['macro_f1']}")
    print(f"artifacts: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
