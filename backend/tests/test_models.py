from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.enums import AvailabilityStatus, Department, ProficiencyLevel, SkillCategory, UserRole
from app.models.faculty_profile import FacultyProfile
from app.models.skill import Skill
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.models.user_skill import UserSkill


@pytest.mark.asyncio
async def test_user_model_creation(db_session):
    user = User(
        full_name="Test User",
        email=f"test_{uuid4()}@example.com",
        password_hash="hashed_password",
        role=UserRole.SOLVER,
    )
    db_session.add(user)
    await db_session.flush()

    assert user.id is not None
    assert user.full_name == "Test User"
    assert user.role == UserRole.SOLVER
    assert user.is_active is True
    assert user.is_verified is False
    assert user.created_at is not None
    assert user.updated_at is not None


@pytest.mark.asyncio
async def test_user_email_unique_constraint(db_session):
    email = f"duplicate_{uuid4()}@example.com"
    user1 = User(
        full_name="User One",
        email=email,
        password_hash="hashed1",
        role=UserRole.SOLVER,
    )
    user2 = User(
        full_name="User Two",
        email=email,
        password_hash="hashed2",
        role=UserRole.REPORTER,
    )
    db_session.add_all([user1, user2])

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_student_profile_creation(db_session):
    user = User(
        full_name="Student User",
        email=f"student_{uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.SOLVER,
    )
    db_session.add(user)
    await db_session.flush()

    profile = StudentProfile(
        user_id=user.id,
        student_identifier=f"CS2021{uuid4().hex[:8].upper()}",
        department=Department.COMPUTER_SCIENCE_ENGINEERING,
        academic_year=3,
        semester=6,
        bio="Test bio",
        availability_status=AvailabilityStatus.AVAILABLE,
        current_workload=0,
        max_workload=3,
    )
    db_session.add(profile)
    await db_session.flush()

    assert profile.id is not None
    assert profile.user_id == user.id
    assert profile.department == Department.COMPUTER_SCIENCE_ENGINEERING
    assert profile.academic_year == 3
    assert profile.semester == 6
    assert profile.availability_status == AvailabilityStatus.AVAILABLE
    assert profile.current_workload == 0
    assert profile.max_workload == 3


@pytest.mark.asyncio
async def test_student_profile_student_identifier_unique(db_session):
    user1 = User(full_name="User1", email=f"user1_{uuid4()}@example.com", password_hash="h1", role=UserRole.SOLVER)
    user2 = User(full_name="User2", email=f"user2_{uuid4()}@example.com", password_hash="h2", role=UserRole.SOLVER)
    db_session.add_all([user1, user2])
    await db_session.flush()

    ident = f"CS2021{uuid4().hex[:8].upper()}"
    profile1 = StudentProfile(
        user_id=user1.id,
        student_identifier=ident,
        department=Department.COMPUTER_SCIENCE_ENGINEERING,
        academic_year=3,
        current_workload=0,
        max_workload=3,
    )
    profile2 = StudentProfile(
        user_id=user2.id,
        student_identifier=ident,
        department=Department.COMPUTER_SCIENCE_ENGINEERING,
        academic_year=2,
        current_workload=0,
        max_workload=3,
    )
    db_session.add_all([profile1, profile2])

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_student_profile_workload_constraints(db_session):
    user = User(full_name="User", email=f"workload_{uuid4()}@example.com", password_hash="h", role=UserRole.SOLVER)
    db_session.add(user)
    await db_session.flush()

    # current_workload > max_workload should fail
    profile = StudentProfile(
        user_id=user.id,
        student_identifier=f"CS2021{uuid4().hex[:8].upper()}",
        department=Department.COMPUTER_SCIENCE_ENGINEERING,
        academic_year=3,
        current_workload=5,
        max_workload=3,
    )
    db_session.add(profile)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_faculty_profile_creation(db_session):
    user = User(
        full_name="Faculty User",
        email=f"faculty_{uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.MENTOR,
    )
    db_session.add(user)
    await db_session.flush()

    profile = FacultyProfile(
        user_id=user.id,
        employee_identifier=f"FAC{uuid4().hex[:8].upper()}",
        department=Department.COMPUTER_SCIENCE_ENGINEERING,
        designation="Professor",
        specialization="AI/ML",
        bio="Faculty bio",
        availability_status=AvailabilityStatus.AVAILABLE,
        current_workload=0,
        max_workload=5,
    )
    db_session.add(profile)
    await db_session.flush()

    assert profile.id is not None
    assert profile.user_id == user.id
    assert profile.designation == "Professor"
    assert profile.specialization == "AI/ML"


