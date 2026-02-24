from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.config import settings
from app.models.reminder import TaskReminder
from app.models.task import Task

SYNC_DATABASE_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")

engine = create_engine(SYNC_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@celery_app.task(name="pingmebot.ping")
def ping():
    print(f"[CELERY] pong at {datetime.now()}")


@celery_app.task(name="pingmebot.send_reminder")
def send_reminder(reminder_id: int):
    with SessionLocal() as db:
        reminder = db.get(TaskReminder, reminder_id)
        if not reminder or reminder.is_sent:
            return

        task = db.get(Task, reminder.task_id)
        if not task:
            return

        print(
            f"[REMINDER] task_id={task.id} title={task.title!r} "
            f"remind_at={reminder.remind_at} due_at={task.due_at}"
        )

        reminder.is_sent = True
        db.commit()
