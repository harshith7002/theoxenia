"""CLI integration tests for schemas, state generation, and static rendering."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from xenia.cli import build_parser, main
from xenia.live.models import RunManifest
from xenia.radio import floor as floor_runner
from xenia.radio import voyager as voyager_runner
from xenia.schemas import export_schemas

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEMO_RUNS = REPOSITORY_ROOT / "tests" / "fixtures" / "live"


def _copy_minimal_project(repo: Path) -> None:
    """Prepare only the files required for an isolated CLI integration run."""
    shutil.copytree(DEMO_RUNS, repo / "tests" / "fixtures" / "live")
    shutil.copytree(REPOSITORY_ROOT / "site" / "templates", repo / "site" / "templates")
    shutil.copyfile(REPOSITORY_ROOT / "site" / "styles.css", repo / "site" / "styles.css")


def test_cadence_parser_accepts_the_synthetic_command() -> None:
    """The EXP-004 command is available before any search runs."""
    parser = build_parser()
    args = parser.parse_args(
        [
            "live",
            "cadence",
            "--synthetic",
            "--mode",
            "reduced",
            "--seed",
            "20261012",
            "--experiment-id",
            "EXP-004",
        ]
    )
    assert args.synthetic is True
    assert args.mode == "reduced"
    assert args.seed == 20261012


def test_archive_cadence_parser_accepts_six_files() -> None:
    """The EXP-003 command names the six files and the window before any download."""
    parser = build_parser()
    args = parser.parse_args(
        [
            "live",
            "cadence",
            "--experiment-id",
            "EXP-003",
            "--target",
            "HIP544",
            "--ra-deg",
            "1.6549208333",
            "--dec-deg",
            "29.0205625",
            "--window",
            "1380.0",
            "1381.0",
            "--sources",
            "HIP544",
            "HIP1024",
            "HIP544",
            "HIP114",
            "HIP544",
            "HIP1344",
            "--files",
            "https://example.invalid/a.h5",
            "https://example.invalid/b.h5",
            "https://example.invalid/c.h5",
            "https://example.invalid/d.h5",
            "https://example.invalid/e.h5",
            "https://example.invalid/f.h5",
        ]
    )
    assert args.synthetic is False
    assert args.window == [1380.0, 1381.0]
    assert len(args.files) == 6
    assert args.cadence_id == "bl-opendata-63460"


def test_schema_export_and_check_are_deterministic(tmp_path: Path) -> None:
    """Schema export is stable and check mode never overwrites drift."""
    schema_dir = tmp_path / "schemas"
    assert set(export_schemas(schema_dir)) == {
        "fusion_baseline.schema.json",
        "incident_telemetry.schema.json",
        "live_state.schema.json",
        "run_manifest.schema.json",
        "recovery_grid.schema.json",
        "cadence_truth.schema.json",
        "cadence_recovery.schema.json",
        "sources_check.schema.json",
    }
    assert export_schemas(schema_dir, check=True) == ()
    stale_file = schema_dir / "live_state.schema.json"
    stale_file.write_text('{"stale": true}\n', encoding="utf-8")
    assert export_schemas(schema_dir, check=True) == ("live_state.schema.json",)
    assert stale_file.read_text(encoding="utf-8") == '{"stale": true}\n'


def test_cli_build_and_render_emit_provenance_manifests(tmp_path: Path, monkeypatch) -> None:
    """Both result-producing CLI commands create complete run manifests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _copy_minimal_project(repo)
    monkeypatch.chdir(repo)

    assert (
        main(
            [
                "live",
                "build-state",
                "--runs",
                "tests/fixtures/live",
                "--output",
                "runs/state.json",
                "--demo",
                "--experiment-id",
                "EXP-030",
            ]
        )
        == 0
    )
    state_path = repo / "runs" / "state.json"
    assert state_path.is_file()
    build_manifests = sorted((repo / "runs").glob("*/manifest.json"))
    assert len(build_manifests) == 1
    build_manifest = RunManifest.model_validate_json(build_manifests[0].read_text(encoding="utf-8"))
    assert build_manifest.outcome == "demo_state_built"
    assert build_manifest.demo is True
    assert build_manifest.experiment_id == "EXP-030"
    assert len(build_manifest.inputs) == 4
    assert all(item.sha256 is not None for item in build_manifest.inputs)
    assert any(item.path == "runs/state.json" for item in build_manifest.outputs)
    assert build_manifest.command.startswith("xenia live build-state")

    assert (
        main(
            [
                "live",
                "render",
                "--state",
                "runs/state.json",
                "--runs",
                "tests/fixtures/live",
                "--output",
                "site",
                "--experiment-id",
                "EXP-030",
            ]
        )
        == 0
    )
    assert (repo / "site" / "index.html").is_file()
    all_manifests = [
        RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted((repo / "runs").glob("*/manifest.json"))
    ]
    render_manifest = next(item for item in all_manifests if item.outcome == "demo_site_rendered")
    assert any(item.uri == "runs/state.json" for item in render_manifest.inputs)
    assert any(item.path == "site/index.html" for item in render_manifest.outputs)
    assert render_manifest.demo is True
    assert render_manifest.experiment_id == "EXP-030"


