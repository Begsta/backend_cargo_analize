"""Сессии с TTL. В ключах Redis хранится SHA-256 от cookie."""

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime

from fastapi import Request

from core.config import settings

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


class SessionStoreUnavailable(Exception):
    """Хранилище сессий не ответило; доступ не предоставляется."""


def session_key(token: str) -> str:
    return "session:" + hashlib.sha256(token.encode()).hexdigest()


class RedisSessionStore:
    def __init__(self, client, ttl: int = settings.SESSION_TTL_SECONDS):
        self.client = client
        self.ttl = ttl

    async def create(self, user_id: int, old_token: str | None = None) -> str:
        token = secrets.token_urlsafe(32)
        data = json.dumps(
            {
                "user_id": user_id,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        try:
            async with self.client.pipeline(transaction=True) as pipe:
                pipe.set(session_key(token), data, ex=self.ttl)
                if old_token and TOKEN_PATTERN.fullmatch(old_token):
                    pipe.delete(session_key(old_token))
                await pipe.execute()
        except Exception as exc:
            raise SessionStoreUnavailable from exc
        return token

    async def user_id(self, token: str) -> int | None:
        if not TOKEN_PATTERN.fullmatch(token):
            return None
        try:
            data = await self.client.get(session_key(token))
        except Exception as exc:
            raise SessionStoreUnavailable from exc
        if data is None:
            return None
        try:
            value = json.loads(data)["user_id"]
            return value if type(value) is int and value > 0 else None
        except (ValueError, TypeError, KeyError):
            return None

    async def delete(self, token: str) -> None:
        if not TOKEN_PATTERN.fullmatch(token):
            return
        try:
            await self.client.delete(session_key(token))
        except Exception as exc:
            raise SessionStoreUnavailable from exc


async def get_session_store(request: Request) -> RedisSessionStore:
    return request.app.state.sessions
