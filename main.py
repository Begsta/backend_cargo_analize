import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.cargos import router as cargos_router
from api.handlers import router
from api.users import router as users_router

app = FastAPI(title="WOLFF — веб-сервис грузов")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(cargos_router)
app.include_router(users_router)
app.mount("/static", StaticFiles(directory="cargo_front/static"), name="static")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
