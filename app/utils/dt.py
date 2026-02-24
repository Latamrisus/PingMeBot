from zoneinfo import ZoneInfo
from datetime import datetime, timezone

from app.config import settings


def app_tz(tz_name: str) -> ZoneInfo:
    return ZoneInfo(tz_name)


def parse_dt_local_to_utc(value: str | None, tz_name: str) -> datetime | None:
    if not value:
        return None

    local_naive = datetime.fromisoformat(value)
    local_aware = local_naive.replace(tzinfo=app_tz(tz_name))
    utc_aware = local_aware.astimezone(timezone.utc)
    return utc_aware.replace(tzinfo=None)


def utc_to_local(dt_utc: datetime | None, tz_name: str) -> datetime | None:
    if not dt_utc:
        return None

    utc_aware = dt_utc.replace(tzinfo=timezone.utc)
    return utc_aware.astimezone(app_tz(tz_name))


def fmt_local(dt_utc: datetime | None, tz_name: str, fmt: str) -> str | None:
    dt_local = utc_to_local(dt_utc, tz_name)
    return dt_local.strftime(fmt) if dt_local else None


def fmt_dtlocal_value(dt_utc: datetime | None) -> str:
    dt_local = utc_to_local(dt_utc, settings.APP_TZ)
    return dt_local.strftime("%Y-%m-%dT%H:%M") if dt_local else ""
