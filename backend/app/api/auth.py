from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_db
from app.auth import create_token, hash_password, verify_password
from app.config import get_settings
from app.models import User
from app.schemas import LoginIn, PublicSettings, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, session: AsyncSession = Depends(get_db)) -> TokenOut:
    email = body.email.strip().lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenOut)
async def register(body: RegisterIn, session: AsyncSession = Depends(get_db)) -> TokenOut:
    settings = get_settings()
    if not settings.allow_registration:
        raise HTTPException(status_code=403, detail="Registration is closed")
    email = body.email.strip().lower()
    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> User:
    return user


settings_router = APIRouter(tags=["settings"])


@settings_router.get("/api/settings/public", response_model=PublicSettings)
async def public_settings() -> PublicSettings:
    settings = get_settings()
    return PublicSettings(
        company_name=settings.company_name,
        company_tagline=settings.company_tagline,
        brand_color=settings.brand_color,
    )
