"""Command-line entry points for Theoxenia's reproducible M0 workflow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from xenia.live.render import render_site
from xenia.live.server import serve
from xenia.live.state import build_state, load_manifests, manifest_paths, read_git_sha
from xenia.provenance import create_run_manifest, input_ref, new_run_id, output_ref
from xenia.schema_validation import validate_recovery_grid_file, validate_state_file
from xenia.schemas import export_schemas


def build_parser() -> argparse.ArgumentParser:
    """Create the user-facing xenia command parser."""
    parser = argparse.ArgumentParser(
        prog="xenia",
        description="Reproducible tools for the Theoxenia public-data research lab.",
    )
    parser.add_argument("--version", action="version", version="xenia 0.1.0")
    top = parser.add_subparsers(dest="group", required=True)

    schemas_parser = top.add_parser("schemas", help="export or check Pydantic JSON Schemas")
    schemas_sub = schemas_parser.add_subparsers(dest="schema_command", required=True)
    export_parser = schemas_sub.add_parser("export", help="write schemas or check freshness")
    export_parser.add_argument("--directory", type=Path, default=Path("schemas"))
    export_parser.add_argument("--check", action="store_true")
    validate_parser = schemas_sub.add_parser(
        "validate-state", help="validate a generated state JSON file against a schema"
    )
    validate_parser.add_argument("--state", type=Path, default=Path("runs/state.json"))
    validate_parser.add_argument(
        "--schema", type=Path, default=Path("schemas/live_state.schema.json")
    )
    validate_floor_parser = schemas_sub.add_parser(
        "validate-floor", help="validate an EXP-002 recovery grid against its schema"
    )
    validate_floor_parser.add_argument("--grid", type=Path, required=True)
    validate_floor_parser.add_argument(
        "--schema", type=Path, default=Path("schemas/recovery_grid.schema.json")
    )

    live_parser = top.add_parser("live", help="Mission Control state and static-site commands")
    live_sub = live_parser.add_subparsers(dest="live_command", required=True)

    build_parser = live_sub.add_parser(
        "build-state", help="aggregate run manifests into runs/state.json"
    )
    build_parser.add_argument("--runs", type=Path, default=Path("runs"))
    build_parser.add_argument("--output", type=Path, default=Path("runs/state.json"))
    build_parser.add_argument("--manifest-root", type=Path, default=Path("runs"))
    build_parser.add_argument("--demo", action="store_true")
    build_parser.add_argument("--repo-url", default="https://github.com/mpetyx/theoxenia")
    build_parser.add_argument("--mirror-url", default=None)
    build_parser.add_argument("--experiment-id", default=None)

    render_parser = live_sub.add_parser("render", help="render the static Mission Control page")
    render_parser.add_argument("--state", type=Path, default=Path("runs/state.json"))
    render_parser.add_argument("--runs", type=Path, default=Path("runs"))
    render_parser.add_argument("--output", type=Path, default=Path("site"))
    render_parser.add_argument("--manifest-root", type=Path, default=Path("runs"))
    render_parser.add_argument("--experiment-id", default=None)

    serve_parser = live_sub.add_parser("serve", help="serve a generated page locally")
    serve_parser.add_argument("--directory", type=Path, default=Path("site"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8080)

    hero_parser = live_sub.add_parser("hero", help="run the Voyager 1 known-answer experiment")
    hero_parser.add_argument("--voyager", action="store_true", required=True)
    hero_parser.add_argument("--source-url", default=None)
    hero_parser.add_argument("--frequency-low-mhz", type=float, default=8419.24)
    hero_parser.add_argument("--frequency-high-mhz", type=float, default=8419.35)
    hero_parser.add_argument("--max-drift-hz-s", type=float, default=4.0)
    hero_parser.add_argument("--minimum-snr", type=float, default=25.0)

    floor_parser = live_sub.add_parser(
        "floor", help="run the seeded synthetic EXP-002 injection/recovery grid"
    )
    floor_parser.add_argument("--mode", choices=("full", "reduced"), default="full")
    floor_parser.add_argument("--seed", type=int, default=20261012)
    floor_parser.add_argument("--experiment-id", default="EXP-002")

    sources_parser = top.add_parser("sources", help="check public data-source endpoints")
    sources_sub = sources_parser.add_subparsers(dest="sources_command", required=True)
    check_parser = sources_sub.add_parser(
        "check", help="probe each catalog row and write sources_check.json"
    )
    check_parser.add_argument("--config", type=Path, default=Path("configs/sources.yaml"))
    check_parser.add_argument("--out", type=Path, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch the CLI and convert expected operational errors to exit code 2."""
    raw_args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(raw_args)
    command = ["xenia", *raw_args]
    root = Path.cwd().resolve()

    try:
        if args.group == "schemas" and args.schema_command == "export":
            directory = _inside_repository(args.directory, root)
            changed = export_schemas(directory, check=args.check)
            if args.check:
                if changed:
                    print(f"Stale schema files: {', '.join(changed)}", file=sys.stderr)
                    return 1
                print("Pydantic schemas are up to date.")
                return 0
            if changed:
                print(f"Wrote schemas: {', '.join(changed)}")
            else:
                print("Schemas are unchanged.")
            return 0

        if args.group == "schemas" and args.schema_command == "validate-state":
            state_path = _inside_repository(args.state, root)
            schema_path = _inside_repository(args.schema, root)
            errors = validate_state_file(state_path, schema_path)
            if errors:
                print("State JSON does not match its schema:", file=sys.stderr)
                for error in errors:
                    print(f"  - {error}", file=sys.stderr)
                return 1
            print(f"{state_path} validates against {schema_path}.")
            return 0

        if args.group == "schemas" and args.schema_command == "validate-floor":
            grid_path = _inside_repository(args.grid, root)
            schema_path = _inside_repository(args.schema, root)
            errors = validate_recovery_grid_file(grid_path, schema_path)
            if errors:
                print("Recovery-grid JSON does not match its schema:", file=sys.stderr)
                for error in errors:
                    print(f"  - {error}", file=sys.stderr)
                return 1
            print(f"{grid_path} validates against {schema_path}.")
            return 0

        if args.group == "live" and args.live_command == "build-state":
            _build_state(args, command=command, root=root)
            return 0

        if args.group == "live" and args.live_command == "render":
            _render(args, command=command, root=root)
            return 0

        if args.group == "live" and args.live_command == "serve":
            if not 0 <= args.port <= 65535:
                parser.error("--port must be between 0 and 65535")
            serve(_inside_repository(args.directory, root), host=args.host, port=args.port)
            return 0

        if args.group == "live" and args.live_command == "hero":
            from xenia.radio.voyager import DEFAULT_SOURCE_URL, run_voyager

            manifest, manifest_path = run_voyager(
                root,
                command,
                source_url=args.source_url or DEFAULT_SOURCE_URL,
                frequency_low_mhz=args.frequency_low_mhz,
                frequency_high_mhz=args.frequency_high_mhz,
                max_drift_hz_s=args.max_drift_hz_s,
                minimum_snr=args.minimum_snr,
            )
            print(
                f"EXP-001 outcome={manifest.outcome}; run_id={manifest.run_id}; "
                f"manifest={manifest_path}"
            )
            return 0

        if args.group == "sources" and args.sources_command == "check":
            from xenia.sources import run_sources_check

            config_path = _inside_repository(args.config, root)
            out_path = _inside_repository(args.out, root)
            document, manifest_path = run_sources_check(
                root,
                command,
                config_path=config_path,
                out_path=out_path,
            )
            verified = sum(item.verdict == "verified" for item in document.results)
            blocked = sum(item.verdict == "blocked" for item in document.results)
            synthetic = sum(item.verdict == "synthetic" for item in document.results)
            print(
                f"sources outcome verified={verified} blocked={blocked} "
                f"synthetic={synthetic}; manifest={_display_path(manifest_path, root)}"
            )
            return 0

        if args.group == "live" and args.live_command == "floor":
            from xenia.radio.floor import run_floor

            manifest, manifest_path = run_floor(
                root,
                command,
                mode=args.mode,
                seed=args.seed,
                experiment_id=args.experiment_id,
            )
            print(
                f"EXP-002 outcome={manifest.outcome}; run_id={manifest.run_id}; "
                f"manifest={manifest_path}"
            )
            return 0

        parser.error("unsupported command")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"xenia: error: {exc}", file=sys.stderr)
        return 2
    return 2


