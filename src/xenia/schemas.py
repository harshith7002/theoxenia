"""Export Pydantic models as stable, checked-in JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from xenia.live.cadence_models import CadenceRecovery, CadenceTruth
from xenia.live.models import LiveState, RecoveryGridArtifact, RunManifest

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "live_state.schema.json": LiveState,
    "run_manifest.schema.json": RunManifest,
    "recovery_grid.schema.json": RecoveryGridArtifact,
    "cadence_truth.schema.json": CadenceTruth,
    "cadence_recovery.schema.json": CadenceRecovery,
}


def schema_text(model: type[BaseModel]) -> str:
    """Serialize a Pydantic schema deterministically."""
    document = model.model_json_schema(mode="validation")
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def export_schemas(directory: Path, *, check: bool = False) -> tuple[str, ...]:
    """Write schemas or report which committed schemas differ from the models.

    Returns the names of stale or newly written schemas. In check mode, no files
    are changed; callers should exit non-zero when the returned tuple is non-empty.
    """
    changed: list[str] = []
    if not check:
        directory.mkdir(parents=True, exist_ok=True)

    for filename, model in SCHEMA_MODELS.items():
        expected = schema_text(model)
        destination = directory / filename
        current = destination.read_text(encoding="utf-8") if destination.exists() else None
        if current != expected:
            changed.append(filename)
            if not check:
                destination.write_text(expected, encoding="utf-8")
    return tuple(changed)
