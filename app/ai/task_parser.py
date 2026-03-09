from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp


@dataclass
class TaskDraft:
    title: str
    description: str | None
    due_at_local: str | None
    reminders_local: list[str]


class OpenAITaskParseError(RuntimeError):
    pass


def _extract_output_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    fragments: list[str] = []
    for item in payload.get("output", []):
        for content_item in item.get("content", []):
            text = content_item.get("text")
            if isinstance(text, str) and text.strip():
                fragments.append(text.strip())

    if fragments:
        return "\n".join(fragments)

    raise OpenAITaskParseError("пустой ответ от модели")


def _parse_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        lines = text.splitlines()
        if lines and lines[0].lower().startswith("json"):
            lines = lines[1:]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OpenAITaskParseError("модель вернула не JSON") from exc

    if not isinstance(parsed, dict):
        raise OpenAITaskParseError("ожидался JSON-объект")
    return parsed


def _normalize_local_datetime(value: object, tz_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None
    if " " in normalized and "T" not in normalized:
        normalized = normalized.replace(" ", "T", 1)

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)
    else:
        dt = dt.replace(tzinfo=None)

    return dt.strftime("%Y-%m-%dT%H:%M")


async def parse_task_draft(
    raw_text: str,
    tz_name: str,
    api_key: str,
    model: str,
    api_base: str,
    timeout_seconds: float,
) -> TaskDraft:
    if not api_key:
        raise OpenAITaskParseError("не задан OPENAI_API_KEY")

    today_local = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
    system_prompt = (
        "Ты помощник по разбору задач. "
        "Верни ТОЛЬКО JSON-объект без markdown. "
        "Схема: {"
        '"title": "string", '
        '"description": "string|null", '
        '"due_at_local": "YYYY-MM-DDTHH:MM|null", '
        '"reminders_local": ["YYYY-MM-DDTHH:MM", ...]'
        "}. "
        "Если дата/время не указаны уверенно, ставь null или []. "
        "Не выдумывай факты."
    )
    user_prompt = (
        f"Локальная таймзона: {tz_name}\n"
        f"Текущая локальная дата: {today_local}\n"
        f"Текст пользователя: {raw_text}\n"
        "Разбери в JSON по схеме."
    )

    request_payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
        "temperature": 0.1,
        "max_output_tokens": 300,
    }

    url = f"{api_base.rstrip('/')}/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=request_payload, headers=headers) as response:
            body = await response.text()
            if response.status >= 400:
                raise OpenAITaskParseError(f"ошибка OpenAI API ({response.status}): {body[:200]}")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise OpenAITaskParseError("OpenAI API вернул невалидный JSON") from exc

    parsed = _parse_json_object(_extract_output_text(payload))

    title_raw = parsed.get("title")
    if not isinstance(title_raw, str) or not title_raw.strip():
        raise OpenAITaskParseError("в ответе нет валидного title")
    title = title_raw.strip()

    description_raw = parsed.get("description")
    description: str | None = None
    if isinstance(description_raw, str) and description_raw.strip():
        description = description_raw.strip()

    due_at_local = _normalize_local_datetime(parsed.get("due_at_local"), tz_name)

    reminders_local_raw = parsed.get("reminders_local")
    reminders_local: list[str] = []
    if isinstance(reminders_local_raw, list):
        for item in reminders_local_raw:
            normalized = _normalize_local_datetime(item, tz_name)
            if normalized:
                reminders_local.append(normalized)

    reminders_local = sorted(set(reminders_local))
    return TaskDraft(
        title=title,
        description=description,
        due_at_local=due_at_local,
        reminders_local=reminders_local,
    )