def test_schema_cli_check_returns_nonzero_on_drift(tmp_path: Path, monkeypatch, capsys) -> None:
    """The installed command can detect stale committed schemas."""
    schema_dir = tmp_path / "schemas"
    export_schemas(schema_dir)
    (schema_dir / "run_manifest.schema.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["schemas", "export", "--check", "--directory", str(schema_dir)]) == 1


def test_voyager_cli_dispatches_the_known_answer_defaults(tmp_path: Path, monkeypatch) -> None:
    """The documented hero command forwards its exact M1 defaults to the runner."""
    from types import SimpleNamespace

    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}
    manifest_path = tmp_path / "runs" / "synthetic-run" / "manifest.json"

    def fake_run(root: Path, command: list[str], **kwargs: object):
        captured["root"] = root
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(
            run_id="synthetic-run", outcome="known_answer_detected"
        ), manifest_path

    monkeypatch.setattr(voyager_runner, "run_voyager", fake_run)

    assert main(["live", "hero", "--voyager"]) == 0
    assert captured["root"] == tmp_path
    assert captured["command"] == ["xenia", "live", "hero", "--voyager"]
    assert captured["frequency_low_mhz"] == 8419.24
    assert captured["frequency_high_mhz"] == 8419.35
    assert captured["max_drift_hz_s"] == 4.0
    assert captured["minimum_snr"] == 25.0


def test_floor_cli_dispatches_the_reduced_grid_defaults(tmp_path: Path, monkeypatch) -> None:
    """The PR smoke command forwards a deterministic seed and EXP-002 identifier."""
    from types import SimpleNamespace

    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}
    manifest_path = tmp_path / "runs" / "synthetic-floor" / "manifest.json"

    def fake_run(root: Path, command: list[str], **kwargs: object):
        captured["root"] = root
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(
            run_id="synthetic-floor", outcome="recovery_grid_completed"
        ), manifest_path

    monkeypatch.setattr(floor_runner, "run_floor", fake_run)

    assert main(["live", "floor", "--mode", "reduced", "--seed", "77"]) == 0
    assert captured["root"] == tmp_path
    assert captured["command"] == [
        "xenia",
        "live",
        "floor",
        "--mode",
        "reduced",
        "--seed",
        "77",
    ]
    assert captured["mode"] == "reduced"
    assert captured["seed"] == 77
    assert captured["experiment_id"] == "EXP-002"


def test_cli_rejects_paths_outside_repository(tmp_path: Path, monkeypatch, capsys) -> None:
    """Read/write paths cannot escape the project checkout."""
    monkeypatch.chdir(tmp_path)
    assert main(["live", "build-state", "--runs", "../outside"]) == 2
    assert "path must stay inside repository" in capsys.readouterr().err


def test_cli_validates_state_against_schema(
    tmp_path: Path, monkeypatch, capsys, demo_state
) -> None:
    """The schema subcommand reports both success and JSON-path failures."""
    monkeypatch.chdir(tmp_path)
    export_schemas(tmp_path / "schemas")
    state_path = tmp_path / "runs" / "state.json"
    state_path.parent.mkdir()
    state_path.write_text(demo_state.model_dump_json(indent=2), encoding="utf-8")

    assert main(["schemas", "validate-state"]) == 0
    state = demo_state.model_dump(mode="json")
    state["meta"]["demo"] = "yes"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert main(["schemas", "validate-state"]) == 1
    assert "meta.demo" in capsys.readouterr().err


def test_cli_validates_recovery_grid_against_schema(
    tmp_path: Path,
    monkeypatch,
    capsys,
    reduced_recovery_grid,
) -> None:
    """The dedicated command checks an experiment artifact and reports field errors."""
    monkeypatch.chdir(tmp_path)
    export_schemas(tmp_path / "schemas")
    grid_path = tmp_path / "runs" / "recovery_grid.json"
    grid_path.parent.mkdir()
    grid_path.write_text(reduced_recovery_grid.model_dump_json(indent=2), encoding="utf-8")

    assert main(["schemas", "validate-floor", "--grid", str(grid_path)]) == 0
    grid = reduced_recovery_grid.model_dump(mode="json")
    grid["source_kind"] = "observational"
    grid_path.write_text(json.dumps(grid), encoding="utf-8")
    assert main(["schemas", "validate-floor", "--grid", str(grid_path)]) == 1
    assert "source_kind" in capsys.readouterr().err
