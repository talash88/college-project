"""Sentence-Transformer singleton (all-MiniLM-L6-v2, 384-dim).

Loaded once per process, lazily. MPS when available, else CPU. Never CUDA-assumed.
"""

import threading
from typing import Any

from app.core.config import settings


def select_st_device() -> str:
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


class EmbeddingModelUnavailableError(RuntimeError):
    pass


_model = None
_lock = threading.Lock()


def get_embedding_model() -> Any:
    """Process-wide singleton SentenceTransformer (384-dim, normalized on encode)."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise EmbeddingModelUnavailableError(
                        "sentence-transformers is not installed"
                    ) from exc
                try:
                    _model = SentenceTransformer(
                        settings.SKILL_EMBEDDING_MODEL, device=select_st_device()
                    )
                except Exception as exc:
                    raise EmbeddingModelUnavailableError(
                        f"could not load embedding model {settings.SKILL_EMBEDDING_MODEL}: {exc}"
                    ) from exc
    return _model


def reset_embedding_singleton() -> None:
    global _model
    with _lock:
        _model = None


def embedding_dimension() -> int:
    return 384
