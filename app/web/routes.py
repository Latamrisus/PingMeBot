from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.schemas.task import TaskStatus
from app.db import get_db
from app.models import Task

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
            "now": now
        }
    )


@router.post("/web/tasks/create", include_in_schema=False)
async def create_task_page(
        request: Request,
        title: str = Form(...),
        description: str = Form(""),
        due_at: str | None = Form(None),
        remind_at: str | None = Form(None),
        db: AsyncSession = Depends(get_db)
):
    due_at_dt = None
    if due_at:
        try:
            due_at_dt = datetime.fromisoformat(due_at)
        except ValueError:
            due_at_dt = None

    remind_at_dt = None
    if remind_at:
        try:
            remind_at_dt = datetime.fromisoformat(remind_at)
        except ValueError:
            remind_at_dt = None

    if remind_at_dt and due_at_dt and remind_at_dt > due_at_dt:
        remind_at_dt = due_at_dt

    task = Task(title=title, description=description, due_at=due_at_dt, remind_at=remind_at_dt)
    db.add(task)
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
        remind_at: str | None = Form(None),
        status: str | None = Form(None),
        db: AsyncSession = Depends(get_db)
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.title = title
    task.description = description or None

    if due_at:
        try:
            task.due_at = datetime.fromisoformat(due_at)
        except ValueError:
            task.due_at = None
    else:
        task.due_at = None

    if remind_at:
        try:
            task.remind_at = datetime.fromisoformat(remind_at)
        except ValueError:
            task.remind_at = None
    else:
        task.remind_at = None

    if task.remind_at and task.due_at and task.remind_at > task.due_at:
        task.remind_at = task.due_at

    if status:
        try:
            task.status = TaskStatus(status)
        except ValueError:
            pass

    await db.commit()
    return RedirectResponse(url="/web/tasks", status_code=303)
