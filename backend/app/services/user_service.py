from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.models.faculty_profile import FacultyProfile
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.repositories.user_repository import (
    FacultyProfileRepository,
    StudentProfileRepository,
    UserRepository,
    UserSkillRepository,
)
from app.schemas.faculty_profile import FacultyProfileCreate, FacultyProfileUpdate
from app.schemas.student_profile import StudentProfileCreate, StudentProfileUpdate
from app.schemas.user import UserCreate, UserUpdate
from app.services.security import hash_password

if TYPE_CHECKING:
    from app.models.user_skill import UserSkill


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.student_repo = StudentProfileRepository(session)
        self.faculty_repo = FacultyProfileRepository(session)
        self.user_skill_repo = UserSkillRepository(session)

    async def create_user(self, user_data: UserCreate) -> User:
        password_hash = hash_password(user_data.password)
        try:
            user = await self.user_repo.create(user_data, password_hash)
            await self.session.commit()
            return user
        except IntegrityError as e:
            await self.session.rollback()
            if "uq_users_email" in str(e):
                raise ValueError("Email already registered") from e
            raise

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.user_repo.get_by_id(user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        return await self.user_repo.get_by_email(email)

    async def list_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        return await self.user_repo.get_all(skip=skip, limit=limit)

    async def update_user(self, user_id: UUID, user_data: UserUpdate) -> User | None:
        user = await self.user_repo.update(user_id, user_data)
        if user:
            await self.session.commit()
        return user

    async def delete_user(self, user_id: UUID) -> bool:
        result = await self.user_repo.delete(user_id)
        if result:
            await self.session.commit()
        return result

    async def create_student_profile(self, profile_data: StudentProfileCreate) -> StudentProfile:
        # Verify user exists and has SOLVER or REPORTER role
        user = await self.user_repo.get_by_id(profile_data.user_id)
        if not user:
            raise ValueError("User not found")
        if user.role not in (UserRole.SOLVER, UserRole.REPORTER):
            raise ValueError("User must have SOLVER or REPORTER role for student profile")

        # Check if student profile already exists
        existing = await self.student_repo.get_by_user_id(profile_data.user_id)
        if existing:
            raise ValueError("Student profile already exists for this user")

        try:
            profile = await self.student_repo.create(profile_data)
            await self.session.commit()
            return profile
        except IntegrityError as e:
            await self.session.rollback()
            if "uq_student_profiles_student_identifier" in str(e):
                raise ValueError("Student identifier already exists") from e
            raise

    async def get_student_profile(self, user_id: UUID) -> StudentProfile | None:
        return await self.student_repo.get_by_user_id(user_id)

    async def update_student_profile(self, user_id: UUID, profile_data: StudentProfileUpdate) -> StudentProfile | None:
        profile = await self.student_repo.update(user_id, profile_data)
        if profile:
            await self.session.commit()
        return profile

    async def create_faculty_profile(self, profile_data: FacultyProfileCreate) -> FacultyProfile:
        # Verify user exists and has MENTOR or ADMIN role
        user = await self.user_repo.get_by_id(profile_data.user_id)
        if not user:
            raise ValueError("User not found")
        if user.role not in (UserRole.MENTOR, UserRole.ADMIN):
            raise ValueError("User must have MENTOR or ADMIN role for faculty profile")

        # Check if faculty profile already exists
        existing = await self.faculty_repo.get_by_user_id(profile_data.user_id)
        if existing:
            raise ValueError("Faculty profile already exists for this user")

        try:
            profile = await self.faculty_repo.create(profile_data)
            await self.session.commit()
            return profile
        except IntegrityError as e:
            await self.session.rollback()
            if "uq_faculty_profiles_employee_identifier" in str(e):
                raise ValueError("Employee identifier already exists") from e
            raise

    async def get_faculty_profile(self, user_id: UUID) -> FacultyProfile | None:
        return await self.faculty_repo.get_by_user_id(user_id)

    async def update_faculty_profile(self, user_id: UUID, profile_data: FacultyProfileUpdate) -> FacultyProfile | None:
        profile = await self.faculty_repo.update(user_id, profile_data)
        if profile:
            await self.session.commit()
        return profile

    async def add_user_skill(self, user_id: UUID, skill_id: UUID, proficiency_level: int, years_experience: int | None = None) -> "UserSkill":
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        # Check if association already exists
        existing = await self.user_skill_repo.get_by_user_and_skill(user_id, skill_id)
        if existing:
            raise ValueError("User already has this skill")

        if not 1 <= proficiency_level <= 5:
            raise ValueError("Proficiency level must be between 1 and 5")
        if years_experience is not None and years_experience < 0:
            raise ValueError("Years of experience cannot be negative")

        user_skill = await self.user_skill_repo.create(user_id, skill_id, proficiency_level, years_experience)
        await self.session.commit()
        return user_skill

    async def get_user_skills(self, user_id: UUID) -> list["UserSkill"]:
        return await self.user_skill_repo.get_by_user_id(user_id)

    async def get_user_skills_with_skills(self, user_id: UUID) -> list["UserSkill"]:
        return await self.user_skill_repo.get_by_user_id_with_skills(user_id)

    async def get_user_skill_with_skill(self, user_id: UUID, skill_id: UUID) -> "UserSkill | None":
        return await self.user_skill_repo.get_by_user_and_skill_with_skill(user_id, skill_id)

    async def update_user_skill(self, user_id: UUID, skill_id: UUID, proficiency_level: int | None = None, years_experience: int | None = None, is_verified: bool | None = None) -> "UserSkill | None":
        if proficiency_level is not None and not 1 <= proficiency_level <= 5:
            raise ValueError("Proficiency level must be between 1 and 5")
        if years_experience is not None and years_experience < 0:
            raise ValueError("Years of experience cannot be negative")

        user_skill = await self.user_skill_repo.update(user_id, skill_id, proficiency_level, years_experience, is_verified)
        if user_skill:
            await self.session.commit()
        return user_skill

    async def remove_user_skill(self, user_id: UUID, skill_id: UUID) -> bool:
        result = await self.user_skill_repo.delete(user_id, skill_id)
        if result:
            await self.session.commit()
        return result
