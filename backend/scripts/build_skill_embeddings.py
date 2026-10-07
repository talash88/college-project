#!/usr/bin/env python3
"""Build pgvector embeddings for the active skill taxonomy (idempotent).

Upserts on (skill_id, model_version): re-running updates vectors in place
and never creates duplicates. Only active skills are embedded.

Usage: python3 scripts/build_skill_embeddings.py
"""

import asyncio
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import async_session_factory  # noqa: E402
from app.ml.skills.embeddings import embedding_dimension, get_embedding_model  # noqa: E402
from app.ml.skills.taxonomy import representation_text  # noqa: E402
from app.models.problem_analysis import SkillEmbedding  # noqa: E402
from app.models.skill import Skill  # noqa: E402


async def main() -> int:
    started = time.time()
    model = get_embedding_model()
    version = settings.SKILL_EMBEDDING_VERSION
    model_name = settings.SKILL_EMBEDDING_MODEL
    dim = embedding_dimension()

    async with async_session_factory() as session:
        skills = (
            (
                await session.execute(
                    select(Skill).where(Skill.is_active.is_(True)).order_by(Skill.name)
                )
            )
            .scalars()
            .all()
        )
        print(f"active skills: {len(skills)}")
        texts = [representation_text(s.name, s.category.value, s.description) for s in skills]
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        upserted = 0
        for skill, vector in zip(skills, vectors, strict=True):
            existing = (
                (
                    await session.execute(
                        select(SkillEmbedding).where(
                            SkillEmbedding.skill_id == skill.id,
                            SkillEmbedding.model_version == version,
                        )
                    )
                )
                .scalars()
                .first()
            )
            values = [round(float(x), 6) for x in vector.tolist()]
            if existing is None:
                session.add(
                    SkillEmbedding(
                        skill_id=skill.id,
                        model_name=model_name,
                        model_version=version,
                        embedding=values,
                        embedding_dimension=dim,
                    )
                )
            else:
                existing.embedding = values
                existing.model_name = model_name
                existing.embedding_dimension = dim
            upserted += 1
        await session.commit()

    elapsed = round(time.time() - started, 1)
    print(f"upserted={upserted} dim={dim} model={model_name} version={version} seconds={elapsed}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
