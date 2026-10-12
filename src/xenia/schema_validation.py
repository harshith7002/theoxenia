"""JSON Schema validation helpers used by CI and the developer CLI."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


def validate_state_file(state_path: Path, schema_path: Path) -> tuple[str, ...]:
    """Return validation errors for a state JSON file against a JSON Schema."""
    try:
        instance = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read state JSON {state_path}: {exc}") from exc
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON Schema {schema_path}: {exc}") from exc

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"invalid JSON Schema {schema_path}: {exc.message}") from exc

    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(instance), key=lambda error: error.json_path)
    return tuple(f"{error.json_path}: {error.message}" for error in errors)
