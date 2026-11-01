from datetime import timedelta, timezone

import pytest

from clear_pdf_properties.core import dates

JST = timezone(timedelta(hours=9))


def test_user_roundtrip():
    dt = dates.parse_user("2026-10-30 14:02:11 +09:00")
    assert dt.tzinfo is not None and dt.utcoffset() == timedelta(hours=9)
    assert dates.format_user(dt) == "2026-10-30 14:02:11 +09:00"


def test_user_partial_forms():
    assert dates.parse_user("2026-10-30").year == 2026
    assert dates.parse_user("2026-10-30 14:02").minute == 2
    assert dates.parse_user("2026-10-30T14:02:11Z").utcoffset() == timedelta(0)


def test_user_invalid():
    with pytest.raises(dates.DateParseError):
        dates.parse_user("30/10/2026")
    with pytest.raises(dates.DateParseError):
        dates.parse_user("2026-13-01")


def test_info_date_roundtrip():
    s = "D:20261030140211+09'00'"
    dt = dates.parse_info_date(s)
    assert dates.to_info_date(dt) == s
    assert dates.info_to_user(s) == "2026-10-30 14:02:11 +09:00"
    assert dates.info_to_xmp(s) == "2026-10-30T14:02:11+09:00"


def test_info_date_variants():
    assert dates.parse_info_date("D:20261030").day == 30
    assert dates.parse_info_date("D:20261030140211Z").utcoffset() == timedelta(0)
    assert dates.parse_info_date("D:20261030140211-05'00").utcoffset() == timedelta(hours=-5)


def test_xmp_date_roundtrip():
    s = "2026-10-30T14:02:11+09:00"
    dt = dates.parse_xmp_date(s)
    assert dates.to_xmp_date(dt) == s
    assert dates.xmp_to_user(s) == "2026-10-30 14:02:11 +09:00"


def test_user_to_formats():
    assert dates.user_to_info("2026-10-30 14:02:11 +09:00") == "D:20261030140211+09'00'"
    assert dates.user_to_xmp("2026-10-30 14:02:11 +09:00") == "2026-10-30T14:02:11+09:00"
