from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from data.collections import cargo_lift_collection

router = APIRouter()
templates = Jinja2Templates(directory="../frontend_cargo_analize/templates/")


@router.get("/")
def get_cargo_tiles(request: Request, cargo_mass: str | None = None):
    try:
        cargo_mass =  float(cargo_mass)
    except (TypeError, ValueError):
        cargo_mass = None
    cargos = []
    for cargo in cargo_lift_collection:
        if cargo["publication_status"] != "published":
            continue
        if cargo_mass is not None and cargo["cargo_mass"] < cargo_mass:
            continue
        copy_cargo = dict(cargo)
        copy_cargo["interest_marks"] = len(copy_cargo["interest_marks"])
        cargos.append(copy_cargo)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "cargos": cargos,
            "mass_filter": "" if cargo_mass is None else cargo_mass,
        },
    )


@router.get("/cargo/{cargo_id}")
def get_cargo_detail(request: Request, cargo_id: int, next_video: bool = False):
    published = [
        cargo
        for cargo in cargo_lift_collection
        if cargo["publication_status"] == "published"
    ]
    if not next_video:
        return templates.TemplateResponse(
            request=request,
            name="lenta-podyoma.html",
            context={
                "cargo": next(
                    (cargo for cargo in published if cargo["cargo_id"] == cargo_id),
                    None,
                ),
                "interest_marks": next(
                    (len(cargo["interest_marks"]) for cargo in published if cargo["cargo_id"] == cargo_id),
                    None,
                )
            },
        )

    for idx, cargo in enumerate(published):
        if cargo["cargo_id"] == cargo_id:
            return templates.TemplateResponse(
                request=request,
                name="lenta-podyoma.html",
                context={"cargo": published[(idx+1) % len(published)],
                "interest_marks": len(published[(idx+1) % len(published)]["interest_marks"])},
            )
        


@router.get("/lift_feed")
def get_first_video(request: Request):
    for cargo in cargo_lift_collection:
        if cargo["publication_status"] == "published":
            return get_cargo_detail(request=request, cargo_id=cargo["cargo_id"])


@router.get("/cargo_addition")
def get_cargo_addition(request: Request):
    for cargo in cargo_lift_collection:
        if cargo["publication_status"] == "draft":
            return templates.TemplateResponse(
                request=request,
                name="cargo_addition.html",
                context={"cargo": cargo},
            )
