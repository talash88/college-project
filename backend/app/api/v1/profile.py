"""Authenticated self-service profile and skill management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.profile import (
    MySkillsResponse,
    ProfileMeResponse,
    ProfileUpdateRequest,
    UserSkillAdd,
    UserSkillPatch,
)
from app.schemas.user_skill import UserSkillWithSkill
from app.services.auth_service import AuthError
from app.services.profile_service import ProfileService
from app.services.skill_service import SkillService
from app.services.user_service import UserService

router = APIRouter(prefix="/profile", tags=["Profile"])


def _to_http(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/me", response_model=ProfileMeResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)) -> ProfileMeResponse:
    return ProfileMeResponse.model_validate(current_user)


@router.patch("/me", response_model=ProfileMeResponse)
async def update_my_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileMeResponse:
    service = ProfileService(db)
    try:
        updated = await service.update_me(current_user, payload)
    except AuthError as exc:
        raise _to_http(exc) from None
    return ProfileMeResponse.model_validate(updated)


@router.get("/me/skills", response_model=MySkillsResponse)
async def list_my_skills(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MySkillsResponse:
    service = UserService(db)
    skills = await service.get_user_skills_with_skills(current_user.id)
    return MySkillsResponse(skills=[UserSkillWithSkill.model_validate(s) for s in skills])


@router.post("/me/skills", response_model=UserSkillWithSkill, status_code=status.HTTP_201_CREATED)
async def add_my_skill(
    payload: UserSkillAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSkillWithSkill:
    skill_service = SkillService(db)
    skill = await skill_service.get_skill(payload.skill_id)
    if skill is None or not skill.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")

    service = UserService(db)
    try:
        await service.add_user_skill(
            current_user.id,
            payload.skill_id,
            proficiency_level=payload.proficiency_level,
            years_experience=payload.years_experience,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    created = await service.get_user_skill_with_skill(current_user.id, payload.skill_id)
    assert created is not None
    return UserSkillWithSkill.model_validate(created)


@router.patch("/me/skills/{skill_id}", response_model=UserSkillWithSkill)
async def update_my_skill(
    skill_id: UUID,
    payload: UserSkillPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSkillWithSkill:
    service = UserService(db)
    try:
        updated = await service.update_user_skill(
            current_user.id,
            skill_id,
            proficiency_level=payload.proficiency_level,
            years_experience=payload.years_experience,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found for user"
        )
    fresh = await service.get_user_skill_with_skill(current_user.id, skill_id)
    assert fresh is not None
    return UserSkillWithSkill.model_validate(fresh)


@router.delete("/me/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_skill(
    skill_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = UserService(db)
    removed = await service.remove_user_skill(current_user.id, skill_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found for user"
        )
    return None
