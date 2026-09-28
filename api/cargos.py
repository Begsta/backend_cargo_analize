import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.serializers import CargoOut, LikeIn, LikeOut, cargo_to_out
from core.current_user import get_current_user_id
from core.storage import (
    MAX_FILE_BYTES,
    StorageError,
    ensure_bucket,
    extension_for,
    latin_object_name,
    upload_bytes,
)
from db.session import get_db
from models.cargo import (
    STATUS_DELETED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    Cargo,
    utc_now,
)
from models.like import Like
from models.user import User

router = APIRouter(prefix="/api/cargos", tags=["Грузы"])

FORBIDDEN_CLIENT_FIELDS = {
    "cargo_id",
    "publication_status",
    "creator_user_id",
    "moderator_user_id",
    "created_at",
    "formed_at",
    "completed_at",
}


async def _mark_counts(db: AsyncSession, cargo_ids: list[int]) -> dict[int, int]:
    if not cargo_ids:
        return {}
    result = await db.execute(
        select(Like.cargo_id, func.count(Like.mark_id))
        .where(Like.cargo_id.in_(cargo_ids))
        .group_by(Like.cargo_id)
    )
    return {cargo_id: count for cargo_id, count in result.all()}


async def _published(db: AsyncSession) -> list[Cargo]:
    result = await db.execute(
        select(Cargo)
        .where(Cargo.publication_status == STATUS_PUBLISHED)
        .order_by(Cargo.cargo_id)
    )
    return list(result.scalars().all())


async def _visible(db: AsyncSession, cargo_id: int) -> Cargo:
    result = await db.execute(
        select(Cargo).where(
            Cargo.cargo_id == cargo_id,
            Cargo.publication_status != STATUS_DELETED,
        )
    )
    cargo = result.scalar_one_or_none()
    if cargo is None:
        raise HTTPException(status_code=404, detail="Груз не найден")
    return cargo


def _ensure_owner(cargo: Cargo, user_id: int) -> None:
    if cargo.creator_user_id != user_id:
        raise HTTPException(status_code=403, detail="Можно изменять только свои грузы")


async def _outs(db: AsyncSession, cargos: list[Cargo]) -> list[CargoOut]:
    user_id = get_current_user_id()
    counts = await _mark_counts(db, [cargo.cargo_id for cargo in cargos])
    return [
        cargo_to_out(
            cargo,
            interest_marks=counts.get(cargo.cargo_id, 0),
            current_user_id=user_id,
        )
        for cargo in cargos
    ]


async def _out(db: AsyncSession, cargo: Cargo) -> CargoOut:
    return (await _outs(db, [cargo]))[0]


async def _reject_system_fields(request: Request) -> None:
    form = await request.form()
    present = sorted(FORBIDDEN_CLIENT_FIELDS.intersection(form.keys()))
    if present:
        names = ", ".join(present)
        raise HTTPException(
            status_code=422,
            detail=f"Системные поля нельзя передавать: {names}",
        )


async def _require_user(db: AsyncSession, user_id: int) -> None:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=409,
            detail=f"Пользователь {user_id} из singleton не найден в таблице users",
        )


async def _store_media(kind: str, upload: UploadFile) -> str:
    data = await upload.read()
    if not data:
        title = "изображения" if kind == "image" else "видео"
        raise HTTPException(status_code=422, detail=f"Файл {title} пустой")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 30 МБ")
    try:
        extension = extension_for(kind, upload.content_type, upload.filename)
        object_name = latin_object_name(kind, extension)
    except StorageError as exc:
        raise HTTPException(status_code=415, detail=exc.detail) from exc
    content_type = upload.content_type or "application/octet-stream"
    try:
        await asyncio.to_thread(upload_bytes, object_name, data, content_type)
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from exc
    return object_name


@router.get("", response_model=list[CargoOut], summary="Список опубликованных грузов")
async def list_cargos(
    cargo_mass: float | None = Query(
        default=None,
        description="Фильтр: масса в тоннах и больше. 0 или пусто — без фильтра",
    ),
    db: AsyncSession = Depends(get_db),
) -> list[CargoOut]:
    if cargo_mass is not None and cargo_mass < 0:
        raise HTTPException(status_code=422, detail="Масса в фильтре не может быть отрицательной")

    stmt = select(Cargo).where(Cargo.publication_status == STATUS_PUBLISHED)
    if cargo_mass:
        stmt = stmt.where(Cargo.cargo_mass >= cargo_mass)
    result = await db.execute(stmt.order_by(Cargo.cargo_id))
    return await _outs(db, list(result.scalars().all()))


@router.get("/feed", response_model=CargoOut, summary="Лента без идентификатора")
async def feed_first(db: AsyncSession = Depends(get_db)) -> CargoOut:
    cargos = await _published(db)
    if not cargos:
        raise HTTPException(status_code=404, detail="Нет опубликованных грузов")
    return await _out(db, cargos[0])


