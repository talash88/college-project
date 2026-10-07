"""Single-load inference: logits → softmax → (label, confidence)."""

import json
import threading
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.ml.classification.config import ClassifierConfig, format_input
from app.ml.classification.model import select_device


class ModelNotAvailableError(RuntimeError):
    """Raised when trained artifacts are missing — never faked around."""


class ProblemClassifier:
    """Loads the fine-tuned artifact once; `predict` is safe to call per request."""

    def __init__(self, artifact_dir: Path, config: ClassifierConfig | None = None):
        self.artifact_dir = artifact_dir
        self.config = config or ClassifierConfig()
        self.device = select_device()
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        labels_file = self.artifact_dir / "label_map.json"
        if not self.artifact_dir.exists() or not labels_file.exists():
            raise ModelNotAvailableError(
                f"problem classifier model not installed/trained at {self.artifact_dir}; "
                "run: python3 scripts/train_classifier.py"
            )
        label_map: dict[str, int] = json.loads(labels_file.read_text(encoding="utf-8"))
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(str(self.artifact_dir))
            self.model = AutoModelForSequenceClassification.from_pretrained(str(self.artifact_dir))
        except Exception as exc:
            raise ModelNotAvailableError(f"could not load classifier artifact: {exc}") from exc
        self.model.to(self.device)
        self.model.eval()
        self.id_to_label = {idx: label for label, idx in label_map.items()}

    @property
    def labels(self) -> list[str]:
        return [self.id_to_label[i] for i in sorted(self.id_to_label)]

    def predict(self, text: str) -> tuple[str, float, list[float]]:
        """Returns (predicted_label, softmax_confidence, all_probabilities)."""
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Cannot classify empty text")
        encoded = self.tokenizer(
            cleaned,
            truncation=True,
            max_length=self.config.max_length,
            return_tensors="pt",
        )
        with torch.inference_mode(), self._lock:
            inputs = {k: v.to(self.device) for k, v in encoded.items()}
            logits = self.model(**inputs).logits
        probs = F.softmax(logits, dim=-1).squeeze(0).cpu().tolist()
        if isinstance(probs, float):  # pragma: no cover - single-class guard
            probs = [probs]
        best = max(range(len(probs)), key=lambda i: probs[i])
        prob_list: list[float] = [float(p) for p in probs]
        return self.id_to_label[best], prob_list[best], prob_list

    def predict_report(
        self, title: str, description: str, location: str | None = None
    ) -> tuple[str, float, list[float]]:
        return self.predict(format_input(title, description, location))


_classifier: ProblemClassifier | None = None
_classifier_lock = threading.Lock()


def get_classifier(artifact_dir: Path) -> ProblemClassifier:
    """Process-wide singleton: the transformer loads exactly once."""
    global _classifier
    if _classifier is None:
        with _classifier_lock:
            if _classifier is None:
                _classifier = ProblemClassifier(artifact_dir)
    return _classifier


def reset_classifier_singleton() -> None:
    """Test helper: drop the cached singleton so a new artifact dir can load."""
    global _classifier
    with _classifier_lock:
        _classifier = None
