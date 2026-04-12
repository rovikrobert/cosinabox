"""Tests for AttioClient."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _make_person_record(
    record_id: str, first: str, last: str, title: str = "", company: str = ""
) -> dict:
    return {
        "id": {"record_id": record_id},
        "values": {
            "name": [{"first_name": first, "last_name": last}],
            "job_title": [{"value": title}] if title else [],
            "primary_company": [{"target_record": {"name": company}}] if company else [],
        },
    }


def test_list_people_returns_normalized() -> None:
    from cosinabox.tools.attio import AttioClient

    client = AttioClient(api_key="test-key")
    record = _make_person_record("r1", "Alice", "Smith", "CEO", "Acme")
    with patch.object(client, "_post", return_value={"data": [record]}):
        people = client.list_people(limit=10)
    assert len(people) == 1
    assert people[0]["name"] == "Alice Smith"
    assert people[0]["role"] == "CEO at Acme"
    assert people[0]["id"] == "r1"


def test_get_person_found() -> None:
    from cosinabox.tools.attio import AttioClient

    client = AttioClient(api_key="test-key")
    record = _make_person_record("r2", "Bob", "Jones")
    with patch.object(client, "_post", return_value={"data": [record]}):
        person = client.get_person("Bob")
    assert person is not None
    assert person["name"] == "Bob Jones"


def test_get_person_not_found() -> None:
    from cosinabox.tools.attio import AttioClient

    client = AttioClient(api_key="test-key")
    with patch.object(client, "_post", return_value={"data": []}):
        person = client.get_person("Nobody")
    assert person is None


def test_no_api_key_raises() -> None:
    from cosinabox.tools.attio import AttioClient, AttioError

    with patch.dict("os.environ", {}, clear=True):
        import os

        os.environ.pop("ATTIO_API_KEY", None)
        with pytest.raises(AttioError, match="ATTIO_API_KEY"):
            AttioClient()


def test_update_person_calls_patch() -> None:
    from cosinabox.tools.attio import AttioClient

    client = AttioClient(api_key="test-key")
    record = _make_person_record("r3", "Carol", "White", "CTO", "Beta")
    with patch.object(client, "_patch", return_value={"data": record}) as mock_patch:
        result = client.update_person("r3", {"job_title": [{"value": "CTO"}]})
    mock_patch.assert_called_once_with(
        "/objects/people/records/r3", {"values": {"job_title": [{"value": "CTO"}]}}
    )
    assert result["name"] == "Carol White"
