from datetime import datetime
from sqlalchemy import String, Text, Enum, DateTime, Integer
from app.db import Base
from sqlalchemy.orm import Mapped, mapped_column

from app.schemas.task import TaskStatus


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        default=TaskStatus.pending,
        nullable=False
    )

    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=True
    )
