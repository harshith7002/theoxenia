"""Curated investigations and verifiable evidence dossiers for the public edition.

Stories are pinned to reviewed source records: a newer experiment never silently
inherits an older story's interpretation. Browser data comes from PUB-001, whose
parent table, counts and artifact checksum are checked before rendering.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import zipfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from jinja2 import Environment

from xenia.live.models import RunManifest
from xenia.live.plots import render_floor_svg, render_sky_svg
from xenia.live.state import build_state, sha256_file

STORIES = (
    {
        "slug": "voyager",
        "number": "01",
        "run_id": "20261012T130904642405Z-exp-001-voyager",
        "title": "A signal with a home.",
        "label": "Voyager 1",
        "kind": "Recorded telescope data",
        "summary": (
            "Find a known spacecraft in a real telescope recording. Start with an "
            "answer we can check."
        ),
        "question": "Can our detector recover a known human transmitter?",
        "conclusion": (
            "The recorded run recovered the Voyager carrier. This is a positive control"
            " for this recording and configuration, not a general sensitivity "
            "guarantee."
        ),
        "steps": [
            (
                "Ask a bounded question",
                (
                    "Use the public Voyager tutorial observation as a known-answer test. The "
                    "target is a known spacecraft transmission."
                ),
            ),
            (
                "Read the waterfall",
                (
                    "Frequency runs horizontally; time runs vertically. A narrow drifting line "
                    "records the carrier's changing received frequency. Brightness is received "
                    "power, not a photograph of the spacecraft."
                ),
            ),
            (
                "Measure the line",
                (
                    "The detector searches across frequency drift rates. The values below are "
                    "recorded outputs; the image is the original plot from that run."
                ),
            ),
            (
                "Keep the conclusion small",
                (
                    "Recovering this carrier demonstrates one successful detection. It does not"
                    " establish that every weaker or faster-drifting signal would be recovered."
                ),
            ),
        ],
        "checks": [
            ("Source", "Measured", "Public telescope recording with a local-slice checksum."),
            ("Recovery", "Recorded", "Carrier measurement and plot preserved together."),
            (
                "Sensitivity",
                "Limited",
                "One positive control; general completeness is not measured.",
            ),
            (
                "External review",
                "Not recorded",
                "No independent acceptance or submission is claimed.",
            ),
        ],
    },
    {
        "slug": "archive",
        "number": "02",
        "run_id": "20261012T203545022355Z-exp-003-cadence",
        "title": "Look at the star. Look away.",
        "label": "HIP544 · six scans",
        "kind": "Recorded telescope data",
        "summary": (
            "Trace 273 labelled rows through a real ON/OFF comparison, including the "
            "questions the run leaves open."
        ),
        "question": "Which recorded lines survive the six-scan comparison?",
        "conclusion": (
            "The stored table contains 149 IN_OFF and 124 SINGLE_POINTING rows, with no"
            " ON_ONLY rows. Later ON scans returned empty detector tables; that "
            "unresolved limitation prevents a broad null-result claim."
        ),
        "steps": [
            (
                "Choose one small window",
                (
                    "The run reads 1380–1381 MHz from six archived Green Bank Telescope "
                    "observations. Three point at HIP544; the others point away. This is one "
                    "cadence, not a sky survey."
                ),
            ),
            (
                "Compare the directions",
                (
                    "A line found in an OFF scan fails the direction test. A line missing from "
                    "one or more ON scans fails repeatability. These are mechanical "
                    "classifications, not identified physical causes."
                ),
            ),
            (
                "Inspect every row",
                (
                    "Explore all 273 classified rows by frequency, drift and signal-to-noise "
                    "ratio. Each row retains its measured ON/OFF counts and the original check "
                    "notes."
                ),
            ),
            (
                "Expose the unfinished checks",
                (
                    "The detector reported empty tables in later ON scans and logging errors. "
                    "No other cadence was supplied for the session census. Neither missing "
                    "check is evidence that the sky is clear."
                ),
            ),
        ],
        "checks": [
            (
                "Source",
                "Measured",
                "Six bounded archive slices; full source files were not hashed.",
            ),
            (
                "Classification",
                "Recorded",
                "Complete table reconciled against the manifest counts.",
            ),
            (
                "Detector health",
                "Open",
                "Empty later ON tables still require a detector-level investigation.",
            ),
            (
                "Session census",
                "Not tested",
                "No other cadence from this observing session was supplied.",
            ),
            (
                "External review",
                "Not recorded",
                "No independent acceptance or submission is claimed.",
            ),
        ],
    },
    {
        "slug": "recovery",
        "number": "03",
        "run_id": "20261012T190848550861Z-exp-002-floor",
        "title": "Learn what we miss.",
        "label": "Injection & recovery",
        "kind": "Synthetic control",
        "summary": (
            "Plant signals with known properties. Explore where the detector "
            "succeeds—and where it misses them."
        ),
        "question": "How does recovery change with injected strength and drift?",
        "conclusion": (
            "Recovery depends strongly on drift and injected strength in this "
            "configuration. No tested strength recovered every trial across ±3 Hz/s. "
            "This is a synthetic detector check, not telescope survey completeness."
        ),
        "steps": [
            (
                "Make the answer known",
                (
                    "Generate synthetic drifting signals with setigen. These are controlled "
                    "inputs, explicitly separate from telescope observations."
                ),
            ),
            (
                "Vary two properties",
                (
                    "Test eight injected SNR levels and nine drift rates, with five trials per "
                    "cell. This records 360 recovery decisions."
                ),
            ),
            (
                "Inspect the misses",
                (
                    "Select a cell to read its recovered count. A result of five out of five "
                    "describes those five trials; it is not proof of perfect detection "
                    "probability."
                ),
            ),
            (
                "Carry the limits forward",
                (
                    "Any interpretation of a future search must account for detector "
                    "sensitivity and failure modes. A blank search table alone cannot establish"
                    " that detectable signals were absent."
                ),
            ),
        ],
        "checks": [
            ("Source", "Synthetic", "Generated controls; no telescope exposure is added."),
            ("Repeatability", "Recorded", "Parameters, seed and recovery decisions preserved."),
            ("Sensitivity", "Limited", "Five trials per cell in one tested configuration."),
            (
                "External review",
                "Not recorded",
                "No independent acceptance or submission is claimed.",
            ),
        ],
    },
)


def available_stories(manifests: Sequence[RunManifest]) -> list[dict[str, Any]]:
    ids = {m.run_id for m in manifests}
    return [
        {**story, "visual_url": f"investigations/{story['slug']}.svg"}
        for story in STORIES
        if story["run_id"] in ids
    ]


def verified_output(manifest: RunManifest, name: str, runs_dir: Path) -> Path:
    artifact = next(
        (a for a in manifest.outputs if a.path == f"runs/{manifest.run_id}/{name}"), None
    )
    if artifact is None or artifact.sha256 is None:
        raise ValueError(f"{manifest.run_id}: missing checksummed artifact {name}")
    source = (runs_dir / manifest.run_id / name).resolve()
    if not source.is_relative_to((runs_dir / manifest.run_id).resolve()):
        raise ValueError("artifact escapes its run directory")
    if source.stat().st_size > 2 * 1024 * 1024 or sha256_file(source) != artifact.sha256:
        raise ValueError(f"artifact size or checksum mismatch: {name}")
    return source


def explorer_evidence(
    manifests: Sequence[RunManifest], runs_dir: Path, source: RunManifest
) -> tuple[dict[str, Any], RunManifest] | None:
    matches = [
        m
        for m in manifests
        if m.outcome == "evidence_prepared"
        and m.parameters.get("source_run_id") == source.run_id
        and not m.demo
    ]
    if not matches:
        return None
    prepared = max(matches, key=lambda m: (m.finished_at, m.run_id))
    path = verified_output(prepared, "explorer.json", runs_dir)
    data: dict[str, Any] = json.loads(path.read_text())
    table = verified_output(source, "hits.parquet", runs_dir)
    if (
        data.get("schema_version") != 1
        or data.get("source_run_id") != source.run_id
        or data.get("preparation_run_id") != prepared.run_id
        or data.get("source_table_sha256") != sha256_file(table)
    ):
        raise ValueError("explorer provenance does not match its source")
    rows = data["rows"]
    counts = Counter(row["verdict"] for row in rows)
    expected = source.parameters["verdict_counts"]
    if not isinstance(expected, dict) or counts != Counter(expected):
        raise ValueError("explorer classifications disagree with source counts")
    if len(rows) != source.parameters["hit_count"] or len({r["hit_id"] for r in rows}) != len(rows):
        raise ValueError("explorer rows are incomplete or duplicated")
    return data, prepared


def _copy_evidence(manifest: RunManifest, runs_dir: Path, output_root: Path) -> list[Path]:
    copied = []
    for artifact in manifest.outputs:
        if artifact.path.endswith("/manifest.json"):
            continue
        prefix = f"runs/{manifest.run_id}/"
        if not artifact.path.startswith(prefix):
            raise ValueError("dossier artifact must belong to its run")
        source = verified_output(manifest, artifact.path.removeprefix(prefix), runs_dir)
        destination = output_root / artifact.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied.append(destination)
    return copied


def _bundle(manifest: RunManifest, output_root: Path, files: list[Path]) -> Path:
    target = output_root / "downloads" / f"{manifest.run_id}.zip"
    target.parent.mkdir(exist_ok=True)
    readme = (
        f"Theoxenia evidence dossier: {manifest.run_id}\n\n"
        "This bundle contains a recorded analysis and compact outputs, not raw telescope data.\n"
        "No external review, acceptance, or DOI is claimed.\n"
        "Input URLs, local-slice checksums, parameters and command are in manifest.json.\n"
        "SHA-256 output checksums are in that manifest. Input hashes may describe local slices,\n"
        "not complete remote objects; read the run notes.\n"
        "Source data retains its original terms. Project code: Apache-2.0; "
        "authored docs: CC BY 4.0.\n"
        "Repository: https://github.com/mpetyx/theoxenia\n\n"
        "Recorded command (requires the project environment and source-data access):\n"
        f"{manifest.command}\n"
    )
    entries = {p.relative_to(output_root).as_posix(): p.read_bytes() for p in files}
    entries[f"runs/{manifest.run_id}/manifest.json"] = (
        output_root / "runs" / manifest.run_id / "manifest.json"
    ).read_bytes()
    entries["README.txt"] = readme.encode()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    return target


def prepare_research_report(
    manifests: Sequence[RunManifest], runs_dir: Path, output_root: Path, repository_root: Path
) -> tuple[dict[str, Any] | None, list[Path]]:
    """Expose the report only with its pinned, checksum-verified evidence."""
    report = repository_root / "reports" / "first-results"
    config = json.loads((report / "package.json").read_text())
    by_id = {m.run_id: m for m in manifests}
    if not all(run_id in by_id for run_id in config["run_ids"]):
        return None, []
    summary: dict[str, Any] = json.loads((report / "summary.json").read_text())
    source = by_id[summary["source_run_id"]]
    for index, row in enumerate(summary["rows"]):
        record = json.loads(verified_output(source, f"scan-{index}.json", runs_dir).read_text())
        if (
            row["hits"] != len(record["original"]["hits"])
            or row["controls_recovered"] != sum(t["recovered"] for t in record["injected_truth"])
            or row["controls_injected"] != len(record["injected_truth"])
            or row["turboseti_max"] != max(t["max_snr"] for t in record["original"]["trials"])
            or row["independent_max"] != max(t["max_snr"] for t in record["independent"]["trials"])
        ):
            raise ValueError("report summary disagrees with recorded evidence")
    if len(summary["rows"]) != 6:
        raise ValueError("report summary must contain six scans")
    copied = []
    entries = {}
    for run_id in config["run_ids"]:
        manifest = by_id[run_id]
        files = _copy_evidence(manifest, runs_dir, output_root)
        copied.extend(files)
        entries.update({p.relative_to(output_root).as_posix(): p.read_bytes() for p in files})
        entries[f"runs/{run_id}/manifest.json"] = (runs_dir / run_id / "manifest.json").read_bytes()
    for name in (
        "report.pdf",
        "report.md",
        "README.md",
        "SUBMISSION.md",
        "metadata.json",
        "diagnosis-overview.png",
        "diagnosis-overview.svg",
        "summary.json",
        "PROTOCOL.md",
    ):
        target = output_root / "reports" / "first-results" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report / name, target)
        copied.append(target)
    bundle = output_root / "downloads" / "research-report-evidence.zip"
    bundle.parent.mkdir(exist_ok=True)
    entries["README.md"] = (report / "README.md").read_bytes()
    entries["PROTOCOL.md"] = (report / "PROTOCOL.md").read_bytes()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    copied.append(bundle)
    return summary, copied


def render_investigations(
    manifests: Sequence[RunManifest],
    *,
    runs_dir: Path,
    output_root: Path,
    environment: Environment,
    repository_root: Path,
) -> tuple[Path, ...]:
    stories = available_stories(manifests)
    if not stories:
        return ()
    by_id = {m.run_id: m for m in manifests}
    written: list[Path] = []
    prepared_data: dict[str, Any] | None = None
    prepared_manifest: RunManifest | None = None
    for story in stories:
        if story["slug"] == "archive":
            evidence = explorer_evidence(manifests, runs_dir, by_id[story["run_id"]])
            if evidence:
                prepared_data, prepared_manifest = evidence
    for name in ("investigations.js", "explorer.js"):
        dest = output_root / name
        shutil.copyfile(repository_root / "site" / name, dest)
        written.append(dest)

    def write(path: str, template: str, **context: Any) -> None:
        destination = output_root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            environment.get_template(template).render(**context), encoding="utf-8"
        )
        written.append(destination)

    write("investigations.html", "investigations.html.j2", stories=stories, prefix="")
    report, report_files = prepare_research_report(
        manifests, runs_dir, output_root, repository_root
    )
    written.extend(report_files)
    write("research.html", "research.html.j2", prefix="", report=report)
    for story in stories:
        manifest = by_id[story["run_id"]]
        if story["slug"] in {"archive", "recovery"}:
            pinned = build_state([manifest], generated_at=manifest.finished_at)
            image = output_root / story["visual_url"]
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_text(
                render_floor_svg(pinned.detection_floor, demo=False)
                if story["slug"] == "recovery"
                else render_sky_svg(pinned.pointings, demo=False),
                encoding="utf-8",
            )
            written.append(image)
        files = _copy_evidence(manifest, runs_dir, output_root)
        written.extend(files)
        written.append(_bundle(manifest, output_root, files))
        write(
            f"investigations/{story['slug']}.html",
            "investigation.html.j2",
            story=story,
            manifest=manifest,
            payload=manifest.mission_control,
            prefix="../",
            explorer_available=prepared_data is not None,
            report=report,
        )
        write(
            f"dossiers/{manifest.run_id}.html",
            "dossier.html.j2",
            story=story,
            manifest=manifest,
            prefix="../",
            preparation=prepared_manifest if story["slug"] == "archive" else None,
        )
    if prepared_data is not None and prepared_manifest is not None:
        written.extend(_copy_evidence(prepared_manifest, runs_dir, output_root))
        # Standard CSV is a complete non-JavaScript alternative to the explorer.
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(prepared_data["rows"][0]))
        writer.writeheader()
        writer.writerows(prepared_data["rows"])
        csv_path = output_root / "downloads" / "archive-hits.csv"
        csv_path.write_text(stream.getvalue(), encoding="utf-8")
        written.append(csv_path)
        write(
            "explorer.html",
            "explorer.html.j2",
            prefix="",
            data=prepared_data,
            source=by_id[prepared_data["source_run_id"]],
            preparation=prepared_manifest,
            report=report,
        )
    return tuple(written)
