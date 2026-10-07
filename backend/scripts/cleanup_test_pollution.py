#!/usr/bin/env python3
"""Safe cleanup of pytest/smoke-test pollution in the development database.

Deletes ONLY records confidently identifiable as test pollution:
- users whose email ends with @example.com AND who are not referenced by any
  remaining problem's workflow graph (reporters/team/mentors/recommendees/
  commenters/activity actors of kept problems are protected as demo data)
- duplicate clusters with no members and no canonical problem

ALWAYS preserves:
- the 7 official seeded development accounts (@campusxolve.local)
- any genuine non-test account (e.g. real Gmail registrations)
- all problems, attachments, and populated clusters

Usage:
    python scripts/cleanup_test_pollution.py           # dry-run (default)
    python scripts/cleanup_test_pollution.py --dry-run # dry-run (explicit)
    python scripts/cleanup_test_pollution.py --apply    # actually delete

Refuses to run when DATABASE_URL points at the test database.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy import delete, func, select  # noqa: E402

from app.db.session import async_session_factory  # noqa: E402
from app.models.problem_duplicate import DuplicateCluster  # noqa: E402
from app.models.user import User  # noqa: E402

DEV_EMAILS = {
    "admin@campusxolve.local",
    "reporter@campusxolve.local",
    "solver1@campusxolve.local",
    "solver2@campusxolve.local",
    "solver3@campusxolve.local",
    "mentor1@campusxolve.local",
    "mentor2@campusxolve.local",
}

# (table, column) pairs whose non-null values mark users as demo-referenced.
REFERENCE_COLUMNS: list[tuple[str, str]] = [
    ("problems", "reporter_id"),
    ("problems", "reviewed_by"),
    ("problems", "approved_by"),
    ("problem_team_members", "user_id"),
    ("problem_assignments", "mentor_user_id"),
    ("team_recommendation_members", "user_id"),
    ("mentor_recommendations", "mentor_user_id"),
    ("problem_comments", "author_id"),
    ("problem_activities", "actor_user_id"),
    ("problem_duplicate_candidates", "reviewed_by"),
]


async def referenced_user_ids(session) -> set:
    """User ids reachable from any remaining problem workflow row."""
    from sqlalchemy import text

    refs: set = set()
    for table, column in REFERENCE_COLUMNS:
        rows = await session.execute(
            text(f"SELECT DISTINCT {column} AS u FROM {table} WHERE {column} IS NOT NULL")
        )
        refs.update(r[0] for r in rows.all())
    return {str(u) for u in refs}


async def classify(session) -> dict:
    from sqlalchemy import text

    dev_count = (
        await session.execute(select(func.count()).select_from(User).where(User.email.in_(DEV_EMAILS)))
    ).scalar_one()

    genuine = (
        await session.execute(
            select(User.id, User.email, User.full_name)
            .where(~User.email.like("%@example.com"))
            .where(~User.email.in_(DEV_EMAILS))
            .order_by(User.email)
        )
    ).all()

    refs = await referenced_user_ids(session)

    candidates = (
        await session.execute(
            select(User.id, User.email, User.full_name)
            .where(User.email.like("%@example.com"))
            .order_by(User.email)
        )
    ).all()
    protected = [u for u in candidates if str(u.id) in refs]
    deletable = [u for u in candidates if str(u.id) not in refs]

    clusters_total = (await session.execute(select(func.count()).select_from(DuplicateCluster))).scalar_one()
    empty_clusters = (
        await session.execute(
            select(DuplicateCluster.id, DuplicateCluster.cluster_number).where(
                DuplicateCluster.canonical_problem_id.is_(None),
                ~DuplicateCluster.members.any(),
            )
        )
    ).all()
    # Double-check member counts directly (relationship `any()` guard above).
    member_counts = await session.execute(
        text(
            "SELECT c.id FROM duplicate_clusters c "
            "LEFT JOIN duplicate_cluster_members m ON m.cluster_id = c.id "
            "WHERE c.canonical_problem_id IS NULL "
            "GROUP BY c.id HAVING COUNT(m.problem_id) = 0"
        )
    )
    empty_ids = {str(r[0]) for r in member_counts.all()}
    orphan_clusters = [c for c in empty_clusters if str(c.id) in empty_ids]

    problems = (await session.execute(select(func.count()).select_from(text("problems")))).scalar_one()

    return {
        "dev_count": dev_count,
        "genuine": genuine,
        "protected_demo": protected,
        "deletable_users": deletable,
        "clusters_total": clusters_total,
        "orphan_clusters": orphan_clusters,
        "problems": problems,
    }


def report(plan: dict, dry_run: bool) -> None:
    mode = "DRY-RUN (no changes)" if dry_run else "APPLY (deleting)"
    print(f"=== Test-pollution cleanup [{mode}] ===")
    print(f"Seeded dev accounts present: {plan['dev_count']} (expected 7, preserved)")
    print(f"Genuine non-test accounts: {len(plan['genuine'])} (preserved)")
    for u in plan["genuine"]:
        print(f"  KEEP genuine: {u.email} | {u.full_name}")
    print(f"Demo-referenced @example.com users: {len(plan['protected_demo'])} (preserved)")
    for u in plan["protected_demo"]:
        print(f"  KEEP demo-referenced: {u.email} | {u.full_name}")
    print(f"Unreferenced @example.com users to delete: {len(plan['deletable_users'])}")
    for u in plan["deletable_users"][:15]:
        print(f"  DELETE user: {u.email} | {u.full_name}")
    if len(plan["deletable_users"]) > 15:
        print(f"  ... and {len(plan['deletable_users']) - 15} more")
    print(f"Duplicate clusters total: {plan['clusters_total']}; "
          f"empty orphans to delete: {len(plan['orphan_clusters'])}")
    for c in plan["orphan_clusters"][:10]:
        print(f"  DELETE cluster: {c.cluster_number}")
    if len(plan["orphan_clusters"]) > 10:
        print(f"  ... and {len(plan['orphan_clusters']) - 10} more")
    print(f"Problems (all preserved): {plan['problems']}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Clean test pollution (dry-run by default).")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted (default).")
    parser.add_argument("--apply", action="store_true", help="Actually delete the classified records.")
    args = parser.parse_args()
    dry_run = not args.apply

    from app.core.config import settings

    if "campusxolve_test" in settings.DATABASE_URL:
        print("Refusing to run cleanup against the test database.")
        return 2

    async with async_session_factory() as session:
        plan = await classify(session)
        report(plan, dry_run)
        if dry_run:
            await session.rollback()
            print("\nDry-run complete. Re-run with --apply to delete.")
            return 0
        user_ids = [u.id for u in plan["deletable_users"]]
        cluster_ids = [c.id for c in plan["orphan_clusters"]]
        if cluster_ids:
            await session.execute(
                delete(DuplicateCluster).where(DuplicateCluster.id.in_(cluster_ids))
            )
        if user_ids:
            # ORM deletes so relationship cascades fire; DB FKs back them up.
            for uid in user_ids:
                user = await session.get(User, uid)
                if user is not None:
                    await session.delete(user)
        await session.commit()
        print(f"\nDeleted {len(user_ids)} users and {len(cluster_ids)} orphan clusters.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
