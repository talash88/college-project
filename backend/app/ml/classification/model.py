"""Device selection + model construction (DistilBERT + classification head)."""

import random

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def select_device() -> torch.device:
    """Prefer Apple Silicon MPS when available, else CPU. Never assume CUDA."""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.backends.mps.is_available():
        torch.mps.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def build_tokenizer(base_model: str):  # type: ignore[no-untyped-def]
    return AutoTokenizer.from_pretrained(base_model)


def build_model(base_model: str, num_labels: int):  # type: ignore[no-untyped-def]
    return AutoModelForSequenceClassification.from_pretrained(base_model, num_labels=num_labels)
