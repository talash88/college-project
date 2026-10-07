from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_admin
from app.core.enums import SkillCategory, UserRole
from app.db.session import get_db
from app.models.user import User
from app.schemas.faculty_profile import FacultyProfileResponse
from app.schemas.skill import SkillResponse
from app.schemas.student_profile import StudentProfileResponse
from app.schemas.user import UserResponse, UserSummary
from app.schemas.user_skill import UserSkillWithSkill
from app.services.skill_service import SkillService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


def _ensure_self_or_admin(user_id: UUID, current_user: User) -> None:
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.get("", response_model=list[UserSummary])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[UserSummary]:
    """List all users (admin only)."""
    service = UserService(db)
    users = await service.list_users(skip=skip, limit=limit)
    return [UserSummary.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Get user by ID (self or admin)."""
    _ensure_self_or_admin(user_id, current_user)
    service = UserService(db)
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.get("/{user_id}/student-profile", response_model=StudentProfileResponse)
async def get_user_student_profile(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StudentProfileResponse:
    """Get student profile for a user (self or admin)."""
    _ensure_self_or_admin(user_id, current_user)
    service = UserService(db)
    profile = await service.get_student_profile(user_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student profile not found")
    return StudentProfileResponse.model_validate(profile)


@router.get("/{user_id}/faculty-profile", response_model=FacultyProfileResponse)
async def get_user_faculty_profile(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FacultyProfileResponse:
    """Get faculty profile for a user (self or admin)."""
    _ensure_self_or_admin(user_id, current_user)
    service = UserService(db)
    profile = await service.get_faculty_profile(user_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faculty profile not found")
    return FacultyProfileResponse.model_validate(profile)


@router.get("/{user_id}/skills", response_model=list[UserSkillWithSkill])
async def get_user_skills(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UserSkillWithSkill]:
    """Get all skills for a user (self or admin)."""
    _ensure_self_or_admin(user_id, current_user)
    service = UserService(db)
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    skills = await service.get_user_skills_with_skills(user_id)
    return [UserSkillWithSkill.model_validate(skill) for skill in skills]


skill_router = APIRouter(prefix="/skills", tags=["Skills"])


@skill_router.get("", response_model=list[SkillResponse])
async def list_skills(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    category: SkillCategory | None = Query(None),
    is_active: bool | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[SkillResponse]:
    """List skills with optional filtering (authenticated users)."""
    service = SkillService(db)
    skills = await service.list_skills(skip=skip, limit=limit, category=category, is_active=is_active, search=search)
    return [SkillResponse.model_validate(skill) for skill in skills]


@skill_router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SkillResponse:
    """Get skill by ID (authenticated users)."""
    service = SkillService(db)
    skill = await service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return SkillResponse.model_validate(skill)
