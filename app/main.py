from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.api.tasks import router as tasks_router
from app.web.routes import router as web_router

app = FastAPI(title=settings.APP_NAME)  # или как ты назвал проект

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(tasks_router)
app.include_router(web_router)
