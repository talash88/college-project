#!/usr/bin/env python3
"""Backfill problem embeddings for reports missing the current version.

Idempotent: only reports WITHOUT a current-version embedding are touched, so a
safe rerun embeds nothing new (processed=0). Optionally runs duplicate
candidate analysis per backfilled report with --analyze.

Usage:
  python3 scripts/backfill_problem_embeddings.py [--analyze] [--limit 500]
"""

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import async_session_factory  # noqa: E402
from app.services.duplicate_service import DuplicateService  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    processed = 0
    skipped = 0
    failed = 0
    analyzed = 0
    async with async_session_factory() as session:
        service = DuplicateService(session)
        missing = await service.embeddings.missing_problem_ids(
            settings.PROBLEM_EMBEDDING_VERSION, limit=args.limit
        )
        print(f"reports missing embeddings: {len(missing)}")
        backfilled: list[UUID] = []
        for problem_id in missing:
            problem = await service.problems.get_by_id(UUID(str(problem_id)))
            if problem is None:
                skipped += 1
                continue
            try:
                await service.ensure_embedding(problem)
                processed += 1
                backfilled.append(problem.id)
            except Exception as exc:
                failed += 1
                print(f"  {problem_id}: FAILED ({type(exc).__name__})")
        print(f"processed={processed} skipped={skipped} failed={failed}")
        if args.analyze:
            analyze_failed = 0
            for problem_id in backfilled:
                problem = await service.problems.get_by_id(UUID(str(problem_id)))
                if problem is None:
                    skipped += 1
                    continue
                try:
                    await service.analyze(problem)
                    analyzed += 1
                except Exception as exc:
                    analyze_failed += 1
                    print(f"  {problem_id}: analysis FAILED ({type(exc).__name__})")
            print(f"analyzed={analyzed} analyze_failed={analyze_failed}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
