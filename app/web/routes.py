from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.schemas.task import TaskStatus
from app.db import get_db
from app.models import Task, TaskReminder
from app.celery_app import celery_app
from app.utils.dt import app_tz, parse_dt_local_to_utc, fmt_local, utc_to_local, fmt_dtlocal_value

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

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    stmt_next = (
        select(TaskReminder.task_id, func.min(TaskReminder.remind_at))
        .where(
            TaskReminder.is_sent.is_(False),
            TaskReminder.remind_at > now_utc
        )
        .group_by(TaskReminder.task_id)
    )

    res_next = await db.execute(stmt_next)
    next_by_task = {task_id: next_dt for task_id, next_dt in res_next.all()}

    for t in tasks:
        t.next_remind_at = next_by_task.get(t.id)
        t.is_overdue = bool(t.due_at and t.due_at < now_utc)
        t.due_at_display = fmt_local(t.due_at, settings.APP_TZ, "%d.%m.%Y %H:%M")
        t.next_remind_at_display = fmt_local(getattr(t, "next_remind_at", None), settings.APP_TZ, "%d.%m.%Y %H:%M")

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
    tz = app_tz(settings.APP_TZ)
    now_local = datetime.now(tz)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    due_at_utc = parse_dt_local_to_utc(due_at, settings.APP_TZ)
    due_at_local = None

    due_at_local = None
    if due_at:
        due_at_local = datetime.fromisoformat(due_at).replace(tzinfo=tz)

    reminder_candidates_utc: set[datetime] = set()

    if due_at_local:
        for preset in remind_presets:
            candidate: datetime | None = None
            if preset == "3d":
                candidate = due_at_local - timedelta(days=3)
            elif preset == "1d":
                candidate = due_at_local - timedelta(days=1)
            elif preset == "12h":
                candidate = due_at_local - timedelta(hours=12)
            elif preset == "1h":
                candidate = due_at_local - timedelta(hours=1)

            if candidate and candidate > now_local:
                candidate_utc = candidate.astimezone(timezone.utc).replace(tzinfo=None)
                if candidate_utc > now_utc:
                    reminder_candidates_utc.add(candidate_utc)

    custom_utc = parse_dt_local_to_utc(custom_remind_at, settings.APP_TZ)
    if custom_utc and custom_utc > now_utc:
        reminder_candidates_utc.add(custom_utc)

    task = Task(title=title, description=description, due_at=due_at_utc)
    db.add(task)
    await db.flush()

    reminders = [
        TaskReminder(task_id=task.id, remind_at=dt) for dt in sorted(reminder_candidates_utc)
    ]

    if reminders:
        db.add_all(reminders)
        await db.flush()

    await db.commit()

    if reminders:
        for r in reminders:
            eta_utc = r.remind_at.replace(tzinfo=timezone.utc)
            celery_app.send_task(
                "pingmebot.send_reminder",
                args=[r.id],
                eta=eta_utc,
            )
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

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    res = await db.execute(
        select(func.min(TaskReminder.remind_at))
        .where(
            TaskReminder.task_id == task.id,
            TaskReminder.is_sent.is_(False),
            TaskReminder.remind_at > now_utc,
        )
    )
    nearest_remind_at = res.scalar_one_or_none()

    return templates.TemplateResponse(
        "task_edit.html",
        {
            "request": request,
            "task": task,
            "due_at_value": fmt_dtlocal_value(task.due_at),
            "custom_value": fmt_dtlocal_value(nearest_remind_at),
        },
    )


@router.post("/web/tasks/{task_id}/edit", include_in_schema=False)
async def update_task_page(
        task_id: int,
        request: Request,
        title: str = Form(...),
        description: str = Form(""),
        due_at: str | None = Form(None),
        remind_presets: list[str] = Form([]),
        remind_at: str | None = Form(None),
        status: str | None = Form(None),
        db: AsyncSession = Depends(get_db)
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.title = title
    task.description = description or None

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    task.due_at = parse_dt_local_to_utc(due_at, settings.APP_TZ)

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

            if candidate and candidate > now_utc:
                reminder_candidates.add(candidate)

    custom_dt = parse_dt_local_to_utc(remind_at, settings.APP_TZ)
    if custom_dt and custom_dt > now_utc:
        reminder_candidates.add(custom_dt)

    def norm(dt: datetime) -> datetime:
        return dt.replace(second=0, microsecond=0)

    candidates_n = {norm(dt) for dt in reminder_candidates}

    res_existing = await db.execute(
        select(TaskReminder.id, TaskReminder.remind_at, TaskReminder.is_sent)
        .where(TaskReminder.task_id == task.id)
    )
    rows = res_existing.all()

    existing_times: set[datetime] = set()
    to_disable_ids: list[int] = []

    for rid, rdt, is_sent in rows:
        rdt_n = norm(rdt)
        existing_times.add(rdt_n)

        if is_sent:
            continue

        invalid = (rdt_n <= now_utc) or (task.due_at is not None and rdt_n > task.due_at)
        if invalid:
            to_disable_ids.append(rid)

    if to_disable_ids:
        await db.execute(
            update(TaskReminder)
            .where(TaskReminder.id.in_(to_disable_ids))
            .values(is_sent=True)
        )

    to_add_times = sorted(candidates_n - existing_times)

    print(to_add_times)

    new_reminders: list[TaskReminder] = []
    for dt in to_add_times:
        if dt <= now_utc:
            continue
        if task.due_at is not None and dt > task.due_at:
            continue
        new_reminders.append(TaskReminder(task_id=task.id, remind_at=dt))

    if new_reminders:
        db.add_all(new_reminders)
        await db.flush()

    print(new_reminders)

    await db.commit()

    if new_reminders and task.status != TaskStatus.done:
        for r in new_reminders:
            eta_utc = r.remind_at.replace(tzinfo=timezone.utc)
            celery_app.send_task(
                "pingmebot.send_reminder",
                args=[r.id],
                eta=eta_utc,
            )

    return RedirectResponse(url="/web/tasks", status_code=303)