def _build_state(args: argparse.Namespace, *, command: list[str], root: Path) -> None:
    """Build state from fixture or live run manifests and record provenance."""
    started_at = datetime.now(UTC)
    runs_dir = _inside_repository(args.runs, root)
    output_path = _inside_repository(args.output, root)
    manifest_root = _inside_repository(args.manifest_root, root)
    source_paths = manifest_paths(runs_dir)
    manifests = load_manifests(runs_dir)
    input_records = tuple(input_ref(path, repository_root=root) for path in source_paths)
    state = build_state(
        manifests,
        generated_at=started_at,
        git_sha=read_git_sha(root),
        repo_url=args.repo_url,
        mirror_url=args.mirror_url,
    )
    if args.demo and not state.meta.demo:
        state = state.model_copy(update={"meta": state.meta.model_copy(update={"demo": True})})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    finished_at = datetime.now(UTC)
    run_id = new_run_id(started_at, "build-state")
    result_notes = (
        ("Synthetic demo fixture state; no telescope observations were read.",)
        if state.meta.demo
        else ("State was aggregated from validated run manifests.",)
    )
    _, manifest_path = create_run_manifest(
        run_id=run_id,
        command=command,
        parameters={
            "runs": _display_path(runs_dir, root),
            "output": _display_path(output_path, root),
            "demo": state.meta.demo,
        },
        inputs=input_records,
        outputs=(output_ref(output_path, repository_root=root),),
        started_at=started_at,
        finished_at=finished_at,
        outcome="demo_state_built" if state.meta.demo else "state_built",
        notes=result_notes,
        repository_root=root,
        demo=state.meta.demo,
        experiment_id=args.experiment_id,
        manifest_path=manifest_root / run_id / "manifest.json",
    )
    print(
        f"State written to {_display_path(output_path, root)}; "
        f"run_id={run_id}; manifest={_display_path(manifest_path, root)}"
    )