@pytest.mark.asyncio
async def test_faculty_profile_employee_identifier_unique(db_session):
    user1 = User(full_name="Fac1", email=f"fac1_{uuid4()}@example.com", password_hash="h1", role=UserRole.MENTOR)
    user2 = User(full_name="Fac2", email=f"fac2_{uuid4()}@example.com", password_hash="h2", role=UserRole.MENTOR)
    db_session.add_all([user1, user2])
    await db_session.flush()

    emp_id = f"FAC{uuid4().hex[:8].upper()}"
    profile1 = FacultyProfile(
        user_id=user1.id,
        employee_identifier=emp_id,
        department=Department.COMPUTER_SCIENCE_ENGINEERING,
        designation="Professor",
        specialization="AI",
        current_workload=0,
        max_workload=5,
    )
    profile2 = FacultyProfile(
        user_id=user2.id,
        employee_identifier=emp_id,
        department=Department.ELECTRICAL,
        designation="Associate Professor",
        specialization="Electronics",
        current_workload=0,
        max_workload=5,
    )
    db_session.add_all([profile1, profile2])

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_skill_creation(db_session):
    skill = Skill(
        name=f"Python_{uuid4().hex[:8]}",
        normalized_name=f"python_{uuid4().hex[:8]}",
        category=SkillCategory.SOFTWARE_DEVELOPMENT,
        description="Python programming language",
    )
    try:
        db_session.add(skill)
        await db_session.flush()

        assert skill.id is not None
        assert skill.category == SkillCategory.SOFTWARE_DEVELOPMENT
        assert skill.is_active is True
    finally:
        # flush() without commit would roll back anyway, but delete explicitly
        # so taxonomy-count assertions elsewhere never see this row.
        from sqlalchemy import inspect as sa_inspect

        await db_session.rollback()
        if sa_inspect(skill).persistent:
            await db_session.delete(skill)
            await db_session.flush()


@pytest.mark.asyncio
async def test_skill_normalized_name_unique(db_session):
    norm = f"python_{uuid4().hex[:8]}"
    skill1 = Skill(
        name="Python",
        normalized_name=norm,
        category=SkillCategory.SOFTWARE_DEVELOPMENT,
    )
    skill2 = Skill(
        name="python",
        normalized_name=norm,
        category=SkillCategory.SOFTWARE_DEVELOPMENT,
    )
    db_session.add_all([skill1, skill2])

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_user_skill_creation(db_session):
    user = User(full_name="Test User", email=f"uskill_{uuid4()}@example.com", password_hash="h", role=UserRole.SOLVER)
    skill = Skill(name=f"React_{uuid4().hex[:8]}", normalized_name=f"react_{uuid4().hex[:8]}", category=SkillCategory.SOFTWARE_DEVELOPMENT)
    db_session.add_all([user, skill])
    await db_session.flush()

    user_skill = UserSkill(
        user_id=user.id,
        skill_id=skill.id,
        proficiency_level=4,
        years_experience=3,
        is_verified=True,
    )
    db_session.add(user_skill)
    await db_session.flush()

    assert user_skill.id is not None
    assert user_skill.user_id == user.id
    assert user_skill.skill_id == skill.id
    assert user_skill.proficiency_level == 4
    assert user_skill.proficiency == ProficiencyLevel.ADVANCED
    assert user_skill.years_experience == 3
    assert user_skill.is_verified is True


