"""Provenance helpers shared by result-producing xenia commands."""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from xenia import __version__
from xenia.live.models import ArtifactRef, InputRef, ManifestPayload, RunManifest
from xenia.live.state import read_git_sha, sha256_file


def input_ref(path: Path, *, repository_root: Path) -> InputRef:
    """Create a checksum-backed reference to one input file."""
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        uri = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"input {path} must live within repository {repository_root}") from exc
    return InputRef(uri=uri, sha256=sha256_file(resolved), size_bytes=resolved.stat().st_size)


def output_ref(path: Path, *, repository_root: Path) -> ArtifactRef:
    """Create a checksum-backed reference to one output artifact."""
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"output {path} must live within repository {repository_root}") from exc
    return ArtifactRef(
        path=relative,
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
    )


def create_run_manifest(
    *,
    run_id: str,
    command: Sequence[str],
    parameters: dict[str, object],
    inputs: Sequence[InputRef],
    outputs: Sequence[ArtifactRef],
    started_at: datetime,
    finished_at: datetime,
    outcome: str,
    notes: Sequence[str],
    repository_root: Path,
    demo: bool,
    pillar: str = "live",
    experiment_id: str | None = None,
    mission_control: ManifestPayload | None = None,
    manifest_path: Path | None = None,
) -> tuple[RunManifest, Path]:
    """Validate, write, and return a run manifest for a completed command."""
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")
    if finished_at.tzinfo is None or finished_at.utcoffset() is None:
        raise ValueError("finished_at must be timezone-aware")
    root = repository_root.resolve()
    destination = manifest_path or root / "runs" / run_id / "manifest.json"
    destination = destination.resolve()
    try:
        relative_path = destination.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("run manifest must be written inside the repository") from exc

    manifest_output = ArtifactRef(path=relative_path, size_bytes=None)
    manifest = RunManifest(
        run_id=run_id,
        pillar=pillar,
        command=shlex.join(command),
        parameters=parameters,
        inputs=tuple(inputs),
        outputs=(*outputs, manifest_output),
        git_sha=read_git_sha(root),
        package_version=__version__,
        started_at=started_at,
        finished_at=finished_at,
        outcome=outcome,
        notes=tuple(notes),
        experiment_id=experiment_id,
        demo=demo,
        mission_control=mission_control,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest, destination


def new_run_id(now: datetime, suffix: str) -> str:
    """Create a UTC, filename-safe run ID with microsecond precision."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("run timestamp must be timezone-aware")
    slug = "".join(char.lower() if char.isalnum() else "-" for char in suffix)
    slug = "-".join(part for part in slug.split("-") if part) or "run"
    return f"{now.astimezone(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{slug}"
