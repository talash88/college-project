#!/usr/bin/env python3
"""Step 17: safe demo reset — removes ONLY demo-marker records.

Deletes users whose email starts with `demo.` (the seed_demo.py marker) and
lets ORM/DB cascades remove their problems graph. Everything else
(seeds, genuine users, other problems) is preserved.

Usage:
    python3 scripts/reset_demo.py           # dry-run (default)
    python3 scripts/reset_demo.py --apply  # actually delete

Refuses protected databases without --allow-dev (same rule as seed_demo.py).
Fresher alternative: drop + recreate the demo database and re-run seed_demo.py.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

PROTECTED_DB_NAMES = {"campusxolve", "campusxolve_test"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the demo environment (dry-run default).")
    parser.add_argument("--database-url", default=os.environ.get(
        "DEMO_DATABASE_URL",
        "postgresql+asyncpg://campusxolve:campusxolve@localhost:5432/campusxolve_demo"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-dev", action="store_true")
    args = parser.parse_args()

    name = (urlparse(args.database_url).path or "/").lstrip("/").split("?")[0]
    if name in PROTECTED_DB_NAMES and not args.allow_dev:
        print(f"Refusing to reset protected database '{name}' without --allow-dev.")
        return 2

    os.environ["DATABASE_URL"] = args.database_url

    from sqlalchemy import select, text  # noqa: E402

    from app.db.session import async_session_factory  # noqa: E402
    from app.models.problem import Problem  # noqa: E402
    from app.models.problem_duplicate import DuplicateCluster  # noqa: E402
    from app.models.user import User  # noqa: E402

    async def plan() -> None:
        async with async_session_factory() as s:
            users = (await s.execute(
                select(User).where(User.email.like("demo.%")))).scalars().all()
            ids = [u.id for u in users]
            probs = []
            if ids:
                probs = (await s.execute(
                    select(Problem).where(Problem.reporter_id.in_(ids)))).scalars().all()
            # Clusters die with their demo problems (members cascade; canonical
            # SET NULLs into a hollow shell), so collect demo-linked clusters
            # BEFORE deleting users: canonical demo-owned, any demo member, or
            # already-hollow shells. Never touch clusters of kept problems.
            from sqlalchemy import bindparam  # noqa: E402
            demo_pids = [p.id for p in probs]
            linked: dict[str, object] = {}
            if demo_pids:
                param = {"ids": demo_pids}
                for row in (await s.execute(select(DuplicateCluster).where(
                        DuplicateCluster.canonical_problem_id.in_(demo_pids)))).scalars().all():
                    linked[str(row.id)] = row
                mem_rows = (await s.execute(text(
                    "SELECT DISTINCT cluster_id FROM duplicate_cluster_members "
                    "WHERE problem_id IN :ids").bindparams(
                        bindparam("ids", expanding=True)), param)).all()
                mem_ids = [r[0] for r in mem_rows]
                if mem_ids:
                    for row in (await s.execute(select(DuplicateCluster).where(
                            DuplicateCluster.id.in_(mem_ids)))).scalars().all():
                        linked[str(row.id)] = row
            empty_clusters = (await s.execute(select(DuplicateCluster).where(
                DuplicateCluster.canonical_problem_id.is_(None)))).scalars().all()
            if empty_clusters:
                counts = (await s.execute(text(
                    "SELECT cluster_id, count(*) FROM duplicate_cluster_members "
                    "WHERE cluster_id IN :ids GROUP BY cluster_id").bindparams(
                        bindparam("ids", expanding=True)),
                    {"ids": [c.id for c in empty_clusters]}))
                with_members = {str(r[0]) for r in counts.all()}
                for c in empty_clusters:
                    if str(c.id) not in with_members:
                        linked[str(c.id)] = c
            orphans = list(linked.values())
            mode = "APPLY (deleting)" if args.apply else "DRY-RUN (no changes)"
            print(f"=== Demo reset [{mode}] on '{name}' ===")
            print(f"Demo users: {len(users)}")
            for u in users:
                print(f"  {u.email} | {u.full_name} | {u.role}")
            print(f"Demo-reported problems: {len(probs)}")
            for p in probs:
                print(f"  {p.ticket_number} | {p.status} | {p.title[:60]}")
            print(f"Demo-linked/orphan clusters: {len(orphans)}")
            for c in orphans:
                print(f"  {c.cluster_number}")
            if not args.apply:
                print("Dry-run complete. Re-run with --apply to delete.")
                return
            for u in users:
                await s.delete(u)
            for c in orphans:
                await s.delete(c)
            # Restart demo ticket numbering so a re-seed starts at CX-YYYY-000001.
            await s.execute(text("DELETE FROM ticket_counters"))
            await s.commit()
            print(f"Deleted {len(users)} demo users (+ cascaded graph), "
                  f"{len(orphans)} orphan clusters; ticket counters reset.")

    asyncio.run(plan())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
