from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.serializers import AuthenticationIn, StubOut, UserOut, UserRegisterIn
from db.session import get_db
from models.user import User

router = APIRouter(prefix="/api", tags=["Пользователи"])

AUTH_STUB = "Аутентификация будет реализована в лабораторной 4"
DEAUTH_STUB = "Деавторизация будет реализована в лабораторной 4"


@router.post("/users", response_model=UserOut, status_code=201, summary="Регистрация")
async def register_user(
    body: UserRegisterIn,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    login = body.user_login.strip()
    name = body.user_name.strip()
    if not login or not name:
        raise HTTPException(status_code=422, detail="Логин и имя обязательны")

    user = User(user_login=login, user_name=name)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Логин уже занят") from None
    await db.refresh(user)
    return UserOut(user_id=user.user_id, user_login=user.user_login, user_name=user.user_name)


@router.post(
    "/authentication",
    response_model=StubOut,
    summary="Аутентификация (заглушка)",
)
async def authenticate(_body: AuthenticationIn) -> StubOut:
    return StubOut(implemented=False, detail=AUTH_STUB)


@router.post(
    "/deauthentication",
    response_model=StubOut,
    summary="Деавторизация (заглушка)",
)
async def deauthenticate() -> StubOut:
    return StubOut(implemented=False, detail=DEAUTH_STUB)
