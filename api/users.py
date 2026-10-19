import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Security
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.serializers import AuthenticationIn, AuthenticationOut, UserOut, UserRegisterIn
from core.config import settings
from core.current_user import session_cookie
from core.passwords import hash_password, verify_password
from core.sessions import RedisSessionStore, SessionStoreUnavailable, get_session_store
from db.session import get_db
from models.user import User

router = APIRouter(prefix="/api", tags=["Пользователи"])


def user_out(user: User) -> UserOut:
    return UserOut(
        user_id=user.user_id, user_login=user.user_login, user_name=user.user_name
    )


@router.post(
    "/users",
    response_model=UserOut,
    status_code=201,
    summary="Регистрация",
    description="Создаёт пользователя с паролем 8–128 символов. "
    "Пароль хранится как Argon2id-хеш. Для входа вызовите authentication.",
    responses={409: {"description": "Логин уже занят"}},
)
async def register_user(
    body: UserRegisterIn,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    login, name = body.user_login.strip(), body.user_name.strip()
    if not login or not name:
        raise HTTPException(status_code=422, detail="Логин и имя обязательны")
    encoded = await asyncio.to_thread(
        hash_password, body.user_password.get_secret_value()
    )
    user = User(user_login=login, user_name=name, password_hash=encoded)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Логин уже занят") from None
    await db.refresh(user)
    return user_out(user)


@router.post(
    "/authentication",
    response_model=AuthenticationOut,
    summary="Вход: сессия и cookie",
    description="Проверяет логин/пароль, создаёт сессию в Redis и устанавливает "
    "HttpOnly cookie session_id. Повторный вход заменяет сессию этой cookie. "
    "Swagger на этом же адресе автоматически отправляет полученную cookie.",
    responses={
        401: {"description": "Неверный логин или пароль"},
        503: {"description": "Redis недоступен"},
    },
    openapi_extra={"security": []},
)
async def authenticate(
    body: AuthenticationIn,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
    sessions: RedisSessionStore = Depends(get_session_store),
) -> AuthenticationOut:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    result = await db.execute(
        select(User).where(User.user_login == body.user_login.strip())
    )
    user = result.scalar_one_or_none()
    valid = await asyncio.to_thread(
        verify_password,
        body.user_password.get_secret_value(),
        user.password_hash if user is not None else None,
    )
    if not valid or user is None:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    try:
        new_token = await sessions.create(user.user_id, old_token=token)
    except SessionStoreUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Хранилище сессий недоступно"
        ) from exc
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=new_token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return AuthenticationOut(
        user=user_out(user), expires_in=settings.SESSION_TTL_SECONDS
    )


@router.post(
    "/deauthentication",
    status_code=204,
    summary="Выход: удалить сессию",
    description="Удаляет сессию из Redis и cookie браузера. "
    "Повторный выход без cookie тоже возвращает 204.",
    responses={503: {"description": "Redis недоступен; отзыв сессии не подтверждён"}},
    openapi_extra={"security": [{}]},
)
async def deauthenticate(
    response: Response,
    token: str | None = Security(session_cookie),
    sessions: RedisSessionStore = Depends(get_session_store),
) -> None:
    if token:
        try:
            await sessions.delete(token)
        except SessionStoreUnavailable as exc:
            raise HTTPException(
                status_code=503, detail="Хранилище сессий недоступно"
            ) from exc
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
