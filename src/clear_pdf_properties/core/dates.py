"""Date conversion between user text, PDF Info format and XMP (ISO 8601) format.

User format:  ``YYYY-MM-DD HH:MM:SS +09:00``  (seconds and offset optional; no offset = local)
Info format:  ``D:20261030140211+09'00'``
XMP format:   ``2026-10-30T14:02:11+09:00``
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

__all__ = [
    "DateParseError",
    "format_user",
    "parse_info_date",
    "parse_user",
    "parse_xmp_date",
    "to_info_date",
    "to_xmp_date",
    "user_to_info",
    "user_to_xmp",
    "info_to_user",
    "xmp_to_user",
    "info_to_xmp",
]


class DateParseError(ValueError):
    """Raised when a date string cannot be parsed."""


_USER_RE = re.compile(
    r"^\s*(?P<y>\d{4})-(?P<mo>\d{1,2})-(?P<d>\d{1,2})"
    r"(?:[ T](?P<h>\d{1,2}):(?P<mi>\d{2})(?::(?P<s>\d{2}))?)?"
    r"\s*(?P<tz>Z|[+-]\d{2}:?\d{2})?\s*$"
)

_INFO_RE = re.compile(
    r"^D:(?P<y>\d{4})(?P<mo>\d{2})?(?P<d>\d{2})?(?P<h>\d{2})?(?P<mi>\d{2})?(?P<s>\d{2})?"
    r"(?P<tz>Z|[+-]\d{2}(?:'\d{2}'?)?)?$"
)


def _tz_from_match(tz: str | None) -> timezone | None:
    if tz is None:
        return None
    if tz == "Z":
        return timezone.utc
    sign = 1 if tz[0] == "+" else -1
    digits = re.sub(r"[^0-9]", "", tz[1:])
    hours = int(digits[:2])
    minutes = int(digits[2:4]) if len(digits) >= 4 else 0
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def _local_tz() -> timezone:
    offset = datetime.now().astimezone().utcoffset() or timedelta(0)
    return timezone(offset)


def parse_user(text: str) -> datetime:
    """Parse user-entered text into an aware datetime. Missing offset means local time."""
    m = _USER_RE.match(text)
    if not m:
        raise DateParseError(f"日時の形式が不正です: {text!r}（例: 2026-10-30 14:02:11 +09:00）")
    g = m.groupdict()
    try:
        dt = datetime(
            int(g["y"]),
            int(g["mo"]),
            int(g["d"]),
            int(g["h"] or 0),
            int(g["mi"] or 0),
            int(g["s"] or 0),
        )
    except ValueError as e:
        raise DateParseError(f"日時の値が不正です: {text!r} ({e})") from e
    tz = _tz_from_match(g["tz"]) or _local_tz()
    return dt.replace(tzinfo=tz)


def parse_info_date(text: str) -> datetime:
    """Parse a PDF Info-dictionary date string (``D:YYYYMMDDHHmmSSOHH'mm'``)."""
    m = _INFO_RE.match(text.strip())
    if not m:
        raise DateParseError(f"PDF 日時の形式が不正です: {text!r}")
    g = m.groupdict()
    try:
        dt = datetime(
            int(g["y"]),
            int(g["mo"] or 1),
            int(g["d"] or 1),
            int(g["h"] or 0),
            int(g["mi"] or 0),
            int(g["s"] or 0),
        )
    except ValueError as e:
        raise DateParseError(f"PDF 日時の値が不正です: {text!r} ({e})") from e
    tz = _tz_from_match(g["tz"]) or _local_tz()
    return dt.replace(tzinfo=tz)


def parse_xmp_date(text: str) -> datetime:
    """Parse an XMP (ISO 8601) date string."""
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError as e:
        raise DateParseError(f"XMP 日時の形式が不正です: {text!r}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_local_tz())
    return dt


def _offset_parts(dt: datetime) -> tuple[str, int, int]:
    off = dt.utcoffset() or timedelta(0)
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return sign, total // 3600, (total % 3600) // 60


def to_info_date(dt: datetime) -> str:
    sign, h, m = _offset_parts(dt)
    return dt.strftime("D:%Y%m%d%H%M%S") + f"{sign}{h:02d}'{m:02d}'"


def to_xmp_date(dt: datetime) -> str:
    sign, h, m = _offset_parts(dt)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f"{sign}{h:02d}:{m:02d}"


def format_user(dt: datetime) -> str:
    sign, h, m = _offset_parts(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S") + f" {sign}{h:02d}:{m:02d}"


# Convenience one-liners ------------------------------------------------------


def user_to_info(text: str) -> str:
    return to_info_date(parse_user(text))


def user_to_xmp(text: str) -> str:
    return to_xmp_date(parse_user(text))


def info_to_user(text: str) -> str:
    return format_user(parse_info_date(text))


def xmp_to_user(text: str) -> str:
    return format_user(parse_xmp_date(text))


def info_to_xmp(text: str) -> str:
    return to_xmp_date(parse_info_date(text))
