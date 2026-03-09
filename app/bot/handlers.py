from datetime import datetime, timezone
from html import escape

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.task_parser import OpenAITaskParseError, parse_task_draft
from app.celery_app import celery_app
from app.config import settings
from app.db import async_session_maker
from app.models import Task, TaskReminder
from app.schemas.task import TaskStatus
from app.utils.dt import parse_dt_local_to_utc, fmt_local

router = Router()


def _help_text() -> str:
    return (
        "Команды:\n"
        "/new <текст> — создать задачу\n"
        "/smart_new <текст> — AI разберет текст в задачу + напоминания\n"
        "/list — список задач\n"
        "/start_task <id> — взять в работу\n"
        "/done <id> — завершить\n"
        "/del <id> — удалить\n"
        "/remind <id> <YYYY-MM-DD HH:MM> — добавить напоминание (МСК) и запланировать\n"
    )


async def _resolve_user_id(message: Message) -> int | None:
    if not message.from_user:
        await message.answer("Не удалось определить пользователя Telegram.")
        return None
    return int(message.from_user.id)


async def _get_user_task(db: AsyncSession, task_id: int, telegram_user_id: int) -> Task | None:
    res = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.telegram_user_id == telegram_user_id,
        )
    )
    return res.scalar_one_or_none()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer("PingMeBot готов.\n\n" + _help_text())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_help_text())