def _render(args: argparse.Namespace, *, command: list[str], root: Path) -> None:
    """Render a static site and record every generated output in a run manifest."""
    started_at = datetime.now(UTC)
    state_path = _inside_repository(args.state, root)
    runs_dir = _inside_repository(args.runs, root)
    output_dir = _inside_repository(args.output, root)
    manifest_root = _inside_repository(args.manifest_root, root)
    input_paths = [state_path, *manifest_paths(runs_dir)]
    input_records = tuple(input_ref(path, repository_root=root) for path in input_paths)
    rendered = render_site(
        state_path=state_path,
        runs_dir=runs_dir,
        output_dir=output_dir,
        repository_root=root,
    )
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    is_demo = bool(state_data["meta"]["demo"])
    output_records = tuple(output_ref(path, repository_root=root) for path in rendered)
    finished_at = datetime.now(UTC)
    run_id = new_run_id(started_at, "render")
    _, manifest_path = create_run_manifest(
        run_id=run_id,
        command=command,
        parameters={
            "state": _display_path(state_path, root),
            "runs": _display_path(runs_dir, root),
            "output": _display_path(output_dir, root),
            "file_count": len(rendered),
        },
        inputs=input_records,
        outputs=output_records,
        started_at=started_at,
        finished_at=finished_at,
        outcome="demo_site_rendered" if is_demo else "site_rendered",
        notes=("Static page rendered from validated state; no JavaScript is required.",),
        repository_root=root,
        demo=is_demo,
        experiment_id=args.experiment_id,
        manifest_path=manifest_root / run_id / "manifest.json",
    )
    print(
        f"Rendered {len(rendered)} files to {_display_path(output_dir, root)}; "
        f"run_id={run_id}; manifest={_display_path(manifest_path, root)}"
    )


def _inside_repository(path: Path, root: Path) -> Path:
    """Resolve a command path and prevent writes outside the checkout."""
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path must stay inside repository: {path}") from exc
    return resolved


def _display_path(path: Path, root: Path) -> str:
    """Format a repository-contained path for logs and manifests."""
    return path.resolve().relative_to(root.resolve()).as_posix()
