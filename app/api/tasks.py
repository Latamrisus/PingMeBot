from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.db import get_db
from app.models import Task
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"]
)


@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
        payload: TaskCreate,
        db: AsyncSession = Depends(get_db)
):
    now = datetime.now(timezone.utc)

    if payload.due_at and payload.due_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="due_at must be in the future"
        )

    if payload.due_at and payload.remind_at and payload.remind_at > payload.due_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="remind_at must be <= due_at"
        )

    task = Task(**payload.model_dump())
    db.add(task)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task with same something already exists"
        )
    await db.refresh(task)
    return task


@router.get("/", response_model=list[TaskOut], status_code=status.HTTP_200_OK)
async def list_tasks(db: AsyncSession = Depends(get_db)):
    stmt = select(Task).order_by(Task.created_at.desc())
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return tasks


@router.get("/{task_id}", response_model=TaskOut, status_code=status.HTTP_200_OK)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, payload: TaskUpdate, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    await db.delete(task)
    await db.commit()
    return None
