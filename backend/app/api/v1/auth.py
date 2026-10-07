"""Step 3 authentication endpoints."""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AuthUserResponse,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from app.security.jwt import REFRESH_COOKIE_NAME
from app.services.auth_service import AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

REFRESH_COOKIE_PATH = "/api/v1/auth"
REFRESH_COOKIE_MAX_AGE = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


def _auth_error_to_http(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> RegisterResponse:
    service = AuthService(db)
    try:
        user, pair = await service.register(
            full_name=payload.full_name,
            email=str(payload.email),
            password=payload.password,
            role=payload.role,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from None
    _set_refresh_cookie(response, pair.refresh_token)
    return RegisterResponse(
        user=AuthUserResponse.model_validate(user),
        access_token=pair.access_token,
        expires_in=pair.expires_in,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    service = AuthService(db)
    try:
        _user, pair = await service.authenticate(
            email=str(payload.email), password=payload.password
        )
    except AuthError as exc:
        # Always 401 for bad credentials; 403 only for disabled accounts.
        raise _auth_error_to_http(exc) from None
    _set_refresh_cookie(response, pair.refresh_token)
    return TokenResponse(access_token=pair.access_token, expires_in=pair.expires_in)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    payload: RefreshRequest | None = None,
    cookie_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> TokenResponse:
    # Cookie takes precedence; body is accepted for non-browser clients/tests.
    raw = cookie_token or (payload.refresh_token if payload and payload.refresh_token else None)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )
    service = AuthService(db)
    try:
        _user, pair = await service.refresh(raw)
    except AuthError as exc:
        raise _auth_error_to_http(exc) from None
    _set_refresh_cookie(response, pair.refresh_token)
    return TokenResponse(access_token=pair.access_token, expires_in=pair.expires_in)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    payload: RefreshRequest | None = None,
    cookie_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> dict[str, str]:
    raw = cookie_token or (payload.refresh_token if payload and payload.refresh_token else None)
    service = AuthService(db)
    await service.logout(raw)
    _clear_refresh_cookie(response)
    return {"detail": "Logged out"}


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse.model_validate(current_user)
