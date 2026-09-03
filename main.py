from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
from api.handlers import router

app = FastAPI(title="tiktok for cargo")

app.include_router(router)
app.mount("/static", StaticFiles(directory="../frontend_cargo_analize/static"), name="static")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
