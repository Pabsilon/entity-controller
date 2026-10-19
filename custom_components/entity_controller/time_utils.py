"""Parsing of time strings (`HH:MM:SS`, `sunset - 00:30:00`, ...) and date helpers."""

import logging
import re
from datetime import datetime, time, timedelta

from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
from homeassistant.core import HomeAssistant
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt

_LOGGER = logging.getLogger(__name__)

_DATETIME_RE = re.compile(r"^(\d+)-(\d+)-(\d+)\s+(\d+):(\d+):(\d+)$")
_TIME_RE = re.compile(r"^(\d+):(\d+):(\d+)$")
_SUN_OFFSET_RE = re.compile(r"^(sunrise|sunset)\s*([+-])\s*(\d+):(\d+):(\d+)$")
_NOW_OFFSET_RE = re.compile(r"^now\s*([+-])\s*(\d+)\s*\(?(\d+)?\)?$")


def parse_time_string(hass: HomeAssistant, time_str: str) -> datetime:
    """Parse a time string into an aware local datetime (today, for times of day)."""
    time_str = str(time_str)
    if parts := _DATETIME_RE.search(time_str):
        return dt.as_local(datetime(*(int(p) for p in parts.groups())))

    if parts := _TIME_RE.search(time_str):
        hour, minute, second = (int(p) for p in parts.groups())
        return dt.as_local(dt.now()).replace(
            hour=hour, minute=minute, second=second, microsecond=0
        )

    if time_str == "sunrise":
        return sunrise(hass)
    if time_str == "sunset":
        return sunset(hass)

    if parts := _SUN_OFFSET_RE.search(time_str):
        event, sign, hours, minutes, seconds = parts.groups()
        base = sunrise(hass) if event == "sunrise" else sunset(hass)
        offset = timedelta(hours=int(hours), minutes=int(minutes), seconds=int(seconds))
        return base + offset if sign == "+" else base - offset

    raise ValueError(f"invalid time string: {time_str}")


def parse_time(hass: HomeAssistant, time_str: str) -> time:
    """Parse a time string into a naive local time of day."""
    return make_naive(parse_time_string(hass, time_str)).time()


def now_is_between(hass: HomeAssistant, start_time_str: str, end_time_str: str) -> bool:
    start_time = parse_time_string(hass, start_time_str)
    end_time = parse_time_string(hass, end_time_str)
    now = dt.as_local(dt.now())
    start_date = now.replace(
        hour=start_time.hour, minute=start_time.minute, second=start_time.second
    )
    end_date = now.replace(
        hour=end_time.hour, minute=end_time.minute, second=end_time.second
    )
    if end_date < start_date:
        # Spans midnight
        if now < start_date and now < end_date:
            now = now + timedelta(days=1)
        end_date = end_date + timedelta(days=1)

    _LOGGER.debug("now_is_between start time %s", start_date)
    _LOGGER.debug("now_is_between end time %s", end_date)
    return start_date <= now <= end_date


def make_naive(dts: datetime) -> datetime:
    """Convert to local time and drop the time zone."""
    return dt.as_local(dts).replace(tzinfo=None)


def sunset(hass: HomeAssistant) -> datetime:
    t = get_astral_event_date(hass, SUN_EVENT_SUNSET, dt.now().date())
    return dt.as_local(t)


def sunrise(hass: HomeAssistant) -> datetime:
    t = get_astral_event_date(hass, SUN_EVENT_SUNRISE, dt.now().date())
    return dt.as_local(t)


def next_sunrise(hass: HomeAssistant, offset: int = 0) -> datetime:
    days = offset
    while (next_rising := sunrise(hass) + timedelta(days)) <= dt.now():
        days += 1
    return next_rising


def next_sunset(hass: HomeAssistant, offset: int = 0) -> datetime:
    days = offset
    while (next_setting := sunset(hass) + timedelta(days)) <= dt.now():
        days += 1
    return next_setting


def futurize(timet: time | datetime) -> datetime:
    """Return the next occurrence of `timet`: today, or tomorrow if it has passed.

    A naive time or datetime is taken to be in HA's time zone.
    """
    now = dt.now()
    if isinstance(timet, datetime):
        t = timet if timet.tzinfo else timet.replace(tzinfo=now.tzinfo)
    else:
        t = datetime.combine(now.date(), timet, tzinfo=now.tzinfo)
    while t <= now:
        t = t + timedelta(days=1)
    return t


def resolve_now_offset(timet: str) -> str:
    """Resolve the `now + N` debugging syntax into a time of day.

    `now + 5 (3)` means 5 seconds from now, except on initial setup where the number
    in brackets is used. Any other string is returned unchanged.
    """
    parts = _NOW_OFFSET_RE.search(timet)
    if not parts:
        return timet

    sign, delay, first_delay = parts.groups()
    delta = timedelta(seconds=int(first_delay if first_delay is not None else delay))
    now = dt.now() - delta if sign == "-" else dt.now() + delta
    return str(make_naive(now).time().replace(microsecond=0))
