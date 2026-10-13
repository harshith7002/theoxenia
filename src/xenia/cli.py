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

    cadence_parser = live_sub.add_parser(
        "cadence", help="search one ABACAD cadence and write its verdicts"
    )
    cadence_parser.add_argument(
        "--synthetic",
        action="store_true",
        help="generate the EXP-004 known-answer cadence instead of reading telescope files",
    )
    cadence_parser.add_argument("--mode", choices=("full", "reduced"), default="full")
    cadence_parser.add_argument("--seed", type=int, default=20261012)
    cadence_parser.add_argument("--experiment-id", default="EXP-004")
    cadence_parser.add_argument(
        "--known-sources", type=Path, default=Path("configs/known_sources.yaml")
    )
    cadence_parser.add_argument(
        "--files",
        nargs=6,
        metavar="FILE",
        help="six ABACAD filterbank URLs or local paths, on source first",
    )
    cadence_parser.add_argument(
        "--window",
        nargs=2,
        type=float,
        metavar=("LOW_MHZ", "HIGH_MHZ"),
        help="inclusive frequency window in MHz",
    )
    cadence_parser.add_argument("--target", help="on-source target name for the pointing")
    cadence_parser.add_argument("--ra-deg", type=float, help="catalog right ascension in degrees")
    cadence_parser.add_argument("--dec-deg", type=float, help="catalog declination in degrees")
    cadence_parser.add_argument(
        "--sources",
        nargs=6,
        metavar="NAME",
        help="expected source_name for each file, matched case-insensitively",
    )
    cadence_parser.add_argument(
        "--roles",
        nargs=6,
        default=["A", "B", "A", "C", "A", "D"],
        help="scan roles; the archive search requires A B A C A D",
    )
    cadence_parser.add_argument("--cadence-id", default="bl-opendata-63460")
    cadence_parser.add_argument("--catalog-md5", nargs=6, metavar="MD5")
    cadence_parser.add_argument("--catalog-size-bytes", nargs=6, type=int, metavar="BYTES")
    cadence_parser.add_argument("--max-transfer-bytes", type=int, default=256 * 1024 * 1024)
    cadence_parser.add_argument(
        "--allow-plain-http",
        action="store_true",
        help="recorded flag; public HTTP stays refused because D-018 was not accepted",
    )

    queue_parser = live_sub.add_parser("queue", help="build the cadence queue")
    queue_sub = queue_parser.add_subparsers(dest="queue_command", required=True)
    queue_build = queue_sub.add_parser("build", help="write configs/queue.jsonl")
    queue_build.add_argument("--config", type=Path, default=Path("configs/live.yaml"))
    queue_build.add_argument("--output", type=Path, default=Path("configs/queue.jsonl"))
    queue_build.add_argument("--listing", type=Path, default=None)
    queue_build.add_argument(
        "--listing-url",
        default=(
            "http://seti.berkeley.edu/opendata/api/query-files"
            "?target=HIP544&cadence=1&telescopes=GBT&file-types=HDF5&limit=20"
        ),
    )
    queue_build.add_argument("--cadence-id", default="63460")
    queue_build.add_argument("--receiver", default="L")
    queue_build.add_argument("--limit", type=int, default=200)
    queue_build.add_argument("--synthetic", action="store_true")
    queue_build.add_argument("--seeds", type=int, nargs="+", default=[20261012])

    run_parser = live_sub.add_parser("run", help="process the cadence queue")
    run_parser.add_argument("--once", action="store_true")
    run_parser.add_argument("--forever", action="store_true")
    run_parser.add_argument("--max-pairs", type=int, default=None)
    run_parser.add_argument("--config", type=Path, default=Path("configs/live.yaml"))
    run_parser.add_argument("--queue", type=Path, default=None)

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

        if args.group == "live" and args.live_command == "cadence":
            manifest, manifest_path = _run_cadence(args, command=command, root=root, parser=parser)
            print(
                f"{args.experiment_id} outcome={manifest.outcome}; run_id={manifest.run_id}; "
                f"manifest={manifest_path}"
            )
            return 0

        if args.group == "live" and args.live_command == "queue":
            _build_queue(args, root=root)
            return 0

        if args.group == "live" and args.live_command == "run":
            summary = _run_worker(args, root=root)
            print(
                f"worker pairs_completed={summary.pairs_completed} "
                f"pairs_failed={summary.pairs_failed}"
            )
            return 0

        parser.error("unsupported command")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"xenia: error: {exc}", file=sys.stderr)
        return 2
    return 2


