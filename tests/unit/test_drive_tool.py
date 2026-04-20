# ruff: noqa: I001
"""Tests for cosinabox.tools.google.drive.DriveTool."""

from __future__ import annotations

from unittest.mock import MagicMock

from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

from cosinabox.tools.google.drive import DriveFile, DriveTool, _q_quote


def _file(
    *,
    id: str,
    name: str = "test.pdf",
    mime: str = "application/pdf",
    modified: str = "2026-04-20T10:00:00Z",
    link: str = "https://drive.google.com/x",
) -> dict:
    return {
        "id": id,
        "name": name,
        "mimeType": mime,
        "modifiedTime": modified,
        "webViewLink": link,
    }


def _service_with_files(files: list[dict]) -> MagicMock:
    svc = MagicMock()
    svc.files.return_value.list.return_value.execute.return_value = {"files": files}
    return svc


# ---------------------------------------------------------------------------
# Query escaping
# ---------------------------------------------------------------------------


def test_q_quote_escapes_backslashes_then_single_quotes() -> None:
    assert _q_quote("foo") == "foo"
    assert _q_quote("o'brien") == "o\\'brien"
    # Backslash before single quote — the backslash should be preserved AND
    # the quote escaped.
    assert _q_quote(r"a\b'c") == r"a\\b\'c"


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------


def test_search_returns_typed_files() -> None:
    svc = _service_with_files([_file(id="f1", name="Deck Q3"), _file(id="f2", name="Notes")])
    tool = DriveTool(service=svc)
    result = tool.search("deck", max_results=5)
    assert [f.id for f in result] == ["f1", "f2"]
    assert all(isinstance(f, DriveFile) for f in result)
    assert result[0].name == "Deck Q3"


def test_search_dedupes_across_accounts() -> None:
    # Same file id returned from two accounts — second should be skipped.
    svc_a = _service_with_files([_file(id="same", name="A copy")])
    svc_b = _service_with_files([_file(id="same", name="B copy")])
    tool = DriveTool(services=[svc_a, svc_b])
    result = tool.search("x")
    assert len(result) == 1
    assert result[0].name == "A copy"


def test_search_sorted_by_modified_desc() -> None:
    svc = _service_with_files(
        [
            _file(id="old", modified="2026-01-01T00:00:00Z"),
            _file(id="new", modified="2026-06-01T00:00:00Z"),
            _file(id="mid", modified="2026-03-15T00:00:00Z"),
        ]
    )
    tool = DriveTool(service=svc)
    result = tool.search("x")
    assert [f.id for f in result] == ["new", "mid", "old"]


def test_search_respects_max_results() -> None:
    svc = _service_with_files(
        [_file(id=f"f{i}", modified=f"2026-01-{i + 1:02d}") for i in range(5)]
    )
    tool = DriveTool(service=svc)
    result = tool.search("x", max_results=3)
    assert len(result) == 3


def test_search_empty_query_returns_empty() -> None:
    svc = _service_with_files([_file(id="f1")])
    tool = DriveTool(service=svc)
    assert tool.search("") == []


def test_search_handles_403_missing_scope() -> None:
    """Refresh token without drive.readonly → 403. Should NOT raise; return []."""
    svc = MagicMock()
    resp = MagicMock()
    resp.status = 403
    err = HttpError(resp=resp, content=b"{}")
    svc.files.return_value.list.return_value.execute.side_effect = err
    tool = DriveTool(service=svc)
    assert tool.search("anything") == []


def test_search_handles_generic_exception() -> None:
    svc = MagicMock()
    svc.files.return_value.list.return_value.execute.side_effect = RuntimeError("network flake")
    tool = DriveTool(service=svc)
    assert tool.search("anything") == []


def test_search_one_account_fails_other_succeeds() -> None:
    bad = MagicMock()
    resp = MagicMock()
    resp.status = 403
    bad.files.return_value.list.return_value.execute.side_effect = HttpError(resp=resp, content=b"")

    good = _service_with_files([_file(id="g1")])

    tool = DriveTool(services=[bad, good])
    result = tool.search("x")
    assert [f.id for f in result] == ["g1"]


# ---------------------------------------------------------------------------
# get_file_metadata()
# ---------------------------------------------------------------------------


def test_get_file_metadata_happy() -> None:
    svc = MagicMock()
    svc.files.return_value.get.return_value.execute.return_value = _file(id="f1", name="x")
    tool = DriveTool(service=svc)
    out = tool.get_file_metadata("f1")
    assert out is not None
    assert out["id"] == "f1"


def test_get_file_metadata_not_found_returns_none() -> None:
    svc = MagicMock()
    resp = MagicMock()
    resp.status = 404
    svc.files.return_value.get.return_value.execute.side_effect = HttpError(resp=resp, content=b"")
    tool = DriveTool(service=svc)
    assert tool.get_file_metadata("missing") is None


def test_get_file_metadata_falls_over_to_next_account() -> None:
    bad = MagicMock()
    resp = MagicMock()
    resp.status = 404
    bad.files.return_value.get.return_value.execute.side_effect = HttpError(resp=resp, content=b"")
    good = MagicMock()
    good.files.return_value.get.return_value.execute.return_value = _file(id="f1")
    tool = DriveTool(services=[bad, good])
    assert tool.get_file_metadata("f1") is not None
