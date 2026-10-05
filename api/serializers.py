from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.storage import public_media_url
from models.cargo import Cargo


class CargoOut(BaseModel):
    """Ответ клиенту. Системные поля только для чтения."""

    cargo_id: int
    cargo_name: str
    cargo_description: str
    publication_status: str
    image_url: str
    video_url: str
    image_public_url: str
    video_public_url: str
    cargo_mass: float
    cargo_volume: float
    created_at: datetime
    formed_at: datetime
    creator_user_id: int
    is_creator: Literal[0, 1]
    interest_marks: int


class LikeIn(BaseModel):
    """0 снимает отметку интереса, 1 ставит. Автор берётся из singleton."""

    model_config = ConfigDict(extra="forbid")

    interest: Literal[0, 1] = Field(description="0 — снять лайк, 1 — поставить")


class LikeOut(BaseModel):
    cargo_id: int
    interest: Literal[0, 1]
    interest_marks: int


class UserRegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_login: str = Field(min_length=1, max_length=64)
    user_name: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    user_id: int
    user_login: str
    user_name: str


class AuthenticationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_login: str = Field(min_length=1, max_length=64)
    user_password: str = Field(min_length=1, max_length=128)


class StubOut(BaseModel):
    implemented: bool = False
    detail: str


def cargo_to_out(cargo: Cargo, *, interest_marks: int, current_user_id: int) -> CargoOut:
    return CargoOut(
        cargo_id=cargo.cargo_id,
        cargo_name=cargo.cargo_name,
        cargo_description=cargo.cargo_description,
        publication_status=cargo.publication_status,
        image_url=cargo.image_url,
        video_url=cargo.video_url,
        image_public_url=public_media_url(cargo.image_url),
        video_public_url=public_media_url(cargo.video_url),
        cargo_mass=cargo.cargo_mass,
        cargo_volume=cargo.cargo_volume,
        created_at=cargo.created_at,
        formed_at=cargo.formed_at,
        creator_user_id=cargo.creator_user_id,
        is_creator=1 if cargo.creator_user_id == current_user_id else 0,
        interest_marks=interest_marks,
    )
