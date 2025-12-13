from fastapi import FastAPI

from app.config import settings
from app.api.tasks import router as tasks_router

app = FastAPI(title=settings.APP_NAME)  # или как ты назвал проект


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(tasks_router)
