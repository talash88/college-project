#!/usr/bin/env python3
"""Backfill the Knowledge Repository from eligible CLOSED problems.

Finds CLOSED problems without a knowledge entry and publishes them through
the same KnowledgeService used by the close hook (idempotent: already
published entries are skipped, repeated runs create nothing new).

Usage:
    python scripts/backfill_knowledge_repository.py          # live run
    python scripts/backfill_knowledge_repository.py --dry-run  # report only

Only CLOSED + mentor-approved + reporter-verified problems publish;
ineligible problems (open, rejected, duplicate members, ...) are reported
as skipped, never fabricated.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill the Knowledge Repository.")
    parser.add_argument("--dry-run", action="store_true", help="Report only, publish nothing.")
    args = parser.parse_args()

    from app.db.session import async_session_factory
    from app.services.knowledge_service import KnowledgeService

    processed = 0
    published = 0
    skipped = 0
    failed: list[str] = []
    async with async_session_factory() as session:
        service = KnowledgeService(session)
        problem_ids = await service.entries.eligible_closed_problem_ids()
        print(f"CLOSED problems without knowledge entries: {len(problem_ids)}")
        for problem_id in problem_ids:
            processed += 1
            if args.dry_run:
                skipped += 1
                continue
            status = await service.publish_for_problem(problem_id)
            if status == "PUBLISHED":
                published += 1
            elif status.startswith("INELIGIBLE") or status in ("ARCHIVED", "NOT_FOUND"):
                skipped += 1
                print(f"  skip {problem_id}: {status}")
            else:
                failed.append(f"{problem_id}: {status}")
                print(f"  FAILED {problem_id}: {status}")
    print(f"processed={processed} published={published} skipped={skipped} failed={len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
