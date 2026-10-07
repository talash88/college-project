"""DistilBERT campus problem classifier: text → tokenizer → encoder → head → softmax."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClassifierConfig:
    base_model: str = "distilbert-base-uncased"
    model_version: str = "campusxolve-problem-classifier-v1"
    dataset_version: str = "problem_classification_v1"
    seed: int = 42
    max_length: int = 256
    train_epochs: int = 8
    train_batch_size: int = 16
    eval_batch_size: int = 32
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    confidence_threshold: float = 0.60
    labels: tuple[str, ...] = field(
        default=(
            "ACADEMIC",
            "CLEANLINESS_SANITATION",
            "ELECTRICAL",
            "HOSTEL",
            "INFRASTRUCTURE",
            "IT_NETWORK",
            "LABORATORY",
            "LIBRARY",
            "OTHER",
            "SAFETY_SECURITY",
            "TRANSPORT",
            "WATER_SANITATION",
        )
    )


def format_input(title: str, description: str, location: str | None = None) -> str:
    """Deterministic combined input: title + description + optional location.

    Only report content is used — no user metadata, no sensitive fields.
    """
    parts = [f"Title: {title.strip()}", f"Description: {description.strip()}"]
    if location and location.strip():
        parts.append(f"Location: {location.strip()}")
    return "\n".join(parts)
