from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.faculty_profile import FacultyProfile
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.models.user_skill import UserSkill
from app.schemas.faculty_profile import FacultyProfileCreate, FacultyProfileUpdate
from app.schemas.student_profile import StudentProfileCreate, StudentProfileUpdate
from app.schemas.user import UserCreate, UserUpdate


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_data: UserCreate, password_hash: str) -> User:
        user = User(
            full_name=user_data.full_name,
            email=user_data.email.lower(),
            password_hash=password_hash,
            role=user_data.role,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(User)
            .options(
                selectinload(User.student_profile),
                selectinload(User.faculty_profile),
                selectinload(User.user_skills),
            )
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        result = await self.session.execute(
            select(User)
            .options(
                selectinload(User.student_profile),
                selectinload(User.faculty_profile),
            )
            .offset(skip)
            .limit(limit)
            .order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, user_id: UUID, user_data: UserUpdate) -> User | None:
        user = await self.get_by_id(user_id)
        if not user:
            return None
        for field, value in user_data.model_dump(exclude_unset=True).items():
            if field == "email" and value:
                value = value.lower()
            setattr(user, field, value)
        await self.session.flush()
        return user

    async def delete(self, user_id: UUID) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False
        await self.session.delete(user)
        await self.session.flush()
        return True


class StudentProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, profile_data: StudentProfileCreate) -> StudentProfile:
        profile = StudentProfile(**profile_data.model_dump())
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get_by_user_id(self, user_id: UUID) -> StudentProfile | None:
        result = await self.session.execute(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_student_identifier(self, student_identifier: str) -> StudentProfile | None:
        result = await self.session.execute(
            select(StudentProfile).where(StudentProfile.student_identifier == student_identifier)
        )
        return result.scalar_one_or_none()

    async def update(self, user_id: UUID, profile_data: StudentProfileUpdate) -> StudentProfile | None:
        profile = await self.get_by_user_id(user_id)
        if not profile:
            return None
        for field, value in profile_data.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
        await self.session.flush()
        return profile


class FacultyProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, profile_data: FacultyProfileCreate) -> FacultyProfile:
        profile = FacultyProfile(**profile_data.model_dump())
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get_by_user_id(self, user_id: UUID) -> FacultyProfile | None:
        result = await self.session.execute(
            select(FacultyProfile).where(FacultyProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_employee_identifier(self, employee_identifier: str) -> FacultyProfile | None:
        result = await self.session.execute(
            select(FacultyProfile).where(FacultyProfile.employee_identifier == employee_identifier)
        )
        return result.scalar_one_or_none()

    async def update(self, user_id: UUID, profile_data: FacultyProfileUpdate) -> FacultyProfile | None:
        profile = await self.get_by_user_id(user_id)
        if not profile:
            return None
        for field, value in profile_data.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
        await self.session.flush()
        return profile


class UserSkillRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: UUID, skill_id: UUID, proficiency_level: int, years_experience: int | None = None) -> UserSkill:
        user_skill = UserSkill(
            user_id=user_id,
            skill_id=skill_id,
            proficiency_level=proficiency_level,
            years_experience=years_experience,
        )
        self.session.add(user_skill)
        await self.session.flush()
        return user_skill

    async def get_by_user_id(self, user_id: UUID) -> list[UserSkill]:
        result = await self.session.execute(
            select(UserSkill)
            .where(UserSkill.user_id == user_id)
            .order_by(UserSkill.proficiency_level.desc())
        )
        return list(result.scalars().all())

    async def get_by_user_id_with_skills(self, user_id: UUID) -> list[UserSkill]:
        result = await self.session.execute(
            select(UserSkill)
            .options(selectinload(UserSkill.skill))
            .where(UserSkill.user_id == user_id)
            .order_by(UserSkill.proficiency_level.desc())
        )
        return list(result.scalars().all())

    async def get_by_user_and_skill_with_skill(self, user_id: UUID, skill_id: UUID) -> UserSkill | None:
        result = await self.session.execute(
            select(UserSkill)
            .options(selectinload(UserSkill.skill))
            .where(
                UserSkill.user_id == user_id,
                UserSkill.skill_id == skill_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user_and_skill(self, user_id: UUID, skill_id: UUID) -> UserSkill | None:
        result = await self.session.execute(
            select(UserSkill).where(
                UserSkill.user_id == user_id,
                UserSkill.skill_id == skill_id,
            )
        )
        return result.scalar_one_or_none()

    async def update(self, user_id: UUID, skill_id: UUID, proficiency_level: int | None = None, years_experience: int | None = None, is_verified: bool | None = None) -> UserSkill | None:
        user_skill = await self.get_by_user_and_skill(user_id, skill_id)
        if not user_skill:
            return None
        if proficiency_level is not None:
            user_skill.proficiency_level = proficiency_level
        if years_experience is not None:
            user_skill.years_experience = years_experience
        if is_verified is not None:
            user_skill.is_verified = is_verified
        await self.session.flush()
        return user_skill

    async def delete(self, user_id: UUID, skill_id: UUID) -> bool:
        user_skill = await self.get_by_user_and_skill(user_id, skill_id)
        if not user_skill:
            return False
        await self.session.delete(user_skill)
        await self.session.flush()
        return True