def _run_cadence(
    args: argparse.Namespace,
    *,
    command: list[str],
    root: Path,
    parser: argparse.ArgumentParser,
) -> tuple[object, Path]:
    """Dispatch the synthetic known-answer or one archive cadence."""
    known_sources = _inside_repository(args.known_sources, root)
    if args.synthetic and args.known_sources == Path("configs/known_sources.yaml"):
        known_sources = _inside_repository(Path("configs/fixtures/exp004_known_sources.yaml"), root)
    if args.synthetic:
        from xenia.live.cadence import run_synthetic_cadence

        return run_synthetic_cadence(
            root,
            command,
            seed=args.seed,
            experiment_id=args.experiment_id,
            mode=args.mode,
            known_sources_path=known_sources,
        )
    missing = [
        name
        for name, value in (
            ("--files", args.files),
            ("--window", args.window),
            ("--target", args.target),
            ("--ra-deg", args.ra_deg),
            ("--dec-deg", args.dec_deg),
            ("--sources", args.sources),
        )
        if value is None
    ]
    if missing:
        parser.error("archive cadence requires " + ", ".join(missing))
    from xenia.live.archive_cadence import run_archive_cadence

    return run_archive_cadence(
        root,
        command,
        files=tuple(args.files),
        sources=tuple(args.sources),
        roles=tuple(args.roles),
        window_mhz=(args.window[0], args.window[1]),
        target=args.target,
        ra_deg=args.ra_deg,
        dec_deg=args.dec_deg,
        experiment_id=args.experiment_id,
        cadence_id=args.cadence_id,
        known_sources_path=known_sources,
        catalog_md5=None if args.catalog_md5 is None else tuple(args.catalog_md5),
        catalog_size_bytes=(
            None if args.catalog_size_bytes is None else tuple(args.catalog_size_bytes)
        ),
        max_transfer_bytes=args.max_transfer_bytes,
        allow_plain_http=args.allow_plain_http,
    )


def _run_worker(args: argparse.Namespace, *, root: Path):
    """Run one pass or the forever loop. Push stays off unless THEOXENIA_PUSH is 1."""
    from xenia.live.config import load_live_config
    from xenia.live.worker import GitPublisher, run_worker

    if args.once == args.forever:
        raise ValueError("pass exactly one of --once or --forever")
    if args.max_pairs is not None and args.max_pairs <= 0:
        raise ValueError("--max-pairs must be positive")
    config = load_live_config(_inside_repository(args.config, root))
    queue_path = _inside_repository(
        args.queue if args.queue is not None else Path(config.queue_file),
        root,
    )
    return run_worker(
        root,
        config,
        queue_path,
        once=args.once,
        max_pairs=args.max_pairs,
        publisher=GitPublisher(),
        refresh=lambda: _refresh_page(root),
    )


def _refresh_page(root: Path) -> None:
    """Rebuild state and the static page from the manifests on disk.

    Called on every heartbeat. It does not write another run manifest; the
    worker heartbeat is the record, and a manifest per minute would bury it.
    """
    runs_dir = root / "runs"
    output_path = runs_dir / "state.json"
    started_at = datetime.now(UTC)
    manifests = load_manifests(runs_dir)
    state = build_state(manifests, generated_at=started_at)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        state.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    render_site(
        state_path=output_path,
        runs_dir=runs_dir,
        output_dir=root / "site",
        repository_root=root,
        now=started_at,
    )


def _build_queue(args: argparse.Namespace, *, root: Path) -> None:
    """Write the queue from a local listing, a catalog fetch, or the synthetic plan."""
    from xenia.live.config import load_live_config
    from xenia.live.queue import build_listing_queue, build_synthetic_queue, fetch_listing

    if args.limit <= 0:
        raise ValueError("--limit must be positive")
    config = load_live_config(_inside_repository(args.config, root))
    output = _inside_repository(args.output, root)
    if args.synthetic:
        text = build_synthetic_queue(config=config, seeds=tuple(args.seeds), limit=args.limit)
    else:
        if args.listing is None:
            listing = fetch_listing(args.listing_url)
            listing_url = args.listing_url
        else:
            listing_path = _inside_repository(args.listing, root)
            listing = listing_path.read_bytes()
            listing_url = _display_path(listing_path, root)
        text = build_listing_queue(
            listing,
            config=config,
            listing_url=listing_url,
            receiver=args.receiver,
            limit=args.limit,
            cadence_id=args.cadence_id,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"Wrote {output}")


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
