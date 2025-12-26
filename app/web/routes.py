from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.schemas.task import TaskStatus
from app.db import get_db
from app.models import Task, TaskReminder

router = APIRouter(tags=["web"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/", include_in_schema=False)
async def index():
    return RedirectResponse(url="/web/tasks")


@router.get("/web/tasks", include_in_schema=False)
async def tasks_page(
        request: Request,
        db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).order_by(Task.created_at.desc())
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    now = datetime.utcnow()

    for t in tasks:
        t.is_overdue = bool(t.due_at and t.due_at < now)

    stmt_next = (
        select(TaskReminder.task_id, func.min(TaskReminder.remind_at))
        .where(
            TaskReminder.is_sent.is_(False),
            TaskReminder.remind_at > now
        )
        .group_by(TaskReminder.task_id)
    )

    res_next = await db.execute(stmt_next)
    next_by_task = {task_id: next_dt for task_id, next_dt in res_next.all()}

    for t in tasks:
        t.next_remind_at = next_by_task.get(t.id)

    def sort_key(task: Task):
        return (
            task.due_at is None,
            task.due_at or task.created_at
        )

    tasks_pending = sorted([t for t in tasks if t.status == TaskStatus.pending], key=sort_key)
    tasks_in_progress = sorted([t for t in tasks if t.status == TaskStatus.in_progress], key=sort_key)
    tasks_done = sorted([t for t in tasks if t.status == TaskStatus.done], key=sort_key)

    return templates.TemplateResponse(
        "tasks.html",
        {
            "request": request,
            "tasks_pending": tasks_pending,
            "tasks_in_progress": tasks_in_progress,
            "tasks_done": tasks_done,
        }
    )


@router.post("/web/tasks/create", include_in_schema=False)
async def create_task_page(
        request: Request,
        title: str = Form(...),
        description: str = Form(""),
        due_at: str | None = Form(None),
        remind_presets: list[str] = Form([]),
        custom_remind_at: str | None = Form(None),
        db: AsyncSession = Depends(get_db)
):
    now = datetime.utcnow()

    due_at_dt = None
    if due_at:
        try:
            due_at_dt = datetime.fromisoformat(due_at)
        except ValueError:
            due_at_dt = None

    reminder_candidates: set[datetime] = set()

    if due_at_dt:
        for preset in remind_presets:
            candidate: datetime | None = None
            if preset == "3d":
                candidate = due_at_dt - timedelta(days=3)
            elif preset == "1d":
                candidate = due_at_dt - timedelta(days=1)
            elif preset == "12h":
                candidate = due_at_dt - timedelta(hours=12)
            elif preset == "1h":
                candidate = due_at_dt - timedelta(hours=1)

            if candidate and candidate > now:
                reminder_candidates.add(candidate)

    if custom_remind_at:
        try:
            custom_dt = datetime.fromisoformat(custom_remind_at)
            if custom_dt > now:
                reminder_candidates.add(custom_dt)
        except ValueError:
            pass

    task = Task(title=title, description=description, due_at=due_at_dt)
    db.add(task)
    await db.flush()

    reminders = [
        TaskReminder(task_id=task.id, remind_at=dt) for dt in sorted(reminder_candidates)
    ]

    if reminders:
        db.add_all(reminders)

    await db.commit()
    return RedirectResponse(url="/web/tasks", status_code=303)


@router.post("/web/tasks/{task_id}/start", include_in_schema=False)
async def task_in_progress(
        task_id: int,
        db: AsyncSession = Depends(get_db)
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = TaskStatus.in_progress
    await db.commit()
    return RedirectResponse(url="/web/tasks", status_code=303)


@router.post("/web/tasks/{task_id}/done", include_in_schema=False)
async def task_done(
        task_id: int,
        db: AsyncSession = Depends(get_db)
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = TaskStatus.done

    await db.execute(
        update(TaskReminder)
        .where(TaskReminder.task_id == task.id, TaskReminder.is_sent.is_(False))
        .values(is_sent=True)
    )

    await db.commit()
    return RedirectResponse(url="/web/tasks", status_code=303)


@router.post("/web/tasks/{task_id}/delete", include_in_schema=False)
async def task_done_delete(
        task_id: int,
        db: AsyncSession = Depends(get_db)
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # if task.status != TaskStatus.done:
    #     raise HTTPException(
    #         status_code=400,
    #         detail="Only done tasks can be deleted",
    #     )

    await db.delete(task)
    await db.commit()
    return RedirectResponse(url="/web/tasks", status_code=303)


@router.get("/web/tasks/{task_id}/edit", include_in_schema=False)
async def edit_task_page(
        task_id: int,
        request: Request,
        db: AsyncSession = Depends(get_db)
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return templates.TemplateResponse(
        "task_edit.html",
        {"request": request, "task": task},
    )


@router.post("/web/tasks/{task_id}/edit", include_in_schema=False)
async def update_task_page(
        task_id: int,
        request: Request,
        title: str = Form(...),
        description: str = Form(""),
        due_at: str | None = Form(None),
        remind_presets: list[str] = Form([]),
        custom_remind_at: str | None = Form(None),
        status: str | None = Form(None),
        db: AsyncSession = Depends(get_db)
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.title = title
    task.description = description or None
    now = datetime.now()

    if due_at:
        try:
            task.due_at = datetime.fromisoformat(due_at)
        except ValueError:
            task.due_at = None
    else:
        task.due_at = None

    if status:
        try:
            task.status = TaskStatus(status)
        except ValueError:
            pass

    reminder_candidates: set[datetime] = set()

    if task.due_at:
        for preset in remind_presets:
            candidate = None
            if preset == "3d":
                candidate = task.due_at - timedelta(days=3)
            elif preset == "1d":
                candidate = task.due_at - timedelta(days=1)
            elif preset == "12h":
                candidate = task.due_at - timedelta(hours=12)
            elif preset == "1h":
                candidate = task.due_at - timedelta(hours=1)

            if candidate and candidate > now:
                reminder_candidates.add(candidate)

    if custom_remind_at:
        try:
            custom_dt = datetime.fromisoformat(custom_remind_at)
            if custom_dt > now:
                reminder_candidates.add(custom_dt)
        except ValueError:
            pass

    await db.execute(delete(TaskReminder).where(TaskReminder.task_id == task.id))

    reminders = [
        TaskReminder(task_id=task.id, remind_at=dt) for dt in sorted(reminder_candidates)
    ]
    if reminders:
        db.add_all(reminders)

    await db.commit()
    return RedirectResponse(url="/web/tasks", status_code=303)