@pytest.mark.asyncio
async def test_user_skill_unique_user_skill(db_session):
    user = User(full_name="User", email=f"unique_{uuid4()}@example.com", password_hash="h", role=UserRole.SOLVER)
    skill = Skill(name=f"React_{uuid4().hex[:8]}", normalized_name=f"react_{uuid4().hex[:8]}", category=SkillCategory.SOFTWARE_DEVELOPMENT)
    db_session.add_all([user, skill])
    await db_session.flush()

    us1 = UserSkill(user_id=user.id, skill_id=skill.id, proficiency_level=3)
    us2 = UserSkill(user_id=user.id, skill_id=skill.id, proficiency_level=4)
    db_session.add_all([us1, us2])

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_user_skill_proficiency_constraints(db_session):
    user = User(full_name="User", email=f"prof_{uuid4()}@example.com", password_hash="h", role=UserRole.SOLVER)
    skill = Skill(name=f"React_{uuid4().hex[:8]}", normalized_name=f"react_{uuid4().hex[:8]}", category=SkillCategory.SOFTWARE_DEVELOPMENT)
    db_session.add_all([user, skill])
    await db_session.flush()

    # proficiency > 5 should fail
    us = UserSkill(user_id=user.id, skill_id=skill.id, proficiency_level=6)
    db_session.add(us)
    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()

    # proficiency < 1 should fail
    us2 = UserSkill(user_id=user.id, skill_id=skill.id, proficiency_level=0)
    db_session.add(us2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_user_skill_years_experience_constraint(db_session):
    user = User(full_name="User", email=f"years_{uuid4()}@example.com", password_hash="h", role=UserRole.SOLVER)
    skill = Skill(name=f"React_{uuid4().hex[:8]}", normalized_name=f"react_{uuid4().hex[:8]}", category=SkillCategory.SOFTWARE_DEVELOPMENT)
    db_session.add_all([user, skill])
    await db_session.flush()

    # negative years_experience should fail
    us = UserSkill(user_id=user.id, skill_id=skill.id, proficiency_level=3, years_experience=-1)
    db_session.add(us)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_relationships(db_session):
    user = User(full_name="Rel User", email=f"rel_{uuid4()}@example.com", password_hash="h", role=UserRole.SOLVER)
    skill = Skill(name=f"Python_{uuid4().hex[:8]}", normalized_name=f"python_{uuid4().hex[:8]}", category=SkillCategory.SOFTWARE_DEVELOPMENT)
    user_skill = None
    db_session.add_all([user, skill])
    try:
        await db_session.flush()

        profile = StudentProfile(
            user_id=user.id,
            student_identifier=f"CS2021{uuid4().hex[:8].upper()}",
            department=Department.COMPUTER_SCIENCE_ENGINEERING,
            academic_year=3,
            current_workload=0,
            max_workload=3,
        )
        db_session.add(profile)
        await db_session.flush()

        user_skill = UserSkill(user_id=user.id, skill_id=skill.id, proficiency_level=4)
        db_session.add(user_skill)
        await db_session.commit()

        # Test relationships (refresh with relationship names: async SQLAlchemy
        # cannot lazy-load relationships outside of an explicit refresh/select).
        await db_session.refresh(user, ["student_profile", "user_skills"])
        assert user.student_profile is not None
        assert user.student_profile.student_identifier.startswith("CS2021")
        assert len(user.user_skills) == 1
        assert user.user_skills[0].skill_id == skill.id
        assert user.user_skills[0].proficiency == ProficiencyLevel.ADVANCED

        await db_session.refresh(skill, ["user_skills"])
        assert len(skill.user_skills) == 1
        assert skill.user_skills[0].user_id == user.id
    finally:
        # This test commits, so remove its rows explicitly: the taxonomy-count
        # assertions elsewhere must never see this throwaway skill.
        from sqlalchemy import inspect as sa_inspect

        await db_session.rollback()
        for obj in (user_skill, skill, user):
            if obj is not None and sa_inspect(obj).persistent:
                await db_session.delete(obj)
        await db_session.commit()


@pytest.mark.asyncio
async def test_cascade_delete_user(db_session):
    user = User(full_name="Cascade User", email=f"cascade_{uuid4()}@example.com", password_hash="h", role=UserRole.SOLVER)
    db_session.add(user)
    await db_session.flush()

    profile = StudentProfile(
        user_id=user.id,
        student_identifier=f"CS2021{uuid4().hex[:8].upper()}",
        department=Department.COMPUTER_SCIENCE_ENGINEERING,
        academic_year=3,
        current_workload=0,
        max_workload=3,
    )
    skill = Skill(name=f"React_{uuid4().hex[:8]}", normalized_name=f"react_{uuid4().hex[:8]}", category=SkillCategory.SOFTWARE_DEVELOPMENT)
    db_session.add_all([profile, skill])
    await db_session.flush()

    user_skill = UserSkill(user_id=user.id, skill_id=skill.id, proficiency_level=3)
    db_session.add(user_skill)
    await db_session.flush()

    user_id = user.id
    await db_session.delete(user)
    await db_session.flush()

    # Student profile should be deleted
    result = await db_session.execute(
        select(StudentProfile).where(StudentProfile.user_id == user_id)
    )
    assert result.first() is None

    # UserSkill should be deleted
    result = await db_session.execute(
        select(UserSkill).where(UserSkill.user_id == user_id)
    )
    assert result.first() is None

    # Skill should remain
    await db_session.refresh(skill)
    assert skill.id is not None


@pytest.mark.asyncio
async def test_skill_seed_idempotency(db_session):
    """Test that seeding skills twice doesn't create duplicates."""
    from app.services.skill_service import SkillService

    service = SkillService(db_session)

    # First seed
    await service.seed_skills()
    count1 = await service.count_skills()

    # Second seed
    await service.seed_skills()
    count2 = await service.count_skills()

    assert count1 == count2
    assert count1 >= 46  # At least 46 skills from taxonomy


@pytest.mark.asyncio
async def test_user_seed_idempotency(db_session):
    """Test that seeding users twice doesn't create duplicates."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "seed_users", str(Path(__file__).parent.parent / "scripts" / "seed_users.py"))
    seed_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed_mod)

    try:
        first = await seed_mod.seed_users(db_session)
        result = await db_session.execute(select(func.count(User.id)))
        after_first = result.scalar()
        assert after_first == 7  # the 7 official development accounts

        second = await seed_mod.seed_users(db_session)
        result = await db_session.execute(select(func.count(User.id)))
        after_second = result.scalar()
        assert after_second == after_first  # second run creates no duplicates
        assert first is not None
        assert second is not None
    finally:
        # Re-seed (idempotent) so later tests still see the 7 reference
        # accounts provisioned for the suite; never leave the DB without them.
        await seed_mod.seed_users(db_session)
