"""Transparent fine-tuning loop (explicit PyTorch; no hidden training on val/test)."""

import copy
import math
import time
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader, Dataset

from app.ml.classification.config import ClassifierConfig
from app.ml.classification.metrics import compute_metrics
from app.ml.classification.model import build_model, build_tokenizer, select_device, set_seed


class TextDataset(Dataset):  # type: ignore[misc]
    def __init__(self, texts: list[str], ids: list[int], tokenizer: Any, max_length: int) -> None:
        self.encodings = tokenizer(texts, truncation=True, padding=True, max_length=max_length)
        self.ids = ids

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        return {
            "input_ids": torch.tensor(self.encodings["input_ids"][idx]),
            "attention_mask": torch.tensor(self.encodings["attention_mask"][idx]),
            "labels": torch.tensor(self.ids[idx]),
        }


def evaluate(model: Any, loader: Any, device: Any) -> tuple[list[int], list[int]]:
    model.eval()
    truth: list[int] = []
    preds: list[int] = []
    with torch.inference_mode():
        for batch in loader:
            inputs = {k: v.to(device) for k, v in batch.items() if k != "labels"}
            logits = model(**inputs).logits
            preds.extend(torch.argmax(logits, dim=-1).cpu().tolist())
            truth.extend(batch["labels"].cpu().tolist())
    return truth, preds


def train(
    config: ClassifierConfig,
    train_texts: list[str],
    train_ids: list[int],
    val_texts: list[str],
    val_ids: list[int],
    output_dir: Path,
) -> dict[str, object]:
    """Fine-tune on TRAIN only; validate each epoch; keep best val macro-F1."""
    set_seed(config.seed)
    device = select_device()
    tokenizer = build_tokenizer(config.base_model)
    model = build_model(config.base_model, len(config.labels))
    model.to(device)

    train_loader = DataLoader(
        TextDataset(train_texts, train_ids, tokenizer, config.max_length),
        batch_size=config.train_batch_size,
        shuffle=True,
    )
    val_loader = DataLoader(
        TextDataset(val_texts, val_ids, tokenizer, config.max_length),
        batch_size=config.eval_batch_size,
    )

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    total_steps = len(train_loader) * config.train_epochs
    warmup_steps = max(1, int(total_steps * config.warmup_ratio))

    def lr_for(step: int) -> float:
        if step < warmup_steps:
            return config.learning_rate * step / warmup_steps
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        return config.learning_rate * 0.5 * (1.0 + math.cos(math.pi * progress))

    best_f1 = -1.0
    best_state = None
    history: list[dict[str, object]] = []
    started = time.time()
    step = 0
    for epoch in range(1, config.train_epochs + 1):
        model.train()
        epoch_loss = 0.0
        for batch in train_loader:
            step += 1
            for group in optimizer.param_groups:
                group["lr"] = lr_for(step)
            optimizer.zero_grad()
            inputs = {k: v.to(device) for k, v in batch.items()}
            loss = model(**inputs).loss
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        truth, preds = evaluate(model, val_loader, device)
        val_metrics = compute_metrics(truth, preds, list(config.labels))
        val_f1 = float(val_metrics["macro_f1"])
        history.append(
            {
                "epoch": epoch,
                "train_loss": round(epoch_loss / len(train_loader), 4),
                "val_macro_f1": val_f1,
                "val_accuracy": val_metrics["accuracy"],
            }
        )
        print(
            f"epoch {epoch}/{config.train_epochs} loss={epoch_loss / len(train_loader):.4f} val_acc={val_metrics['accuracy']:.4f} val_macro_f1={val_f1:.4f}",
            flush=True,
        )
        if val_f1 > best_f1:
            best_f1 = val_f1
            best_state = copy.deepcopy(model.state_dict())

    if best_state is not None:
        model.load_state_dict(best_state)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    elapsed = round(time.time() - started, 1)
    return {
        "device": str(device),
        "best_val_macro_f1": round(best_f1, 4),
        "history": history,
        "seconds": elapsed,
    }
