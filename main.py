from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.cargos import router as cargos_router
from api.handlers import router
from api.users import router as users_router
from core.config import settings
from core.origin import OriginGuardMiddleware
from core.sessions import RedisSessionStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    from redis.asyncio import Redis

    client = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    app.state.sessions = RedisSessionStore(client)
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(
    title="WOLFF — веб-сервис грузов",
    version="4.0.0",
    lifespan=lifespan,
    description="Лабораторная 4: публичное чтение, сессии Redis и cookie. "
    "Начните с регистрации и входа через /api/authentication. "
    "Методы с замком требуют действующую сессию.",
    swagger_ui_parameters={"withCredentials": True},
)
app.add_middleware(OriginGuardMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(cargos_router)
app.include_router(users_router)
app.mount("/static", StaticFiles(directory="cargo_front/static"), name="static")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
