# ruff: noqa: I001
"""Tests for Keep Warm fields on Attio people records.

Covers the plan milestones:
- M1: parse keep_warm custom fields into _normalize output.
- M2: list_keep_warm + get_keep_warm_overdue.
- M3: set_keep_warm + unset_keep_warm.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch


from cosinabox.defaults import KEEP_WARM_DEFAULT_CADENCE_DAYS
from cosinabox.tools.attio import AttioClient, KeepWarmPerson


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record(
    *,
    name: str = "Sarah Chen",
    record_id: str = "r1",
    keep_warm: bool | None = True,
    cadence: int | None = 14,
    note: str | None = "Lead Investor",
    last_interaction: str | None = None,
    extra: dict | None = None,
) -> dict:
    """Build an Attio /objects/people/records API response item."""
    parts = name.split()
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    values: dict = {
        "name": [{"first_name": first, "last_name": last}],
        "job_title": [],
        "primary_company": [],
    }
    if keep_warm is True:
        values["keep_warm"] = [{"value": True}]
    elif keep_warm is False:
        values["keep_warm"] = [{"value": False}]
    if cadence is not None:
        values["keep_warm_cadence_days"] = [{"value": cadence}]
    if note is not None:
        values["keep_warm_note"] = [{"value": note}]
    if last_interaction is not None:
        values["last_interaction"] = [{"value": last_interaction}]
    if extra:
        values.update(extra)
    return {"id": {"record_id": record_id}, "values": values}


def _client(
    *, post_returns: list[dict] | None = None, patch_returns: dict | None = None
) -> AttioClient:
    """Build an AttioClient with stubbed HTTP methods.

    ``post_returns`` is a FIFO of response bodies for each _post call so we
    can chain get_profile lookups with the list query.
    """
    client = AttioClient.__new__(AttioClient)
    client._headers = {"Authorization": "Bearer test"}
    client._post_calls = []
    client._patch_calls = []

    def _post(path: str, body: dict) -> dict:
        client._post_calls.append((path, body))
        if post_returns:
            return post_returns.pop(0)
        return {"data": []}

    def _patch(path: str, body: dict) -> dict:
        client._patch_calls.append((path, body))
        if patch_returns is not None:
            return patch_returns
        return {"data": {"id": {"record_id": "r1"}, "values": {}}}

    client._post = _post  # type: ignore[method-assign]
    client._patch = _patch  # type: ignore[method-assign]
    return client


# ---------------------------------------------------------------------------
# M1: parse keep_warm fields
# ---------------------------------------------------------------------------


def test_normalize_extracts_keep_warm_true() -> None:
    client = _client()
    r = client._normalize(_record(keep_warm=True, cadence=30, note="founder"))
    assert r["keep_warm"] is True
    assert r["keep_warm_cadence_days"] == 30
    assert r["keep_warm_note"] == "founder"


def test_normalize_missing_keep_warm_defaults_false() -> None:
    client = _client()
    r = client._normalize(_record(keep_warm=None, cadence=None, note=None))
    assert r["keep_warm"] is False
    assert r["keep_warm_cadence_days"] is None
    assert r["keep_warm_note"] is None


def test_normalize_keep_warm_false_kept() -> None:
    client = _client()
    r = client._normalize(_record(keep_warm=False, cadence=None, note=None))
    assert r["keep_warm"] is False


def test_normalize_corrupt_cadence_falls_back_to_none() -> None:
    client = _client()
    raw = _record(cadence=None)
    raw["values"]["keep_warm_cadence_days"] = ["not a dict"]  # corrupt shape
    r = client._normalize(raw)
    assert r["keep_warm_cadence_days"] is None


def test_default_cadence_constant_exists() -> None:
    assert KEEP_WARM_DEFAULT_CADENCE_DAYS == 14


# ---------------------------------------------------------------------------
# M2: list_keep_warm + get_keep_warm_overdue
# ---------------------------------------------------------------------------


def _iso_days_ago(n: int) -> str:
    return (datetime.now(UTC) - timedelta(days=n)).isoformat()


def test_list_keep_warm_posts_server_side_filter() -> None:
    client = _client(post_returns=[{"data": []}])
    client.list_keep_warm()
    path, body = client._post_calls[0]
    assert path == "/objects/people/records/query"
    assert body["filter"] == {"keep_warm": True}
    assert body["limit"] == 200


def test_list_keep_warm_returns_typed_rows_sorted_by_days_since_desc() -> None:
    records = [
        _record(name="Sarah Chen", record_id="r1", cadence=14, last_interaction=_iso_days_ago(5)),
        _record(name="Tom Vasquez", record_id="r2", cadence=30, last_interaction=_iso_days_ago(50)),
        _record(
            name="Ada Lovelace", record_id="r3", cadence=60, last_interaction=_iso_days_ago(20)
        ),
    ]
    client = _client(post_returns=[{"data": records}])
    result = client.list_keep_warm()
    assert isinstance(result[0], KeepWarmPerson)
    # Tom oldest → surfaced first
    assert [p.name for p in result] == ["Tom Vasquez", "Ada Lovelace", "Sarah Chen"]
    assert result[0].days_since == 50
    assert result[0].cadence_days == 30
    assert result[0].record_id == "r2"


def test_list_keep_warm_last_interaction_none_sorts_last() -> None:
    records = [
        _record(name="Known", record_id="r1", last_interaction=_iso_days_ago(10)),
        _record(name="Unknown", record_id="r2", last_interaction=None),
    ]
    client = _client(post_returns=[{"data": records}])
    result = client.list_keep_warm()
    assert [p.name for p in result] == ["Known", "Unknown"]
    assert result[-1].days_since is None


def test_get_keep_warm_overdue_filters_by_cadence() -> None:
    records = [
        _record(
            name="OverdueSarah", record_id="r1", cadence=14, last_interaction=_iso_days_ago(30)
        ),
        _record(name="OnTrackTom", record_id="r2", cadence=30, last_interaction=_iso_days_ago(10)),
        _record(name="UnknownAda", record_id="r3", cadence=60, last_interaction=None),
    ]
    client = _client(post_returns=[{"data": records}])
    overdue = client.get_keep_warm_overdue()
    names = [p.name for p in overdue]
    assert "OverdueSarah" in names
    assert "OnTrackTom" not in names
    assert "UnknownAda" not in names  # None days_since never overdue


def test_list_keep_warm_uses_default_cadence_when_missing() -> None:
    records = [
        _record(name="Defaulted", record_id="r1", cadence=None, last_interaction=_iso_days_ago(20)),
    ]
    client = _client(post_returns=[{"data": records}])
    result = client.list_keep_warm()
    assert result[0].cadence_days == KEEP_WARM_DEFAULT_CADENCE_DAYS


def test_list_keep_warm_empty_response() -> None:
    client = _client(post_returns=[{"data": []}])
    assert client.list_keep_warm() == []
    assert client.get_keep_warm_overdue() == []


def test_list_keep_warm_api_error_returns_empty() -> None:
    client = _client()
    with patch.object(client, "_post", side_effect=Exception("500 err")):
        assert client.list_keep_warm() == []


# ---------------------------------------------------------------------------
# M3: set_keep_warm + unset_keep_warm
# ---------------------------------------------------------------------------


def test_set_keep_warm_happy_path_patches_record() -> None:
    # first _post: get_person lookup
    lookup = {"data": [_record(name="Sarah Chen", record_id="abc")]}
    client = _client(post_returns=[lookup])
    out = client.set_keep_warm(person="Sarah Chen", cadence_days=14, note="Lead Investor")
    assert out["status"] == "ok"
    assert out["record_id"] == "abc"
    path, body = client._patch_calls[0]
    assert path == "/objects/people/records/abc"
    values = body["values"]
    assert values["keep_warm"] == [{"value": True}]
    assert values["keep_warm_cadence_days"] == [{"value": 14}]
    assert values["keep_warm_note"] == [{"value": "Lead Investor"}]


def test_set_keep_warm_person_not_found() -> None:
    client = _client(post_returns=[{"data": []}])
    out = client.set_keep_warm(person="Ghost", cadence_days=14)
    assert out["status"] == "error"
    assert "Ghost" in out["message"]
    assert client._patch_calls == []


def test_set_keep_warm_clamps_cadence() -> None:
    lookup = {"data": [_record(name="x", record_id="abc")]}
    client = _client(post_returns=[lookup])
    client.set_keep_warm(person="x", cadence_days=0)
    assert client._patch_calls[0][1]["values"]["keep_warm_cadence_days"] == [{"value": 1}]

    lookup2 = {"data": [_record(name="x", record_id="abc")]}
    client2 = _client(post_returns=[lookup2])
    client2.set_keep_warm(person="x", cadence_days=9999)
    assert client2._patch_calls[0][1]["values"]["keep_warm_cadence_days"] == [{"value": 365}]


def test_unset_keep_warm_clears_fields() -> None:
    lookup = {"data": [_record(name="Sarah Chen", record_id="abc")]}
    client = _client(post_returns=[lookup])
    out = client.unset_keep_warm(person="Sarah Chen", note="deprioritized 2026-05-12")
    assert out["status"] == "ok"
    path, body = client._patch_calls[0]
    assert path == "/objects/people/records/abc"
    values = body["values"]
    assert values["keep_warm"] == [{"value": False}]
    assert values["keep_warm_cadence_days"] == []
    assert values["keep_warm_note"] == [{"value": "deprioritized 2026-05-12"}]


def test_unset_keep_warm_person_not_found() -> None:
    client = _client(post_returns=[{"data": []}])
    out = client.unset_keep_warm(person="Ghost")
    assert out["status"] == "error"
    assert client._patch_calls == []
