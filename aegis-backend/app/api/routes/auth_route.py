"""app/api/routes/auth_route.py — Login, register, token refresh"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import (
    create_access_token, create_refresh_token, decode_token,
    get_current_active_user, hash_password, verify_password,
)
from app.database import get_db
from app.models import Organization, User
from app.schemas import LoginRequest, RefreshRequest, TokenResponse, UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory reset token store: {token: (user_id, expires_at)}
_reset_tokens: dict[str, tuple[str, datetime]] = {}


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(payload: UserCreate, org_name: str, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Email already registered")
    slug = org_name.lower().replace(" ", "-")[:100]
    org = Organization(name=org_name, slug=slug)
    db.add(org)
    await db.flush()
    initials = "".join(w[0].upper() for w in payload.full_name.split()[:2])
    user = User(
        org_id=org.id, email=payload.email, full_name=payload.full_name,
        initials=initials, role=payload.role, hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.flush()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password")
    user.last_login_at = datetime.now(timezone.utc)
    return TokenResponse(
        access_token=create_access_token(str(user.id), str(user.org_id), user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=15 * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    claims = decode_token(payload.refresh_token)
    if claims.get("type") != "refresh":
        raise HTTPException(401, "Not a refresh token")
    user = (await db.execute(select(User).where(User.id == claims["sub"]))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(401, "User not found")
    return TokenResponse(
        access_token=create_access_token(str(user.id), str(user.org_id), user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=15 * 60,
    )


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(get_current_active_user)]):
    return user


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@router.post("/change-password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()


class ForgotPasswordRequest(BaseModel):
    email: str

class ForgotPasswordResponse(BaseModel):
    token: str
    message: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "No account found with that email")
    token = secrets.token_urlsafe(12)
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    _reset_tokens[token] = (str(user.id), expires)
    return ForgotPasswordResponse(
        token=token,
        message="Copy this token and use it to set a new password. It expires in 30 minutes.",
    )


@router.post("/reset-password", status_code=204)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    entry = _reset_tokens.get(payload.token)
    if not entry:
        raise HTTPException(400, "Invalid or expired reset token")
    user_id, expires = entry
    if datetime.now(timezone.utc) > expires:
        del _reset_tokens[payload.token]
        raise HTTPException(400, "Reset token has expired")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(400, "User not found")
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    del _reset_tokens[payload.token]