@router.message(Command("new"))
async def cmd_new(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Используй: /new <текст задачи>")
        return

    telegram_user_id = await _resolve_user_id(message)
    if telegram_user_id is None:
        return

    title = parts[1].strip()

    async with async_session_maker() as db:
        task = Task(
            telegram_user_id=telegram_user_id,
            title=title[:255],
            description=None,
            due_at=None,
            status=TaskStatus.pending,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

    await message.answer(f"Создано: <b>#{task.id}</b> — {escape(task.title)}")


@router.message(Command("smart_new"))
async def cmd_smart_new(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Используй: /smart_new <текст задачи>")
        return

    telegram_user_id = await _resolve_user_id(message)
    if telegram_user_id is None:
        return

    if not settings.OPENAI_API_KEY:
        await message.answer("Для /smart_new задай OPENAI_API_KEY в .env")
        return

    raw_text = parts[1].strip()

    try:
        draft = await parse_task_draft(
            raw_text=raw_text,
            tz_name=settings.APP_TZ,
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
            api_base=settings.OPENAI_API_BASE,
            timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
        )
    except OpenAITaskParseError as exc:
        await message.answer(f"AI не смог разобрать задачу: {exc}")
        return

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    due_at_utc = parse_dt_local_to_utc(draft.due_at_local, settings.APP_TZ)
    due_was_ignored = False
    if due_at_utc and due_at_utc <= now_utc:
        due_at_utc = None
        due_was_ignored = True

    reminder_times: set[datetime] = set()
    skipped_reminders = 0
    for reminder_local in draft.reminders_local:
        reminder_utc = parse_dt_local_to_utc(reminder_local, settings.APP_TZ)
        if not reminder_utc:
            skipped_reminders += 1
            continue
        if reminder_utc <= now_utc:
            skipped_reminders += 1
            continue
        if due_at_utc and reminder_utc > due_at_utc:
            skipped_reminders += 1
            continue
        reminder_times.add(reminder_utc)

    title = draft.title.strip()[:255]
    if not title:
        title = raw_text[:255]

    description = (draft.description or "").strip() or None

    async with async_session_maker() as db:
        task = Task(
            telegram_user_id=telegram_user_id,
            title=title,
            description=description,
            due_at=due_at_utc,
            status=TaskStatus.pending,
        )
        db.add(task)
        await db.flush()

        reminders = [
            TaskReminder(task_id=task.id, remind_at=remind_at_utc)
            for remind_at_utc in sorted(reminder_times)
        ]

        if reminders:
            db.add_all(reminders)
            await db.flush()

        await db.commit()
        await db.refresh(task)

    for reminder in reminders:
        eta_utc = reminder.remind_at.replace(tzinfo=timezone.utc)
        celery_app.send_task("pingmebot.send_reminder", args=[reminder.id], eta=eta_utc)

    due_text = fmt_local(task.due_at, settings.APP_TZ, "%d.%m.%Y %H:%M") if task.due_at else "нет"
    msg_lines = [
        f"AI создал задачу: <b>#{task.id}</b> — {escape(task.title)}",
        f"Дедлайн: {due_text}",
        f"Напоминаний: {len(reminders)}",
    ]
    if due_was_ignored:
        msg_lines.append("Примечание: AI предложил дедлайн в прошлом, я его пропустил.")
    if skipped_reminders:
        msg_lines.append(f"Пропущено некорректных/просроченных напоминаний: {skipped_reminders}.")

    await message.answer("\n".join(msg_lines))


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    telegram_user_id = await _resolve_user_id(message)
    if telegram_user_id is None:
        return

    async with async_session_maker() as db:
        res = await db.execute(
            select(Task)
            .where(Task.telegram_user_id == telegram_user_id)
            .order_by(Task.created_at.desc())
        )
        tasks = res.scalars().all()

    if not tasks:
        await message.answer("Пока задач нет. Добавь: /new <текст>")
        return

    def fmt_task(t: Task) -> str:
        due = fmt_local(t.due_at, settings.APP_TZ, "%d.%m %H:%M")
        due_part = f" | ⏰ {due}" if due else ""
        status = t.status.value if isinstance(t.status, TaskStatus) else str(t.status)
        return f"#{t.id} [{status}] {escape(t.title)}{due_part}"

    lines = [fmt_task(t) for t in tasks[:20]]
    await message.answer("\n".join(lines))


@router.message(Command("start_task"))
async def cmd_start_task(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используй: /start_task <id>")
        return

    task_id = int(parts[1])
    telegram_user_id = await _resolve_user_id(message)
    if telegram_user_id is None:
        return

    async with async_session_maker() as db:
        task = await _get_user_task(db, task_id, telegram_user_id)
        if not task:
            await message.answer("Не найдено.")
            return
        task.status = TaskStatus.in_progress
        await db.commit()

    await message.answer(f"Задача #{task_id} → in_progress")


@router.message(Command("done"))
async def cmd_done(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используй: /done <id>")
        return

    task_id = int(parts[1])
    telegram_user_id = await _resolve_user_id(message)
    if telegram_user_id is None:
        return

    async with async_session_maker() as db:
        task = await _get_user_task(db, task_id, telegram_user_id)
        if not task:
            await message.answer("Не найдено.")
            return

        task.status = TaskStatus.done
        await db.execute(
            update(TaskReminder)
            .where(TaskReminder.task_id == task.id, TaskReminder.is_sent.is_(False))
            .values(is_sent=True)
        )
        await db.commit()

    await message.answer(f"Задача #{task_id} → done (напоминания погашены)")


@router.message(Command("del"))
async def cmd_del(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используй: /del <id>")
        return

    task_id = int(parts[1])
    telegram_user_id = await _resolve_user_id(message)
    if telegram_user_id is None:
        return

    async with async_session_maker() as db:
        task = await _get_user_task(db, task_id, telegram_user_id)
        if not task:
            await message.answer("Не найдено.")
            return
        await db.delete(task)
        await db.commit()

    await message.answer(f"Удалено: #{task_id}")


@router.message(Command("remind"))
async def cmd_remind(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 4 or not parts[1].isdigit():
        await message.answer("Используй: /remind <id> <YYYY-MM-DD HH:MM> (МСК)")
        return

    task_id = int(parts[1])
    dt_str = f"{parts[2]} {parts[3]}"

    remind_at_utc = parse_dt_local_to_utc(dt_str, settings.APP_TZ)
    if not remind_at_utc:
        await message.answer("Не понял дату. Пример: /remind 12 2026-02-25 19:00")
        return

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if remind_at_utc <= now_utc:
        await message.answer("Это время уже прошло.")
        return

    telegram_user_id = await _resolve_user_id(message)
    if telegram_user_id is None:
        return

    async with async_session_maker() as db:
        task = await _get_user_task(db, task_id, telegram_user_id)
        if not task:
            await message.answer("Задача не найдена.")
            return
        if task.status == TaskStatus.done:
            await message.answer("Задача уже done — напоминание не добавляю.")
            return
        if task.due_at and remind_at_utc > task.due_at:
            await message.answer("Напоминание после дедлайна — не добавляю.")
            return

        reminder = TaskReminder(task_id=task.id, remind_at=remind_at_utc)
        db.add(reminder)

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            await message.answer("Такое напоминание уже есть.")
            return

        await db.refresh(reminder)

    eta_utc = reminder.remind_at.replace(tzinfo=timezone.utc)
    celery_app.send_task("pingmebot.send_reminder", args=[reminder.id], eta=eta_utc)

    shown = fmt_local(reminder.remind_at, settings.APP_TZ, "%d.%m.%Y %H:%M")
    await message.answer(f"Добавлено напоминание для #{task_id}: 🔔 {shown}")
