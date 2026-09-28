import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import user_from_token
from app.database import SessionLocal
from app.models import User

bearer = HTTPBearer(auto_error=False)


async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await user_from_token(session, creds.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def parse_user_id(token: str) -> uuid.UUID | None:
    from app.auth import decode_token

    try:
        payload = decode_token(token)
        return uuid.UUID(payload["sub"])
    except Exception:
        return None
