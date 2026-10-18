"""Render a validated LiveState as a self-contained, static Mission Control site."""

from __future__ import annotations

import html
import json
import re
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from jinja2 import Environment, FileSystemLoader, select_autoescape

from xenia.live.evidence import is_synthetic, selected_cadences, verdict_counts
from xenia.live.investigations import available_stories, render_investigations
from xenia.live.models import (
    CadenceStatus,
    LiveState,
    RunManifest,
    Verdict,
    WorkerStatus,
)
from xenia.live.pages import cadence_asset_urls, render_detail_pages
from xenia.live.plots import render_floor_svg, render_sky_svg
from xenia.live.state import ManifestLoadError, load_manifests, manifest_paths

MAX_RENDERED_ASSET_BYTES = 2 * 1024 * 1024
PAGE_COUNTER_LINKS = {
    "cadences": "Cadences searched",
    "sky-hours": "Sky searched",
    "hits": "Hits found",
    "survivors": "Survivors waiting for checks",
    "unexplained": "Unexplained",
}


def render_site(
    *,
    state_path: Path,
    runs_dir: Path,
    output_dir: Path,
    repository_root: Path | None = None,
    now: datetime | None = None,
) -> tuple[Path, ...]:
    """Validate state and build the static page, SVG plots, and manifest index."""
    root = (repository_root or Path.cwd()).resolve()
    template_path = root / "site" / "templates" / "index.html.j2"
    stylesheet_path = root / "site" / "styles.css"
    if not template_path.is_file():
        raise FileNotFoundError(f"page template not found: {template_path}")
    if not stylesheet_path.is_file():
        raise FileNotFoundError(f"page stylesheet not found: {stylesheet_path}")

    try:
        state = LiveState.model_validate_json(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid state file {state_path}: {exc}") from exc
    manifests = load_manifests(runs_dir)
    output_root = output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    rendered: list[Path] = []
    generated_state = output_root / "state.json"
    generated_state.write_text(
        json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    rendered.append(generated_state)

    stylesheet_output = output_root / "styles.css"
    if stylesheet_path.resolve() != stylesheet_output.resolve():
        shutil.copyfile(stylesheet_path, stylesheet_output)
    rendered.append(stylesheet_output)

    sky_output = output_root / "sky.svg"
    sky_output.write_text(
        render_sky_svg(state.pointings, demo=state.meta.demo),
        encoding="utf-8",
    )
    rendered.append(sky_output)

    floor_output = output_root / "floor.svg"
    floor_output.write_text(
        render_floor_svg(state.detection_floor, demo=state.meta.demo),
        encoding="utf-8",
    )
    rendered.append(floor_output)

    copied_manifests = _copy_manifests(manifests, runs_dir=runs_dir, output_root=output_root)
    rendered.extend(copied_manifests)
    copied_assets = _copy_state_assets(
        state,
        runs_dir=runs_dir,
        output_root=output_root,
        extra_urls=cadence_asset_urls(manifests),
    )
    rendered.extend(copied_assets)

    status = worker_status(state, now=now)
    ticker = ticker_text(state)
    preview_hits = state.gallery[:8]
    template_env = Environment(
        loader=FileSystemLoader(template_path.parent),
        autoescape=select_autoescape(("html", "xml", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = template_env.get_template(template_path.name)
    investigation_outputs = render_investigations(
        manifests,
        runs_dir=runs_dir,
        output_root=output_root,
        environment=template_env,
        repository_root=root,
    )
    rendered.extend(investigation_outputs)
    html_text = template.render(
        stories=available_stories(manifests),
        prefix="",
        state=state,
        status=status,
        ticker=ticker,
        metrics=_metrics_context(state),
        gallery=preview_hits,
        map_accessible_pointings=state.pointings,
        sky_markup=sky_output.read_text(encoding="utf-8"),
        floor_svg_url="floor.svg",
        floor_markup=floor_output.read_text(encoding="utf-8"),
        verdict_rows=_verdict_rows(state),
        synthetic_only=bool(selected_cadences(manifests))
        and all(is_synthetic(m) and not m.demo for m, _ in selected_cadences(manifests)),
        generated_at_text=state.generated_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        repo_url=state.meta.repo_url,
        mirror_url=state.meta.mirror_url,
        floor_manifest_url=(
            state.detection_floor.manifest_url if state.detection_floor is not None else None
        ),
        floor_ci_url=(
            state.detection_floor.ci_run_url if state.detection_floor is not None else None
        ),
        hero_manifest_url=state.hero.manifest_url if state.hero is not None else None,
        og_image=_og_image(state),
        later_bluebook=_later_card(manifests, "EXP-010"),
        later_nearearth=_later_card(manifests, "EXP-020"),
    )
    index_output = output_root / "index.html"
    index_output.write_text(html_text, encoding="utf-8")
    rendered.append(index_output)
    notebook_output = output_root / "evidence.html"
    notebook_output.write_text(
        template_env.get_template("evidence.html.j2").render(notebook=_notebook(manifests)),
        encoding="utf-8",
    )
    rendered.append(notebook_output)
    feed_output = output_root / "feed.json"
    feed_output.write_text(_feed_document(state), encoding="utf-8")
    rendered.append(feed_output)

    rendered.extend(
        render_detail_pages(
            manifests,
            output_root=output_root,
            template_dir=template_path.parent,
            base_url=state.meta.mirror_url,
            explorer_run_ids={
                s["run_id"] for s in available_stories(manifests) if s["slug"] == "archive"
            }
            if (output_root / "explorer.html").is_file()
            else set(),
            additional_paths=[
                p.relative_to(output_root).as_posix()
                for p in investigation_outputs
                if p.suffix == ".html"
            ],
        )
    )

    manifest_index = output_root / "runs" / "index.html"
    manifest_index.parent.mkdir(parents=True, exist_ok=True)
    manifest_index.write_text(_render_manifest_index(manifests), encoding="utf-8")
    rendered.append(manifest_index)

    _assert_referenced_manifests_exist(state, output_root)
    _assert_page_has_no_external_assets(index_output)
    return tuple(rendered)


def _later_card(manifests: Sequence[RunManifest], experiment_id: str) -> dict[str, str] | None:
    """Live later-panel copy when a non-demo manifest for that experiment exists."""
    matches = [item for item in manifests if item.experiment_id == experiment_id and not item.demo]
    if not matches:
        return None
    latest = max(matches, key=lambda item: item.finished_at)
    parts = [f"Run {latest.run_id} outcome {latest.outcome}."]
    pages = latest.parameters.get("pages_processed")
    if isinstance(pages, int) and not isinstance(pages, bool):
        parts.append(f"Pages processed: {pages}.")
    fireballs = latest.parameters.get("fireball_count")
    if isinstance(fireballs, int) and not isinstance(fireballs, bool):
        parts.append(f"Fireballs recorded: {fireballs}.")
    kp_max = latest.parameters.get("kp_max")
    if isinstance(kp_max, int | float) and not isinstance(kp_max, bool):
        parts.append(f"Kp max recorded: {kp_max}.")
    return {
        "summary": " ".join(parts),
        "manifest_url": f"runs/{latest.run_id}/manifest.json",
    }


def _public_base(state: LiveState) -> str:
    return (state.meta.mirror_url or state.meta.repo_url).rstrip("/")


def _og_image(state: LiveState) -> str | None:
    """Absolute URL of the newest waterfall PNG, when one is on the page."""
    relative: str | None = None
    for item in state.gallery:
        if item.plot_url and item.plot_url.endswith(".png"):
            relative = item.plot_url
            break
        if item.thumbnail_url.endswith(".png"):
            relative = item.thumbnail_url
            break
    if relative is None and state.hero is not None and state.hero.image_url.endswith(".png"):
        relative = state.hero.image_url
    if relative is None:
        return None
    return f"{_public_base(state)}/{relative.lstrip('/')}"


def _feed_document(state: LiveState) -> str:
    """JSON Feed 1.1 of survivor cards only."""
    base = _public_base(state)
    items = [
        {
            "id": item.hit_id,
            "url": f"{base}/{item.manifest_url.lstrip('/')}",
            "title": f"{item.target}: {item.badge_text}",
            "content_text": item.explanation,
            "date_published": item.found_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for item in state.gallery
        if item.verdict is Verdict.ON_ONLY
    ]
    document = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Theoxenia Mission control",
        "home_page_url": base,
        "feed_url": f"{base}/feed.json",
        "items": items,
    }
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def worker_status(state: LiveState, *, now: datetime | None = None) -> dict[str, str | bool]:
    """Return an honest status label and pulse flag for the page header."""
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    if state.meta.is_mirror:
        updated = (
            _format_utc(state.meta.mirror_updated_at) if state.meta.mirror_updated_at else "unknown"
        )
        return {"label": f"Mirror, updated {updated}", "tone": "muted", "is_live": False}

    worker = state.worker
    if worker.status is WorkerStatus.ERROR:
        label = "Worker error"
        tone = "warning"
        is_live = False
    elif worker.status is WorkerStatus.PAUSED:
        label = "Worker paused"
        tone = "muted"
        is_live = False
    elif worker.last_heartbeat is None:
        label = "Heartbeat unavailable"
        tone = "warning"
        is_live = False
    else:
        age_seconds = (current_time - worker.last_heartbeat).total_seconds()
        if age_seconds < 0:
            label = "Worker clock is ahead"
            tone = "warning"
            is_live = False
        elif age_seconds <= 600 and not state.meta.demo:
            label = f"Live, heartbeat {max(0, int(age_seconds))} s ago"
            tone = "live"
            is_live = True
        elif age_seconds <= 21_600:
            label = f"Worker quiet since {_format_utc(worker.last_heartbeat)}"
            tone = "warning"
            is_live = False
        else:
            label = f"Worker stopped, last run at {_format_utc(worker.last_heartbeat)}"
            tone = "warning"
            is_live = False

    if state.meta.demo:
        label = f"{label}, demo state"
        is_live = False
    return {"label": label, "tone": tone, "is_live": is_live}


def ticker_text(state: LiveState) -> str:
    """Render the current or next cadence as a plain-language sentence."""
    current = state.worker.current
    if current is not None:
        start_mhz, stop_mhz = current.window_mhz
        return (
            f"Now searching {current.target}, {current.receiver}, "
            f"{start_mhz:g} to {stop_mhz:g} MHz, scan {current.scan_index} "
            f"of {current.scan_count}."
        )
    next_item = state.worker.next
    if next_item is None:
        return "Idle, no cadence queued."
    if next_item.eta is None:
        return f"Idle, next cadence {next_item.target}."
    return f"Idle, next cadence {next_item.target} at {_format_utc(next_item.eta)}."


def _metrics_context(state: LiveState) -> tuple[dict[str, str], ...]:
    """Prepare tabular metric labels and relative manifest-list links."""
    totals = state.totals
    values = (
        ("cadences", totals.cadences_searched, "Cadences searched", ""),
        ("sky-hours", f"{totals.mhz_hours_on_target:,.1f}", "Sky searched", "MHz·hours"),
        ("hits", totals.hits, "Hits found", ""),
        ("survivors", totals.survivors, "Survivors waiting for checks", ""),
        ("unexplained", totals.unexplained, "Unexplained", ""),
    )
    return tuple(
        {
            "key": key,
            "value": value if isinstance(value, str) else f"{value:,}",
            "label": label,
            "unit": unit,
            "href": f"runs/index.html#{key}",
        }
        for key, value, label, unit in values
    )


def _copy_manifests(
    manifests: Sequence[RunManifest], *, runs_dir: Path, output_root: Path
) -> list[Path]:
    """Copy only validated JSON manifests into the static site's runs tree."""
    copied: list[Path] = []
    for source in manifest_paths(runs_dir):
        manifest = next(item for item in manifests if item.run_id == _run_id_from_path(source))
        size = source.stat().st_size
        if size > MAX_RENDERED_ASSET_BYTES:
            raise ValueError(f"manifest {source} exceeds the 2 MiB static-artifact limit")
        target = output_root / "runs" / manifest.run_id / "manifest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append(target)
    return copied


def _run_id_from_path(path: Path) -> str:
    """Read and validate the run ID from an already validated manifest path."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        return str(document["run_id"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ManifestLoadError(f"cannot read run_id from manifest {path}: {exc}") from exc


def _copy_state_assets(
    state: LiveState,
    *,
    runs_dir: Path,
    output_root: Path,
    extra_urls: set[str] | None = None,
) -> list[Path]:
    """Copy only assets referenced by visible state items and enforce size limits."""
    urls: set[str] = set() if extra_urls is None else set(extra_urls)
    for item in state.gallery:
        urls.add(item.thumbnail_url)
        if item.plot_url is not None:
            urls.add(item.plot_url)
    if state.hero is not None:
        urls.add(state.hero.image_url)

    copied: list[Path] = []
    for url in sorted(urls):
        parts = PurePosixPath(url).parts
        if len(parts) < 3 or parts[0] != "runs":
            raise ValueError(f"asset URL must be under runs/<RUN_ID>/: {url}")
        source = runs_dir.joinpath(*parts[1:]).resolve()
        try:
            source.relative_to(runs_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"asset path escapes run directory: {url}") from exc
        if not source.is_file():
            raise FileNotFoundError(f"state references missing asset {url} (looked for {source})")
        if source.stat().st_size > MAX_RENDERED_ASSET_BYTES:
            raise ValueError(f"asset {url} exceeds the 2 MiB static-artifact limit")
        destination = output_root.joinpath(*parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied.append(destination)
    return copied


def _assert_referenced_manifests_exist(state: LiveState, output_root: Path) -> None:
    """Refuse to render if a displayed item has a missing provenance target."""
    urls = {pointing.manifest_url for pointing in state.pointings}
    urls.update(item.manifest_url for item in state.gallery)
    if state.hero is not None:
        urls.add(state.hero.manifest_url)
    if state.detection_floor is not None:
        urls.add(state.detection_floor.manifest_url)
    for url in urls:
        parts = PurePosixPath(url).parts
        if len(parts) < 3 or parts[0] != "runs":
            raise ValueError(f"manifest URL must be under runs/<RUN_ID>/: {url}")
        path = output_root.joinpath(*parts)
        if not path.is_file():
            raise FileNotFoundError(f"state references missing manifest {url}")


def _render_manifest_index(manifests: Sequence[RunManifest]) -> str:
    """Render static category anchors that counter links can open without JS."""
    categories: dict[str, list[tuple[str, str]]] = {key: [] for key in PAGE_COUNTER_LINKS}
    for manifest, payload in selected_cadences(manifests):
        counts = verdict_counts(manifest, payload)
        link = f"{manifest.run_id}/manifest.json"
        if payload.status is CadenceStatus.DONE:
            categories["cadences"].append((link, f"{payload.target}, completed cadence"))
            categories["sky-hours"].append((link, f"{payload.target}, searched window"))
        if sum(counts.values()):
            categories["hits"].append((link, f"{payload.target}, recorded hits"))
        if counts[Verdict.ON_ONLY]:
            categories["survivors"].append((link, f"{payload.target}, survivor checks"))
        if counts[Verdict.UNEXPLAINED]:
            categories["unexplained"].append((link, f"{payload.target}, reviewed verdict"))

    sections: list[str] = []
    for anchor, heading in PAGE_COUNTER_LINKS.items():
        links = categories[anchor]
        if links:
            entries = "".join(
                f'<li><a href="{html.escape(url, quote=True)}">{html.escape(label)}</a></li>'
                for url, label in links
            )
        else:
            entries = '<li class="empty">No matching manifests yet.</li>'
        sections.append(
            f'<section id="{anchor}"><h2>{html.escape(heading)}</h2><ul>{entries}</ul></section>'
        )
    return (
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>Run manifests · Theoxenia</title>
  <link rel="stylesheet" href="../styles.css">
</head>
<body>
  <main class="manifest-index">
    <p><a href="../index.html">Back to Mission control</a></p>
    <h1>Run manifests</h1>
    <p>Each entry links to the exact run record that produced the displayed data.</p>
    """
        + "\n".join(sections)
        + "\n  </main>\n</body>\n</html>\n"
    )


def _assert_page_has_no_external_assets(page_path: Path) -> None:
    """Guard the M0 fast, no-external-request requirement."""
    text = page_path.read_text(encoding="utf-8").lower()
    if "<script" in text:
        raise ValueError("M0 page must not include JavaScript")
    attribute_pattern = re.compile(
        r"<(?:img|script|link|source)\b[^>]*\b(?:src|href)\s*=\s*(['\"])(.*?)\1",
        flags=re.DOTALL,
    )
    for match in attribute_pattern.finditer(text):
        value = match.group(2).strip()
        if value.startswith(("http://", "https://", "//")):
            raise ValueError(f"M0 page must not load a remote asset: {value}")

    stylesheet = page_path.with_name("styles.css")
    if stylesheet.is_file():
        css = stylesheet.read_text(encoding="utf-8").lower()
        if "@import" in css or re.search(r"url\(\s*['\"]?(?:https?:)?//", css):
            raise ValueError("M0 stylesheet must not import remote assets")


def _format_utc(timestamp: datetime | None) -> str:
    """Format an aware timestamp for concise, explicit UTC display."""
    if timestamp is None:
        return "not available"
    return timestamp.astimezone(UTC).strftime("%H:%M UTC")


def _verdict_rows(state: LiveState) -> list[dict[str, str | int | float]]:
    totals = state.totals
    values = [
        ("known_source", "Known transmitter", totals.known_source),
        ("in_off", "Also in the OFF scans", totals.in_off),
        ("single_pointing", "Missing from one or more ON scans", totals.single_pointing),
        ("rfi_census", "Shared with another target", totals.rfi_census),
        ("on_only", "Waiting for further checks", totals.survivors),
        ("unexplained", "Unexplained after review", totals.unexplained),
    ]
    return [
        {
            "key": key,
            "label": label,
            "count": count,
            "percent": round(100 * count / totals.hits, 2) if totals.hits else 0,
        }
        for key, label, count in values
    ]


def _notebook(manifests: Sequence[RunManifest]) -> list[dict[str, str]]:
    titles = {
        "EXP-001": "Recovering the Voyager carrier",
        "EXP-002": "Measuring injection recovery",
        "EXP-003": "Searching one archived cadence",
        "EXP-004": "Testing the ON/OFF sequence",
        "EXP-010": "Reading Project Blue Book records",
        "EXP-020": "Checking public environmental records",
    }
    return [
        {
            "experiment": m.experiment_id or "",
            "title": titles[m.experiment_id or ""],
            "kind": "Synthetic control"
            if is_synthetic(m) or m.experiment_id == "EXP-002"
            else "Recorded source work",
            "date": m.finished_at.strftime("%Y-%m-%d"),
            "outcome": m.outcome,
            "run_id": m.run_id,
            "command": m.command,
        }
        for m in sorted(manifests, key=lambda m: (m.finished_at, m.run_id), reverse=True)
        if m.experiment_id in titles
    ]
