from __future__ import annotations

from pathlib import Path

from cosinabox.timezone import (
    get_timezone,
    load_timezone_override,
    persist_timezone,
    resolve_timezone,
    set_timezone,
)


def test_get_timezone_returns_default() -> None:
    # Reset to default
    import cosinabox.defaults as d
    import cosinabox.timezone as tz_mod

    tz_mod._timezone = d.DEFAULT_TIMEZONE
    assert get_timezone() == d.DEFAULT_TIMEZONE


def test_set_timezone_updates_and_returns_previous() -> None:
    import cosinabox.timezone as tz_mod

    tz_mod._timezone = "UTC"
    prev = set_timezone("Asia/Singapore")
    assert prev == "UTC"
    assert get_timezone() == "Asia/Singapore"
    # Reset
    tz_mod._timezone = "UTC"


def test_set_timezone_rejects_invalid() -> None:
    import pytest

    with pytest.raises(KeyError):
        set_timezone("Not/A/Timezone")


def test_resolve_timezone_exact() -> None:
    assert resolve_timezone("America/New_York") == "America/New_York"
    assert resolve_timezone("US/Eastern") == "US/Eastern"
    assert resolve_timezone("Asia/Singapore") == "Asia/Singapore"


def test_resolve_timezone_fuzzy_city() -> None:
    assert resolve_timezone("New York") == "America/New_York"
    assert resolve_timezone("new york") == "America/New_York"
    assert resolve_timezone("Tokyo") == "Asia/Tokyo"


def test_resolve_timezone_no_match() -> None:
    assert resolve_timezone("Fake/Zone") is None
    assert resolve_timezone("nonsense") is None


def test_persist_and_load_roundtrip(tmp_path: Path) -> None:
    import cosinabox.timezone as tz_mod

    tz_mod._timezone = "UTC"
    db = tmp_path / "test.db"
    persist_timezone("America/New_York", db_path=db)
    loaded = load_timezone_override(db_path=db)
    assert loaded == "America/New_York"
    assert get_timezone() == "America/New_York"
    # Reset
    tz_mod._timezone = "UTC"
