from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from models.cargo import Cargo
from models.like import Like
from models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="cargo_front/templates")

CURRENT_USER_ID = 1
DEFAULT_MEDIA_CARGO_ID = 4
DEFAULT_IMAGE_URL = "/static/img/default-cargo.jpg"
DEFAULT_VIDEO_URL = "http://localhost:9000/media/12466938_3840_2160_30fps.mp4"


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
    return cargo


async def load_default_media(db: AsyncSession) -> tuple[str, str]:
    result = await db.execute(
        select(Cargo.image_url, Cargo.video_url).where(
            Cargo.cargo_id == DEFAULT_MEDIA_CARGO_ID
        )
    )
    row = result.one_or_none()
    if row is None:
        return DEFAULT_IMAGE_URL, DEFAULT_VIDEO_URL
    _image_url, video_url = row
    return DEFAULT_IMAGE_URL, video_url or DEFAULT_VIDEO_URL


async def get_user_draft(db: AsyncSession) -> Cargo | None:
    stmt = select(Cargo).where(
        Cargo.publication_status == "draft",
        Cargo.creator_user_id == CURRENT_USER_ID,
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
    default_image, default_video = await load_default_media(db)
    for cargo in cargos:
        apply_default_media(cargo, default_image, default_video)

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
        stmt = select(Cargo).where(Cargo.publication_status == "published")
        result = await db.execute(stmt)
        cargos = result.scalars().all()
        if not cargos:
            raise HTTPException(status_code=404, detail="No published cargos")

        cargo = cargos[0]
        for idx, item in enumerate(cargos):
            if item.cargo_id == cargo_id:
                cargo = cargos[(idx + 1) % len(cargos)]
                break
    else:
        stmt = select(Cargo).where(
            Cargo.publication_status == "published",
            Cargo.cargo_id == cargo_id,
        )
        result = await db.execute(stmt)
        cargo = result.scalar_one_or_none()
        if cargo is None:
            raise HTTPException(status_code=404, detail="Cargo not found")

    default_image, default_video = await load_default_media(db)
    apply_default_media(cargo, default_image, default_video)
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
    stmt = select(Cargo).where(Cargo.publication_status == "published").limit(1)
    result = await db.execute(stmt)
    cargo = result.scalar_one_or_none()
    if cargo is None:
        raise HTTPException(status_code=404, detail="No published cargos")

    return RedirectResponse(url=f"/cargo/{cargo.cargo_id}")


@router.get("/cargo_addition")
async def get_cargo_addition(request: Request, db: AsyncSession = Depends(get_db)):
    default_image, default_video = await load_default_media(db)
    draft = apply_default_media(await get_user_draft(db), default_image, default_video)
    if draft is not None:
        draft.image_url = default_image
        draft.video_url = default_video
    empty = {
        "cargo_name": "",
        "cargo_description": "",
        "publication_status": "",
        "image_url": default_image,
        "video_url": default_video,
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
    cargo_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    draft = await get_user_draft(db)
    if draft is None:
        db.add(
            Cargo(
                cargo_name=cargo_name.strip() or "Новый груз",
                cargo_description="",
                publication_status="draft",
                image_url="",
                video_url="",
                cargo_mass=0,
                cargo_volume=0,
                created_at=utc_now(),
                formed_at=utc_now(),
                creator_user_id=CURRENT_USER_ID,
            )
        )
        await db.commit()
    return RedirectResponse(url="/cargo_addition", status_code=303)


@router.post("/cargo_addition/publish")
async def publish_draft(
    cargo_name: str = Form(...),
    cargo_description: str = Form(""),
    cargo_mass: str = Form("0"),
    cargo_volume: str = Form("0"),
    db: AsyncSession = Depends(get_db),
):
    draft = await get_user_draft(db)
    if draft is None:
        raise HTTPException(status_code=400, detail="Draft not found")

    try:
        mass = int(float(cargo_mass.replace(",", ".")))
        volume = int(float(cargo_volume.replace(",", ".")))
    except ValueError:
        mass, volume = 0, 0

    draft.cargo_name = cargo_name.strip() or draft.cargo_name
    draft.cargo_description = cargo_description
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
