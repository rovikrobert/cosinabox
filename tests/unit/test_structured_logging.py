from __future__ import annotations

import pytest

from cosinabox.agent.logging import ToolLogger, classify_error
from cosinabox.memory import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


class TestClassifyError:
    def test_timeout_by_class_name(self):
        class ConnectTimeout(Exception): pass
        assert classify_error(ConnectTimeout("")) == "timeout"

    def test_rate_limit_by_status_code(self):
        exc = Exception("error")
        exc.status_code = 429  # type: ignore[attr-defined]
        assert classify_error(exc) == "rate_limit"

    def test_auth_by_string(self):
        assert classify_error(Exception("401 Unauthorized")) == "auth"

    def test_validation_by_string(self):
        assert classify_error(Exception("missing required field 'to'")) == "validation"

    def test_unknown_defaults_to_api_error(self):
        assert classify_error(Exception("something weird")) == "api_error"

    def test_auth_by_status_403(self):
        exc = Exception("forbidden")
        exc.status_code = 403  # type: ignore[attr-defined]
        assert classify_error(exc) == "auth"

    def test_server_error_by_status_500(self):
        exc = Exception("internal")
        exc.status_code = 500  # type: ignore[attr-defined]
        assert classify_error(exc) == "api_error"


class TestToolLogger:
    def test_log_success(self, mem):
        tl = ToolLogger(db=mem)
        tl.log(session_id="s1", tool_name="gmail_search", duration_ms=150, error=None)
        cur = mem._conn.execute("SELECT * FROM tool_logs WHERE session_id = 's1'")
        row = cur.fetchone()
        assert row["tool_name"] == "gmail_search"
        assert row["duration_ms"] == 150
        assert row["error_type"] == "none"

    def test_log_error(self, mem):
        tl = ToolLogger(db=mem)
        tl.log(session_id="s1", tool_name="gmail_send", duration_ms=500, error=Exception("429 rate limited"))
        cur = mem._conn.execute("SELECT error_type FROM tool_logs WHERE session_id = 's1'")
        assert cur.fetchone()["error_type"] == "rate_limit"

    def test_empty_logs_query(self, mem):
        cur = mem._conn.execute("SELECT COUNT(*) FROM tool_logs")
        assert cur.fetchone()[0] == 0
