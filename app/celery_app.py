from celery import Celery
from app.config import settings

celery_app = Celery(
    "pingmebot",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.celery_tasks"]
)

celery_app.conf.update(
    timezone="Europe/Berlin",
    enable_utc=False,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json"
)