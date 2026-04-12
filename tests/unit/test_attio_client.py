from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cosinabox.tools.attio import AttioClient


@pytest.fixture
def client() -> AttioClient:
    with patch.dict("os.environ", {"ATTIO_API_KEY": "test-key"}):
        return AttioClient()


def test_list_people_returns_records(client: AttioClient) -> None:
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "data": [
            {
                "id": {"object_id": "ppl_1"},
                "values": {
                    "name": [{"first_name": "Sarah", "last_name": "Chen"}],
                    "job_title": [{"value": "Investor"}],
                    "company": [{"value": "Sequoia"}],
                },
            }
        ]
    }
    with patch.object(client._http, "post", return_value=fake_resp):
        people = client.list_people(limit=10)
    assert len(people) == 1
    assert people[0]["name"] == "Sarah Chen"
    assert people[0]["role"] == "Investor at Sequoia"


def test_get_person_by_name(client: AttioClient) -> None:
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "data": [
            {
                "id": {"object_id": "ppl_1"},
                "values": {
                    "name": [{"first_name": "Sarah", "last_name": "Chen"}],
                    "job_title": [{"value": "Investor"}],
                    "company": [{"value": "Sequoia"}],
                },
            }
        ]
    }
    with patch.object(client._http, "post", return_value=fake_resp):
        person = client.get_person("Sarah Chen")
    assert person is not None
    assert person["name"] == "Sarah Chen"


def test_get_person_returns_none_when_not_found(client: AttioClient) -> None:
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"data": []}
    with patch.object(client._http, "post", return_value=fake_resp):
        person = client.get_person("Nobody")
    assert person is None


def test_client_raises_without_api_key() -> None:
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("ATTIO_API_KEY", None)
        with pytest.raises(RuntimeError, match="ATTIO_API_KEY"):
            AttioClient()


def test_update_person_sends_patch(client: AttioClient) -> None:
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"data": {"id": {"object_id": "ppl_1"}}}
    with patch.object(client._http, "patch", return_value=fake_resp) as mock_patch:
        client.update_person("ppl_1", {"job_title": "CEO"})
    mock_patch.assert_called_once()
