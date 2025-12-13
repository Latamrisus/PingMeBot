from datetime import datetime
from enum import Enum
from pydantic import BaseModel, field_validator


class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"


class TaskBase(BaseModel):
    title: str
    description: str | None = None
    due_at: datetime | None = None
    remind_at: datetime | None = None
    status: TaskStatus = TaskStatus.pending

    @field_validator("remind_at")
    @classmethod
    def validate_remind_at(cls, v, info):
        due_at = info.data.get("due_at")
        if v and due_at and v > due_at:
            raise ValueError("remind_at must be <= due_at")
        return v



class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_at: datetime | None = None
    remind_at: datetime | None = None
    status: TaskStatus | None = None


class TaskOut(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
