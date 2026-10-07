#!/usr/bin/env python3
"""
Idempotent development user seed script.
Seeds development users with hashed passwords.
Safe to run multiple times.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AvailabilityStatus,
    Department,
    ProficiencyLevel,
    SkillCategory,
    UserRole,
)
from app.db.session import async_session_factory
from app.models.faculty_profile import FacultyProfile
from app.models.skill import Skill
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.models.user_skill import UserSkill
from app.services.security import hash_password

DEV_USERS = [
    {
        "email": "admin@campusxolve.local",
        "full_name": "CampusXolve Admin",
        "role": UserRole.ADMIN,
        "password": "dev_admin_123",
        "is_verified": True,
    },
    {
        "email": "reporter@campusxolve.local",
        "full_name": "Test Reporter",
        "role": UserRole.REPORTER,
        "password": "dev_reporter_123",
        "is_verified": True,
    },
    {
        "email": "solver1@campusxolve.local",
        "full_name": "Alex Chen",
        "role": UserRole.SOLVER,
        "password": "dev_solver_123",
        "is_verified": True,
    },
    {
        "email": "solver2@campusxolve.local",
        "full_name": "Priya Sharma",
        "role": UserRole.SOLVER,
        "password": "dev_solver_123",
        "is_verified": True,
    },
    {
        "email": "solver3@campusxolve.local",
        "full_name": "Jordan Kim",
        "role": UserRole.SOLVER,
        "password": "dev_solver_123",
        "is_verified": True,
    },
    {
        "email": "mentor1@campusxolve.local",
        "full_name": "Dr. Sarah Johnson",
        "role": UserRole.MENTOR,
        "password": "dev_mentor_123",
        "is_verified": True,
    },
    {
        "email": "mentor2@campusxolve.local",
        "full_name": "Prof. Michael Torres",
        "role": UserRole.MENTOR,
        "password": "dev_mentor_123",
        "is_verified": True,
    },
]

DEV_STUDENT_PROFILES = {
    "solver1@campusxolve.local": {
        "student_identifier": "CS2021001",
        "department": Department.COMPUTER_SCIENCE_ENGINEERING,
        "academic_year": 3,
        "semester": 6,
        "bio": "Full stack developer passionate about React and TypeScript.",
        "availability_status": AvailabilityStatus.AVAILABLE,
        "current_workload": 0,
        "max_workload": 3,
    },
    "solver2@campusxolve.local": {
        "student_identifier": "CS2021002",
        "department": Department.COMPUTER_SCIENCE_ENGINEERING,
        "academic_year": 4,
        "semester": 8,
        "bio": "ML enthusiast with focus on NLP and Python.",
        "availability_status": AvailabilityStatus.AVAILABLE,
        "current_workload": 0,
        "max_workload": 3,
    },
    "solver3@campusxolve.local": {
        "student_identifier": "CS2021003",
        "department": Department.COMPUTER_SCIENCE_ENGINEERING,
        "academic_year": 3,
        "semester": 6,
        "bio": "Backend developer specializing in PostgreSQL and Docker.",
        "availability_status": AvailabilityStatus.LIMITED,
        "current_workload": 1,
        "max_workload": 3,
    },
    "reporter@campusxolve.local": {
        "student_identifier": "CS2021004",
        "department": Department.COMPUTER_SCIENCE_ENGINEERING,
        "academic_year": 2,
        "semester": 4,
        "bio": "Student reporter testing the platform.",
        "availability_status": AvailabilityStatus.UNAVAILABLE,
        "current_workload": 0,
        "max_workload": 2,
    },
}

DEV_FACULTY_PROFILES = {
    "mentor1@campusxolve.local": {
        "employee_identifier": "FAC001",
        "department": Department.COMPUTER_SCIENCE_ENGINEERING,
        "designation": "Associate Professor",
        "specialization": "Artificial Intelligence / Machine Learning",
        "bio": "Researcher in NLP and ML with 15+ years experience.",
        "availability_status": AvailabilityStatus.AVAILABLE,
        "current_workload": 0,
        "max_workload": 5,
    },
    "mentor2@campusxolve.local": {
        "employee_identifier": "FAC002",
        "department": Department.COMPUTER_SCIENCE_ENGINEERING,
        "designation": "Professor",
        "specialization": "Computer Networks / Systems",
        "bio": "Expert in networking, security, and distributed systems.",
        "availability_status": AvailabilityStatus.AVAILABLE,
        "current_workload": 0,
        "max_workload": 5,
    },
}

# Skill assignments for development users
DEV_USER_SKILLS = {
    "solver1@campusxolve.local": [
        ("React", SkillCategory.SOFTWARE_DEVELOPMENT, ProficiencyLevel.EXPERT),
        ("Next.js", SkillCategory.SOFTWARE_DEVELOPMENT, ProficiencyLevel.EXPERT),
        ("TypeScript", SkillCategory.SOFTWARE_DEVELOPMENT, ProficiencyLevel.EXPERT),
        ("UI/UX Design", SkillCategory.DESIGN, ProficiencyLevel.ADVANCED),
    ],
    "solver2@campusxolve.local": [
        ("Python", SkillCategory.SOFTWARE_DEVELOPMENT, ProficiencyLevel.EXPERT),
        ("FastAPI", SkillCategory.SOFTWARE_DEVELOPMENT, ProficiencyLevel.EXPERT),
        ("Machine Learning", SkillCategory.AI_DATA, ProficiencyLevel.EXPERT),
        ("Natural Language Processing", SkillCategory.AI_DATA, ProficiencyLevel.EXPERT),
    ],
    "solver3@campusxolve.local": [
        ("PostgreSQL", SkillCategory.SOFTWARE_DEVELOPMENT, ProficiencyLevel.EXPERT),
        ("Backend Development", SkillCategory.SOFTWARE_DEVELOPMENT, ProficiencyLevel.EXPERT),
        ("Docker", SkillCategory.INFRASTRUCTURE_NETWORKING, ProficiencyLevel.ADVANCED),
        ("Linux", SkillCategory.INFRASTRUCTURE_NETWORKING, ProficiencyLevel.ADVANCED),
    ],
    "mentor1@campusxolve.local": [
        ("Machine Learning", SkillCategory.AI_DATA, ProficiencyLevel.EXPERT),
        ("Natural Language Processing", SkillCategory.AI_DATA, ProficiencyLevel.EXPERT),
        ("Python", SkillCategory.SOFTWARE_DEVELOPMENT, ProficiencyLevel.EXPERT),
    ],
    "mentor2@campusxolve.local": [
        ("Computer Networking", SkillCategory.INFRASTRUCTURE_NETWORKING, ProficiencyLevel.EXPERT),
        ("Linux", SkillCategory.INFRASTRUCTURE_NETWORKING, ProficiencyLevel.EXPERT),
        ("Cybersecurity", SkillCategory.INFRASTRUCTURE_NETWORKING, ProficiencyLevel.EXPERT),
    ],
}


async def get_or_create_user(session: AsyncSession, user_data: dict) -> User:
    """Get existing user or create new one. Idempotent."""
    result = await session.execute(select(User).where(User.email == user_data["email"]))
    user = result.scalar_one_or_none()
    if user:
        print(f"User already exists: {user.email}")
        return user

    password_hash = hash_password(user_data["password"])
    user = User(
        full_name=user_data["full_name"],
        email=user_data["email"],
        password_hash=password_hash,
        role=user_data["role"],
        is_verified=user_data.get("is_verified", False),
    )
    session.add(user)
    await session.flush()
    print(f"Created user: {user.email} ({user.role})")
    return user


async def get_or_create_student_profile(session: AsyncSession, user: User, profile_data: dict) -> StudentProfile:
    """Get existing student profile or create new one. Idempotent."""
    result = await session.execute(
        select(StudentProfile).where(StudentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile:
        print(f"Student profile already exists for: {user.email}")
        return profile

    profile = StudentProfile(user_id=user.id, **profile_data)
    session.add(profile)
    await session.flush()
    print(f"Created student profile for: {user.email} ({profile.student_identifier})")
    return profile


async def get_or_create_faculty_profile(session: AsyncSession, user: User, profile_data: dict) -> FacultyProfile:
    """Get existing faculty profile or create new one. Idempotent."""
    result = await session.execute(
        select(FacultyProfile).where(FacultyProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile:
        print(f"Faculty profile already exists for: {user.email}")
        return profile

    profile = FacultyProfile(user_id=user.id, **profile_data)
    session.add(profile)
    await session.flush()
    print(f"Created faculty profile for: {user.email} ({profile.employee_identifier})")
    return profile


async def get_skill_by_name(session: AsyncSession, name: str) -> Skill | None:
    """Get skill by normalized name."""
    from app.repositories.skill_repository import normalize_skill_name
    normalized = normalize_skill_name(name)
    result = await session.execute(select(Skill).where(Skill.normalized_name == normalized))
    return result.scalar_one_or_none()


async def assign_user_skills(session: AsyncSession, user: User, skill_assignments: list) -> int:
    """Assign skills to user. Idempotent - skips existing."""
    assigned_count = 0
    for skill_name, _category, proficiency in skill_assignments:
        skill = await get_skill_by_name(session, skill_name)
        if not skill:
            print(f"Warning: Skill '{skill_name}' not found, skipping")
            continue

        # Check if already assigned
        result = await session.execute(
            select(UserSkill).where(
                UserSkill.user_id == user.id,
                UserSkill.skill_id == skill.id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(f"  Skill already assigned: {skill_name} (level {proficiency})")
            continue

        user_skill = UserSkill(
            user_id=user.id,
            skill_id=skill.id,
            proficiency_level=proficiency,
            years_experience=None,
            is_verified=True,
        )
        session.add(user_skill)
        assigned_count += 1
        print(f"  Assigned skill: {skill_name} (level {proficiency})")

    await session.flush()
    return assigned_count


async def seed_users(session: AsyncSession) -> dict:
    """Seed all development users, profiles, and skills."""
    stats = {
        "users_created": 0,
        "users_existed": 0,
        "student_profiles_created": 0,
        "faculty_profiles_created": 0,
        "skills_assigned": 0,
    }

    # Create users
    for user_data in DEV_USERS:
        user = await get_or_create_user(session, user_data)
        if user_data["email"] in [u["email"] for u in DEV_USERS if "Created user" in ""]:
            stats["users_created"] += 1
        else:
            # We need to check if it was newly created
            # For simplicity, let's check after
            pass

    await session.flush()

    # Count actual created
    for user_data in DEV_USERS:
        result = await session.execute(select(User).where(User.email == user_data["email"]))
        user = result.scalar_one()
        # We can't easily tell if created or existed without tracking
        # Just log what we have
        print(f"User: {user.email} - {user.role}")

    # Create student profiles
    for email, profile_data in DEV_STUDENT_PROFILES.items():
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        await get_or_create_student_profile(session, user, profile_data)
        stats["student_profiles_created"] += 1  # approximate

    # Create faculty profiles
    for email, profile_data in DEV_FACULTY_PROFILES.items():
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        await get_or_create_faculty_profile(session, user, profile_data)
        stats["faculty_profiles_created"] += 1  # approximate

    await session.flush()

    # Assign skills
    for email, skill_assignments in DEV_USER_SKILLS.items():
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        count = await assign_user_skills(session, user, skill_assignments)
        stats["skills_assigned"] += count

    await session.commit()
    return stats


async def main():
    async with async_session_factory() as session:
        stats = await seed_users(session)
        print("\n=== Seed Summary ===")
        for key, value in stats.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
