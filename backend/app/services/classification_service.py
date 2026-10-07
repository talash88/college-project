"""DistilBERT problem classification service (Step 5).

Loads the fine-tuned transformer once per process, converts logits to
softmax probabilities, persists an audit row per run, and caches the latest
result on the problem. Inference failure never loses a problem report.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ClassificationStatus
from app.ml.classification.config import ClassifierConfig
from app.ml.classification.inference import ModelNotAvailableError, get_classifier
from app.models.problem import Problem
from app.models.problem_classification import ProblemClassification
from app.models.user import User
from app.repositories.problem_repository import ClassificationRepository, ProblemRepository
from app.services.auth_service import AuthError

logger = logging.getLogger(__name__)

MODEL_NAME = "campusxolve-problem-classifier"
# backend/app/services/classification_service.py -> backend/
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def resolve_artifact_dir() -> Path:
    configured = Path(settings.CLASSIFICATION_MODEL_DIR)
    if configured.is_absolute():
        return configured
    return BACKEND_ROOT / configured


def taxonomy_labels() -> tuple[str, ...]:
    return ClassifierConfig().labels


def read_model_version(artifact_dir: Path) -> str:
    train_config = artifact_dir / "train_config.json"
    if train_config.exists():
        try:
            data = json.loads(train_config.read_text(encoding="utf-8"))
            version = data.get("model_version")
            if isinstance(version, str) and version:
                return version
        except (json.JSONDecodeError, OSError):
            pass
    return ClassifierConfig().model_version


class ProblemClassificationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemRepository(session)
        self.classifications = ClassificationRepository(session)
        self.threshold = settings.CLASSIFICATION_CONFIDENCE_THRESHOLD

    def _predict(self, title: str, description: str, location: str | None) -> tuple[str, float]:
        """Run the transformer on plain data (never ORM instances: threads can't lazy-load)."""
        artifact_dir = resolve_artifact_dir()
        classifier = get_classifier(artifact_dir)
        label, confidence, _ = classifier.predict_report(title, description, location)
        if label not in taxonomy_labels():
            raise RuntimeError(f"Model returned uncontrolled label: {label}")
        return label, confidence

    async def _record_failure(self, problem: Problem, reason: str) -> ProblemClassification:
        logger.warning("classification failed for problem %s: %s", problem.id, reason)
        row = await self.classifications.create(
            problem_id=problem.id,
            predicted_category=None,
            confidence=None,
            model_name=MODEL_NAME,
            model_version=read_model_version(resolve_artifact_dir()),
            status=ClassificationStatus.FAILED,
            requires_manual_review=True,
            classified_at=None,
        )
        problem.predicted_category = None
        problem.classification_confidence = None
        problem.classification_status = ClassificationStatus.FAILED
        await self.session.commit()
        return row

    async def classify(self, problem: Problem) -> ProblemClassification:
        """Classify one persisted problem; failure yields a FAILED row, never an exception."""
        # Snapshot plain values first: the ORM instance must not cross threads.
        title = problem.title
        description = problem.description
        location = problem.location_text
        try:
            label, confidence = await asyncio.to_thread(self._predict, title, description, location)
        except ModelNotAvailableError as exc:
            return await self._record_failure(problem, str(exc))
        except Exception as exc:  # inference must never lose the report
            return await self._record_failure(problem, f"{type(exc).__name__}: {exc}")

        status = (
            ClassificationStatus.COMPLETED
            if confidence >= self.threshold
            else ClassificationStatus.LOW_CONFIDENCE
        )
        row = await self.classifications.create(
            problem_id=problem.id,
            predicted_category=label,
            confidence=confidence,
            model_name=MODEL_NAME,
            model_version=read_model_version(resolve_artifact_dir()),
            status=status,
            requires_manual_review=status != ClassificationStatus.COMPLETED,
            classified_at=datetime.now(UTC),
        )
        problem.predicted_category = label
        problem.classification_confidence = confidence
        problem.classification_status = status
        await self.session.commit()
        return row

    async def classify_new_problem(self, problem_id: UUID) -> ProblemClassification | None:
        """Post-commit hook for problem creation. Returns None only if the problem vanished."""
        problem = await self.problems.get_by_id(problem_id)
        if problem is None:
            logger.warning("classify_new_problem: problem %s not found", problem_id)
            return None
        return await self.classify(problem)

    async def rerun(self, problem_id: UUID) -> ProblemClassification:
        problem = await self.problems.get_by_id(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        return await self.classify(problem)

    async def latest_for(self, problem_id: UUID) -> ProblemClassification | None:
        return await self.classifications.latest_for_problem(problem_id)

    async def history_for(self, problem_id: UUID) -> list[ProblemClassification]:
        return await self.classifications.history_for_problem(problem_id)

    async def review(
        self,
        row: ProblemClassification,
        admin: User,
        *,
        accept: bool,
        final_category: str | None,
        review_note: str | None,
    ) -> ProblemClassification:
        """Human-in-the-loop: original prediction is never modified."""
        if row.status == ClassificationStatus.FAILED or row.predicted_category is None:
            raise AuthError(409, "There is no AI prediction to review yet")
        if accept:
            final = row.predicted_category
        elif final_category and final_category.strip():
            final = final_category.strip()
            if final not in taxonomy_labels():
                raise AuthError(422, f"Unknown category: {final}")
        else:
            raise AuthError(422, "Provide final_category or accept the prediction")
        note = review_note.strip() if review_note and review_note.strip() else None
        if note and len(note) > 1000:
            raise AuthError(422, "Review note is too long")
        row.final_category = final
        row.review_note = note
        row.reviewed_by = admin.id
        row.reviewed_at = datetime.now(UTC)
        row.requires_manual_review = False
        await self.session.commit()
        return row
