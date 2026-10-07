"""Self-service profile logic: update own user fields and upsert own role profile."""

from typing import cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AvailabilityStatus, UserRole
from app.models.faculty_profile import FacultyProfile
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.repositories.user_repository import (
    FacultyProfileRepository,
    StudentProfileRepository,
    UserRepository,
)
from app.schemas.faculty_profile import FacultyProfileCreate
from app.schemas.profile import FacultySelfUpdate, ProfileUpdateRequest, StudentSelfUpdate
from app.schemas.student_profile import StudentProfileCreate
from app.services.auth_service import AuthError

_STUDENT_ROLES = frozenset({UserRole.REPORTER, UserRole.SOLVER})
_FACULTY_ROLES = frozenset({UserRole.MENTOR, UserRole.ADMIN})


class ProfileService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.student_repo = StudentProfileRepository(session)
        self.faculty_repo = FacultyProfileRepository(session)

    async def get_me(self, user_id: UUID) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise AuthError(404, "User not found")
        return user

    async def update_me(self, user: User, payload: ProfileUpdateRequest) -> User:
        if payload.full_name is not None:
            name = payload.full_name.strip()
            if not name:
                raise AuthError(422, "Full name cannot be empty")
            user.full_name = name

        if payload.student_profile is not None:
            if UserRole(user.role) not in _STUDENT_ROLES:
                raise AuthError(422, "Student profile does not apply to your role")
            await self._upsert_student_profile(user, payload.student_profile)

        if payload.faculty_profile is not None:
            if UserRole(user.role) not in _FACULTY_ROLES:
                raise AuthError(422, "Faculty profile does not apply to your role")
            await self._upsert_faculty_profile(user, payload.faculty_profile)

        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            message = str(exc)
            if "uq_student_profiles_student_identifier" in message:
                raise AuthError(409, "Student identifier already exists") from exc
            if "uq_faculty_profiles_employee_identifier" in message:
                raise AuthError(409, "Employee identifier already exists") from exc
            raise AuthError(409, "Profile identifier already exists") from exc

        await self.session.refresh(user)
        return await self.get_me(user.id)

    async def _upsert_student_profile(self, user: User, data: StudentSelfUpdate) -> StudentProfile:
        existing = await self.student_repo.get_by_user_id(user.id)
        fields = data.model_dump(exclude_unset=True)
        if existing is None:
            missing = [
                f for f in ("student_identifier", "department", "academic_year") if f not in fields
            ]
            if missing:
                raise AuthError(
                    422, f"Missing required student profile fields: {', '.join(missing)}"
                )
            student_status = cast(
                AvailabilityStatus,
                fields.get("availability_status") or AvailabilityStatus.AVAILABLE,
            )
            create_data = StudentProfileCreate(
                user_id=user.id,
                student_identifier=str(fields["student_identifier"]),
                department=fields["department"],
                academic_year=int(fields["academic_year"]),
                semester=fields.get("semester"),
                bio=fields.get("bio"),
                availability_status=student_status,
                max_workload=int(fields.get("max_workload", 3)),
            )
            profile = await self.student_repo.create(create_data)
            await self.session.flush()
            return profile
        for field, value in fields.items():
            setattr(existing, field, value)
        await self.session.flush()
        return existing

    async def _upsert_faculty_profile(self, user: User, data: FacultySelfUpdate) -> FacultyProfile:
        existing = await self.faculty_repo.get_by_user_id(user.id)
        fields = data.model_dump(exclude_unset=True)
        if existing is None:
            missing = [
                f
                for f in ("employee_identifier", "department", "designation", "specialization")
                if f not in fields
            ]
            if missing:
                raise AuthError(
                    422, f"Missing required faculty profile fields: {', '.join(missing)}"
                )
            faculty_status = cast(
                AvailabilityStatus,
                fields.get("availability_status") or AvailabilityStatus.AVAILABLE,
            )
            create_data = FacultyProfileCreate(
                user_id=user.id,
                employee_identifier=str(fields["employee_identifier"]),
                department=fields["department"],
                designation=str(fields["designation"]),
                specialization=str(fields["specialization"]),
                bio=fields.get("bio"),
                availability_status=faculty_status,
                max_workload=int(fields.get("max_workload", 5)),
            )
            profile = await self.faculty_repo.create(create_data)
            await self.session.flush()
            return profile
        for field, value in fields.items():
            setattr(existing, field, value)
        await self.session.flush()
        return existing
