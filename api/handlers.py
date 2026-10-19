from datetime import UTC, datetime
from math import isfinite

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.cargos import create_cargo
from core.current_user import get_current_user_id
from core.storage import public_media_url
from db.session import get_db
from models.cargo import Cargo
from models.like import Like
from models.user import User  # noqa: F401 — регистрация связанной модели SQLAlchemy

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="cargo_front/templates")
DEFAULT_IMAGE_URL = "/static/img/default-cargo.jpg"
DEFAULT_VIDEO_URL = "/static/vid/gemini_generated_video_076b54a8.mp4"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def apply_default_media(
    cargo: Cargo | None,
    image_url: str = DEFAULT_IMAGE_URL,
    video_url: str = DEFAULT_VIDEO_URL,
) -> Cargo | None:
    if cargo is None:
        return None
    if not cargo.image_url:
        cargo.image_url = image_url
    if not cargo.video_url:
        cargo.video_url = video_url
    cargo.image_url = public_media_url(cargo.image_url)
    cargo.video_url = public_media_url(cargo.video_url)
    return cargo


async def get_user_draft(db: AsyncSession) -> Cargo | None:
    stmt = select(Cargo).where(
        Cargo.publication_status == "draft",
        Cargo.creator_user_id == get_current_user_id(),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def count_interest_marks(db: AsyncSession, cargo_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(Like).where(Like.cargo_id == cargo_id)
    )
    return result.scalar() or 0


@router.get("/")
async def get_cargo_tiles(
    request: Request,
    cargo_mass: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        cargo_mass = float(cargo_mass)
    except (TypeError, ValueError):
        cargo_mass = None

    # Как Hotel.is_deleted == False в методичке: в выдачу только «живые» записи.
    stmt = select(Cargo).where(Cargo.publication_status == "published")

    # Как if search: stmt = stmt.where(Hotel.title.ilike(...))
    if cargo_mass:
        stmt = stmt.where(Cargo.cargo_mass >= cargo_mass)

    result = await db.execute(stmt)
    cargos = result.scalars().all()
    for cargo in cargos:
        apply_default_media(cargo)

    like_counts = dict(
        (
            await db.execute(
                select(Like.cargo_id, func.count(Like.mark_id)).group_by(Like.cargo_id)
            )
        ).all()
    )
    for cargo in cargos:
        cargo.interest_marks = like_counts.get(cargo.cargo_id, 0)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "cargos": cargos,
            "mass_filter": "" if cargo_mass is None else cargo_mass,
        },
    )


@router.get("/cargo/{cargo_id}")
async def get_cargo_detail(
    request: Request,
    cargo_id: int,
    next_video: bool = False,
    db: AsyncSession = Depends(get_db),
):

    if next_video:
        stmt = (
            select(Cargo)
            .where(
                Cargo.publication_status == "published",
                Cargo.cargo_id > cargo_id,
            )
            .order_by(Cargo.cargo_id)
            .limit(1)
        )
        result = await db.execute(stmt)
        cargo = result.scalar_one_or_none()
        if cargo is None:
            stmt = (
                select(Cargo)
                .where(Cargo.publication_status == "published")
                .order_by(Cargo.cargo_id)
                .limit(1)
            )
            result = await db.execute(stmt)
            cargo = result.scalar_one_or_none()
        if cargo is None:
            raise HTTPException(status_code=404, detail="No published cargos")
    else:
        stmt = select(Cargo).where(
            Cargo.publication_status == "published",
            Cargo.cargo_id == cargo_id,
        )
        result = await db.execute(stmt)
        cargo = result.scalar_one_or_none()
        if cargo is None:
            raise HTTPException(status_code=404, detail="Cargo not found")

    apply_default_media(cargo)
    return templates.TemplateResponse(
        request=request,
        name="lenta-podyoma.html",
        context={
            "cargo": cargo,
            "interest_marks": await count_interest_marks(db, cargo.cargo_id),
        },
    )


@router.get("/lift_feed")
async def get_first_video(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Cargo)
        .where(Cargo.publication_status == "published")
        .order_by(Cargo.cargo_id)
        .limit(1)
    )
    result = await db.execute(stmt)
    cargo = result.scalar_one_or_none()
    if cargo is None:
        raise HTTPException(status_code=404, detail="No published cargos")

    return RedirectResponse(url=f"/cargo/{cargo.cargo_id}")


@router.get("/cargo_addition")
async def get_cargo_addition(request: Request, db: AsyncSession = Depends(get_db)):
    draft = apply_default_media(await get_user_draft(db))
    empty = {
        "cargo_name": "",
        "cargo_description": "",
        "publication_status": "",
        "image_url": DEFAULT_IMAGE_URL,
        "video_url": DEFAULT_VIDEO_URL,
        "cargo_mass": "",
        "cargo_volume": "",
    }
    return templates.TemplateResponse(
        request=request,
        name="cargo_addition.html",
        context={
            "cargo": draft if draft is not None else empty,
            "has_draft": draft is not None,
        },
    )


@router.post("/cargo_addition/next")
async def create_draft(
    request: Request,
    cargo_name: str = Form(...),
    image: UploadFile = File(...),
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    await create_cargo(
        request=request, cargo_name=cargo_name, image=image, video=video, db=db,
    )
    return RedirectResponse(url="/cargo_addition", status_code=303)


@router.post("/cargo_addition/publish")
async def publish_draft(
    cargo_name: str = Form(...),
    cargo_description: str = Form(""),
    cargo_mass: str = Form(""),
    cargo_volume: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    draft = await get_user_draft(db)
    if draft is None:
        raise HTTPException(status_code=400, detail="Draft not found")

    try:
        mass = float(cargo_mass.replace(",", ".")) if cargo_mass.strip() else None
        volume = float(cargo_volume.replace(",", ".")) if cargo_volume.strip() else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Масса и объём должны быть числами") from None
    if any(value is not None and (not isfinite(value) or value < 0) for value in (mass, volume)):
        raise HTTPException(status_code=422, detail="Масса и объём должны быть конечными неотрицательными числами")

    draft.cargo_name = cargo_name.strip() or draft.cargo_name
    draft.cargo_description = cargo_description if cargo_description.strip() else None
    draft.cargo_mass = mass
    draft.cargo_volume = volume
    draft.publication_status = "published"
    draft.formed_at = utc_now()
    await db.commit()
    return RedirectResponse(url="/", status_code=303)


@router.post("/cargo/{cargo_id}/delete")
async def delete_cargo(cargo_id: int, db: AsyncSession = Depends(get_db)):
    # Мы не используем ORM delete(), а выполняем сырой SQL-запрос на обновление флага
    update_query = """
        UPDATE cargos 
        SET publication_status = 'deleted' 
        WHERE cargo_id = :id
    """
    
    # Выполняем запрос через курсор
    await db.execute(text(update_query), {"id": cargo_id})
    await db.commit()
    
    # Перенаправляем пользователя обратно на главную страницу
    return RedirectResponse(url="/", status_code=303)
