#!/usr/bin/env python3
"""
Idempotent skill seed script.
Seeds the CampusXolve AI skill taxonomy.
Safe to run multiple times.
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.services.skill_service import SkillService


async def seed_skills(session: AsyncSession) -> int:
    """Seed skills. Returns count of skills in database after seeding."""
    service = SkillService(session)
    seeded = await service.seed_skills()
    print(f"Seeded/verified {len(seeded)} skills")
    return len(seeded)


async def main():
    async with async_session_factory() as session:
        count = await seed_skills(session)
        print(f"Total skills in database: {count}")


if __name__ == "__main__":
    asyncio.run(main())
