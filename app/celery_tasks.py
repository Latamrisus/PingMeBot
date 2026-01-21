import asyncio
from datetime import datetime
from app.celery_app import celery_app


@celery_app.task(name="pingmeobt.ping")
def ping():
    print(f"[CELERY] pong at {datetime.now()}")

@celery_app.task(name="pingmebot.send_reminder")
def send_reminder(reminder_id: int):
    asyncio.run(_send_reminder_async(reminder_id))


async def _send_reminder_async(reminder_id: int):
    from sqlalchemy import select
    from app.db import async_session_maker
    from app.models.reminder import TaskReminder
    from app.models.task import Task

    async with async_session_maker() as db:
        res = await db.execute(select(TaskReminder).where(TaskReminder.id == reminder_id))
        reminder = res.scalar_one_or_none()
        if not reminder:
            return

        if reminder.is_sent:
            return

        task = await db.get(Task, reminder.task_id)
        if not task:
            return

        print(
            f"[REMINDER] task_id={task.id} title={task.title!r} "
            f"remind_at={reminder.remind_at} due_at={task.due_at}"
        )

        reminder.is_sent = True
        await db.commit()
