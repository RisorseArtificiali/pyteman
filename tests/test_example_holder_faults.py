"""Holder fault classification and heartbeat robustness for hermes-109966.

The driver classifies holder failures by exception type: only known
WAL-incident signatures count as REPRODUCED; generic faults yield
INCONCLUSIVE. These tests exercise the classification and heartbeat
helpers without requiring hermes-agent.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver():
    with pytest.MonkeyPatch.context() as mp:
        stub = types.ModuleType("hermes_state")
        stub.SessionDB = object
        stub.DeletedWalGenerationError = type("DeletedWalGenerationError", (Exception,), {})
        mp.setitem(sys.modules, "hermes_state", stub)
        stub_dbfile = types.ModuleType("hermes_state_dbfile")
        stub_dbfile.iter_deleted_sqlite_sidecar_holders = lambda _: []
        mp.setitem(sys.modules, "hermes_state_dbfile", stub_dbfile)
        yield load(EXAMPLES / "hermes-109966" / "run_repro.py", "ex109966_driver")


# --- _read_holder_failure ---------------------------------------------------

class TestReadHolderFailure:

    def test_no_failure_when_file_absent(self, driver, tmp_path):
        is_incident, reason = driver._read_holder_failure(str(tmp_path / "no-such"))
        assert is_incident is None
        assert reason == ""

    def test_wal_incident_deleted_wal_generation(self, driver, tmp_path):
        flag = tmp_path / "holder.failed"
        flag.write_text(json.dumps({
            "type": "DeletedWalGenerationError",
            "module": "hermes_state",
            "message": "WAL generation mismatch",
            "phase": "append",
            "tick": 5,
        }))
        is_incident, reason = driver._read_holder_failure(str(flag))
        assert is_incident is True
        assert "DeletedWalGenerationError" in reason
        assert "tick=5" in reason

    def test_wal_incident_operational_error(self, driver, tmp_path):
        flag = tmp_path / "holder.failed"
        flag.write_text(json.dumps({
            "type": "OperationalError",
            "module": "sqlite3",
            "message": "database is locked",
            "phase": "append",
            "tick": 12,
        }))
        is_incident, reason = driver._read_holder_failure(str(flag))
        assert is_incident is True
        assert "OperationalError" in reason

    def test_generic_error_is_not_incident(self, driver, tmp_path):
        flag = tmp_path / "holder.failed"
        flag.write_text(json.dumps({
            "type": "RuntimeError",
            "module": "builtins",
            "message": "something unrelated",
            "phase": "append",
            "tick": 1,
        }))
        is_incident, reason = driver._read_holder_failure(str(flag))
        assert is_incident is False
        assert "RuntimeError" in reason

    def test_permission_error_is_not_incident(self, driver, tmp_path):
        flag = tmp_path / "holder.failed"
        flag.write_text(json.dumps({
            "type": "PermissionError",
            "module": "builtins",
            "message": "Permission denied",
            "phase": "append",
            "tick": 2,
        }))
        is_incident, reason = driver._read_holder_failure(str(flag))
        assert is_incident is False
        assert "PermissionError" in reason

    def test_unreadable_json_is_not_incident(self, driver, tmp_path):
        flag = tmp_path / "holder.failed"
        flag.write_text("not json at all")
        is_incident, reason = driver._read_holder_failure(str(flag))
        assert is_incident is False
        assert "unreadable" in reason

    def test_empty_file_is_not_incident(self, driver, tmp_path):
        flag = tmp_path / "holder.failed"
        flag.write_text("")
        is_incident, reason = driver._read_holder_failure(str(flag))
        assert is_incident is False
        assert "unreadable" in reason

    def test_legacy_repr_format_is_not_incident(self, driver, tmp_path):
        """Old holder.py wrote repr(exc), not JSON. That is a non-incident."""
        flag = tmp_path / "holder.failed"
        flag.write_text("RuntimeError('disk full')")
        is_incident, reason = driver._read_holder_failure(str(flag))
        assert is_incident is False

    def test_missing_type_field_is_not_incident(self, driver, tmp_path):
        flag = tmp_path / "holder.failed"
        flag.write_text(json.dumps({"message": "oops"}))
        is_incident, reason = driver._read_holder_failure(str(flag))
        assert is_incident is False

    @pytest.mark.parametrize("content", ["null", "42", '"hello"', "[1,2,3]"])
    def test_non_dict_json_is_not_incident(self, driver, tmp_path, content):
        flag = tmp_path / "holder.failed"
        flag.write_text(content)
        is_incident, reason = driver._read_holder_failure(str(flag))
        assert is_incident is False
        assert "unreadable" in reason


# --- _read_heartbeat --------------------------------------------------------

class TestReadHeartbeat:

    def test_reads_normal_heartbeat(self, driver, tmp_path):
        hb = tmp_path / "heartbeat"
        hb.write_text("42")
        assert driver._read_heartbeat(str(hb)) == "42"

    def test_missing_file_returns_none(self, driver, tmp_path):
        assert driver._read_heartbeat(str(tmp_path / "no-such")) is None

    def test_empty_file_returns_none(self, driver, tmp_path):
        hb = tmp_path / "heartbeat"
        hb.write_text("")
        assert driver._read_heartbeat(str(hb)) is None

    def test_whitespace_only_returns_none(self, driver, tmp_path):
        hb = tmp_path / "heartbeat"
        hb.write_text("   \n  ")
        assert driver._read_heartbeat(str(hb)) is None

    def test_strips_whitespace(self, driver, tmp_path):
        hb = tmp_path / "heartbeat"
        hb.write_text("  17\n")
        assert driver._read_heartbeat(str(hb)) == "17"


# --- WAL_INCIDENT_TYPES membership ------------------------------------------

class TestWalIncidentTypes:

    def test_known_types(self, driver):
        assert "DeletedWalGenerationError" in driver.WAL_INCIDENT_TYPES
        assert "OperationalError" in driver.WAL_INCIDENT_TYPES

    def test_generic_types_excluded(self, driver):
        for name in ("RuntimeError", "ValueError", "OSError",
                     "PermissionError", "FileNotFoundError"):
            assert name not in driver.WAL_INCIDENT_TYPES
