from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from ui.presentation import format_message_time, private_path_label, short_chunk_id


@pytest.mark.parametrize(
    "value,zone,expected",
    [
        ("2026-10-27T14:58:01.123456+00:00", "Australia/Sydney", "2026-10-28 01:58"),
        ("2026-06-30T23:30:00+00:00", "Australia/Sydney", "2026-07-01 09:30"),
        ("2026-01-01T01:00:00Z", "America/Los_Angeles", "2025-12-31 17:00"),
        ("2026-10-03T15:30:00+00:00", "Australia/Sydney", "2026-10-04 01:30"),
        ("2026-10-03T16:30:00+00:00", "Australia/Sydney", "2026-10-04 03:30"),
    ],
)
def test_local_time_date_boundaries_and_dst(value, zone, expected):
    assert format_message_time(value, ZoneInfo(zone)) == expected


def test_local_time_defaults_to_system_and_preserves_utc_input():
    value = "2026-10-27T14:58:01.123456+00:00"
    expected = datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    assert format_message_time(value) == expected
    assert format_message_time("2026-10-27T14:58:01", UTC) == "2026-10-27 14:58"
    assert value == "2026-10-27T14:58:01.123456+00:00"


@pytest.mark.parametrize("value", ["invalid", "", None])
def test_invalid_time_has_safe_fallback(value):
    assert format_message_time(value) == "时间未知"


def test_default_path_is_an_environment_alias_and_custom_path_is_hidden():
    base = "R:/SyntheticLocalData"
    assert private_path_label(base + "/ProjectRAGAssistant", base) == (
        "%LOCALAPPDATA%" + chr(92) + "ProjectRAGAssistant" + chr(92)
    )
    custom = "R:/SyntheticAccount/custom-data"
    label = private_path_label(custom, base)
    assert "SyntheticAccount" not in label and "custom-data" not in label
    assert "隐藏" in label


def test_chunk_id_display_is_short_but_original_is_unchanged():
    value = "a" * 36 + ":" + "b" * 32 + ":12"
    original = value
    assert len(short_chunk_id(value)) < 24
    assert value.startswith(short_chunk_id(value).split("…")[0])
    assert value.endswith(short_chunk_id(value).split("…")[1])
    assert short_chunk_id("chunk-1") == "chunk-1"
    assert value == original
