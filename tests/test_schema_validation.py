"""JSON Schema contract tests for the checked-in Pydantic schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xenia.schema_validation import validate_recovery_grid_file, validate_state_file

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPOSITORY_ROOT / "schemas" / "live_state.schema.json"
RECOVERY_SCHEMA_PATH = REPOSITORY_ROOT / "schemas" / "recovery_grid.schema.json"


def test_demo_state_matches_committed_json_schema(demo_state, tmp_path: Path) -> None:
    """The public JSON Schema accepts the exact state model used by the page."""
    state_path = tmp_path / "state.json"
    state_path.write_text(demo_state.model_dump_json(indent=2), encoding="utf-8")
    assert validate_state_file(state_path, SCHEMA_PATH) == ()


def test_schema_validator_reports_field_path_for_invalid_state(demo_state, tmp_path: Path) -> None:
    """A type error is reported with the JSON path instead of being hidden."""
    state = demo_state.model_dump(mode="json")
    state["meta"]["demo"] = "yes"
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    errors = validate_state_file(state_path, SCHEMA_PATH)
    assert errors
    assert any("meta.demo" in error for error in errors)


def test_invalid_schema_is_reported_as_clear_value_error(tmp_path: Path) -> None:
    """A stale or hand-edited schema fails before any data comparison."""
    state_path = tmp_path / "state.json"
    state_path.write_text("{}\n", encoding="utf-8")
    schema_path = tmp_path / "schema.json"
    schema_path.write_text('{"type": "not-a-json-schema-type"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON Schema"):
        validate_state_file(state_path, schema_path)


def test_unreadable_state_json_is_reported(tmp_path: Path) -> None:
    """Malformed output fails with the state path in the diagnostic."""
    state_path = tmp_path / "state.json"
    state_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read state JSON"):
        validate_state_file(state_path, SCHEMA_PATH)


def test_reduced_recovery_grid_matches_committed_json_schema(
    reduced_recovery_grid,
    tmp_path: Path,
) -> None:
    """The per-trial synthetic EXP-002 artifact matches its checked-in contract."""
    grid_path = tmp_path / "recovery_grid.json"
    grid_path.write_text(reduced_recovery_grid.model_dump_json(indent=2), encoding="utf-8")
    assert validate_recovery_grid_file(grid_path, RECOVERY_SCHEMA_PATH) == ()


def test_recovery_grid_schema_reports_invalid_source_kind(
    reduced_recovery_grid,
    tmp_path: Path,
) -> None:
    """The schema rejects relabeling synthetic setigen output as observational data."""
    artifact = reduced_recovery_grid.model_dump(mode="json")
    artifact["source_kind"] = "observational"
    grid_path = tmp_path / "recovery_grid.json"
    grid_path.write_text(json.dumps(artifact), encoding="utf-8")
    errors = validate_recovery_grid_file(grid_path, RECOVERY_SCHEMA_PATH)
    assert any("source_kind" in error for error in errors)