@router.get(
    "/feed/{cargo_id}",
    response_model=CargoOut,
    summary="Лента по идентификатору",
)
async def feed_by_id(
    cargo_id: int,
    next_item: bool = Query(False, alias="next"),
    db: AsyncSession = Depends(get_db),
) -> CargoOut:
    cargos = await _published(db)
    if not cargos:
        raise HTTPException(status_code=404, detail="Нет опубликованных грузов")

    if next_item:
        for cargo in cargos:
            if cargo.cargo_id > cargo_id:
                return await _out(db, cargo)
        return await _out(db, cargos[0])

    for cargo in cargos:
        if cargo.cargo_id == cargo_id:
            return await _out(db, cargo)
    raise HTTPException(status_code=404, detail="Груз не найден")


@router.get("/draft", response_model=CargoOut, summary="Черновик текущего пользователя")
async def get_draft(db: AsyncSession = Depends(get_db)) -> CargoOut:
    result = await db.execute(
        select(Cargo).where(
            Cargo.publication_status == STATUS_DRAFT,
            Cargo.creator_user_id == get_current_user_id(),
        )
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="Черновик не найден")
    return await _out(db, draft)


@router.post("", response_model=CargoOut, status_code=201, summary="Добавление груза")
async def create_cargo(
    request: Request,
    cargo_name: str = Form(...),
    cargo_description: str = Form(""),
    cargo_mass: float = Form(0),
    cargo_volume: float = Form(0),
    image: UploadFile = File(...),
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> CargoOut:
    await _reject_system_fields(request)
    user_id = get_current_user_id()
    await _require_user(db, user_id)

    name = cargo_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Название груза обязательно")
    if len(name) > 256:
        raise HTTPException(status_code=422, detail="Название длиннее 256 символов")
    if cargo_mass < 0 or cargo_volume < 0:
        raise HTTPException(status_code=422, detail="Масса и объём не могут быть отрицательными")

    existing = await db.execute(
        select(Cargo.cargo_id).where(
            Cargo.publication_status == STATUS_DRAFT,
            Cargo.creator_user_id == user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="У пользователя уже есть черновик. Сначала опубликуйте или удалите его",
        )

    try:
        await asyncio.to_thread(ensure_bucket)
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from exc

    image_name = await _store_media("image", image)
    video_name = await _store_media("video", video)
    now = utc_now()
    cargo = Cargo(
        cargo_name=name,
        cargo_description=cargo_description,
        publication_status=STATUS_DRAFT,
        image_url=image_name,
        video_url=video_name,
        cargo_mass=int(cargo_mass),
        cargo_volume=int(cargo_volume),
        created_at=now,
        formed_at=now,
        creator_user_id=user_id,
    )
    db.add(cargo)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="У пользователя уже есть черновик",
        ) from None
    await db.refresh(cargo)
    return await _out(db, cargo)


@router.put(
    "/{cargo_id}",
    response_model=CargoOut,
    summary="Публикация черновика",
)
async def publish_cargo(
    cargo_id: int,
    db: AsyncSession = Depends(get_db),
) -> CargoOut:
    cargo = await _visible(db, cargo_id)
    _ensure_owner(cargo, get_current_user_id())
    if cargo.publication_status != STATUS_DRAFT:
        raise HTTPException(
            status_code=409,
            detail="Вернуть груз в черновик нельзя. Публикация доступна только из черновика",
        )
    cargo.publication_status = STATUS_PUBLISHED
    cargo.formed_at = utc_now()
    await db.commit()
    await db.refresh(cargo)
    return await _out(db, cargo)


@router.delete("/{cargo_id}", status_code=204, summary="Мягкое удаление своего груза")
async def delete_cargo(
    cargo_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    cargo = await _visible(db, cargo_id)
    _ensure_owner(cargo, get_current_user_id())
    cargo.publication_status = STATUS_DELETED
    await db.commit()


@router.post(
    "/{cargo_id}/likes",
    response_model=LikeOut,
    summary="Отметка интереса текущего пользователя",
)
async def set_like(
    cargo_id: int,
    body: LikeIn,
    db: AsyncSession = Depends(get_db),
) -> LikeOut:
    user_id = get_current_user_id()
    await _require_user(db, user_id)

    result = await db.execute(
        select(Cargo).where(
            Cargo.cargo_id == cargo_id,
            Cargo.publication_status == STATUS_PUBLISHED,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Опубликованный груз не найден")

    existing = await db.execute(
        select(Like).where(Like.user_id == user_id, Like.cargo_id == cargo_id)
    )
    mark = existing.scalar_one_or_none()
    if body.interest == 1 and mark is None:
        db.add(Like(user_id=user_id, cargo_id=cargo_id))
    elif body.interest == 0 and mark is not None:
        await db.delete(mark)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Отметка уже стоит") from None

    count = await db.execute(
        select(func.count()).select_from(Like).where(Like.cargo_id == cargo_id)
    )
    return LikeOut(
        cargo_id=cargo_id,
        interest=body.interest,
        interest_marks=count.scalar() or 0,
    )
