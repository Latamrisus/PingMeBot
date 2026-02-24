from datetime import datetime

from sqlalchemy import Integer, ForeignKey, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TaskReminder(Base):
    __tablename__ = "task_reminders"
    __table_args__ = (
        UniqueConstraint("task_id", "remind_at", name="uq_task_reminders_task_id_remind_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)

    task = relationship("Task", back_populates="reminders")
