from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.sessions import RedisSessionStore, SessionStoreUnavailable, get_session_store
from db.session import get_db
from models.user import User

session_cookie = APIKeyCookie(
    name=settings.SESSION_COOKIE_NAME,
    scheme_name="SessionCookie",
    auto_error=False,
    description="Cookie из POST /api/authentication. В Swagger сначала выполните вход: "
    "браузер сохранит HttpOnly cookie автоматически.",
)


async def get_optional_user(
    token: str | None = Security(session_cookie),
    db: AsyncSession = Depends(get_db),
    sessions: RedisSessionStore = Depends(get_session_store),
) -> User | None:
    if not token:
        return None
    try:
        user_id = await sessions.user_id(token)
    except SessionStoreUnavailable:
        # Публичное чтение не зависит от действительности cookie и доступности Redis.
        return None
    return await db.get(User, user_id) if user_id is not None else None


async def get_current_user(
    token: str | None = Security(session_cookie),
    db: AsyncSession = Depends(get_db),
    sessions: RedisSessionStore = Depends(get_session_store),
) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Необходимо войти в систему")
    try:
        user_id = await sessions.user_id(token)
    except SessionStoreUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Хранилище сессий недоступно"
        ) from exc
    user = await db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status_code=401, detail="Сессия недействительна или истекла"
        )
    return user
