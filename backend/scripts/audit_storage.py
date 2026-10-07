#!/usr/bin/env python3
"""Audit attachment storage consistency (report by default, never deletes).

Compares database file rows against files on disk in both directions:

- DB row with no file on disk  -> broken download link (needs attention)
- file on disk with no DB row  -> orphan (safe to remove with --cleanup-orphans)

Usage:
    python scripts/audit_storage.py                 # report only (default)
    python scripts/audit_storage.py --cleanup-orphans  # also delete orphan files

Only orphan *files on disk* are ever deleted, and only with the explicit
flag. Database rows are never touched by this script.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))


async def audit(*, cleanup_orphans: bool) -> int:
    from sqlalchemy import select

    from app.core.config import settings
    from app.db.session import async_session_factory
    from app.models.problem import ProblemAttachment
    from app.models.workspace import ProblemWorkAttachment
    from app.storage.local import resolve_storage_dir

    root = resolve_storage_dir(settings.STORAGE_DIR)
    disk_files = {p.name for p in root.iterdir() if p.is_file()}

    async with async_session_factory() as session:
        db_names: set[str] = set()
        for row in (
            (await session.execute(select(ProblemAttachment.stored_filename))).scalars().all()
        ):
            db_names.add(Path(str(row)).name)
        for row in (
            (await session.execute(select(ProblemWorkAttachment.storage_key))).scalars().all()
        ):
            db_names.add(Path(str(row)).name)

    missing_on_disk = sorted(name for name in db_names if name not in disk_files)
    orphans_on_disk = sorted(name for name in disk_files if name not in db_names)

    print(f"storage dir: {root}")
    print(f"DB file rows: {len(db_names)}; files on disk: {len(disk_files)}")
    print(f"DB rows missing their file: {len(missing_on_disk)}")
    for name in missing_on_disk[:20]:
        print(f"  MISSING: {name}")
    print(f"orphan files on disk: {len(orphans_on_disk)}")
    for name in orphans_on_disk[:20]:
        print(f"  ORPHAN: {name}")

    removed = 0
    if cleanup_orphans:
        for name in orphans_on_disk:
            target = root / name
            # Containment guard: never follow paths outside the storage root.
            if target.parent != root or "/" in name or "\\" in name:
                print(f"  SKIP (unsafe name): {name}")
                continue
            target.unlink(missing_ok=True)
            removed += 1
        print(f"removed {removed} orphan file(s)")
    else:
        print("dry-run: nothing deleted (pass --cleanup-orphans to remove orphans)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit attachment storage consistency.")
    parser.add_argument(
        "--cleanup-orphans",
        action="store_true",
        help="Delete orphan files on disk (DB rows are never touched).",
    )
    args = parser.parse_args()
    return asyncio.run(audit(cleanup_orphans=args.cleanup_orphans))


if __name__ == "__main__":
    raise SystemExit(main())
