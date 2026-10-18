"""Cadence and hit pages, the sitemap, and the experiments index."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

from xenia.live.models import CadenceHit, CadencePayload, RunManifest

CHECK_NAMES: tuple[str, ...] = (
    "not_in_off",
    "not_known_transmitter",
    "drift_sane",
    "session_census_clear",
    "review",
)
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def cadence_asset_urls(manifests: Sequence[RunManifest]) -> set[str]:
    """Relative plot and thumbnail URLs referenced by cadence payloads."""
    urls: set[str] = set()
    for _manifest, payload in _latest_cadences(manifests):
        for hit in payload.hits:
            urls.add(hit.thumbnail_url)
            if hit.plot_url is not None:
                urls.add(hit.plot_url)
    return urls


def render_detail_pages(
    manifests: Sequence[RunManifest],
    *,
    output_root: Path,
    template_dir: Path,
    base_url: str | None = None,
    additional_paths: Sequence[str] = (),
    explorer_run_ids: set[str] | None = None,
) -> tuple[Path, ...]:
    """Write cadence pages, hit pages, and sitemap.xml under the site root."""
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(("html", "xml", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    cadence_template = environment.get_template("cadence.html.j2")
    hit_template = environment.get_template("hit.html.j2")
    written: list[Path] = []
    sitemap_paths = ["index.html", "evidence.html", "feed.json", *additional_paths]
    seen_hits: dict[str, str] = {}

    for manifest, payload in _latest_cadences(manifests):
        cadence_id = _segment(payload.cadence_id, "cadence_id")
        page_dir = output_root / "cadences" / cadence_id
        page_dir.mkdir(parents=True, exist_ok=True)
        hits = []
        for hit in payload.hits:
            hit_id = _segment(hit.hit_id, "hit_id")
            owner = seen_hits.get(hit_id)
            if owner is not None and owner != cadence_id:
                raise ValueError(f"hit_id {hit_id} is used by {owner} and {cadence_id}")
            seen_hits[hit_id] = cadence_id
            hits.append(_hit_context(hit, cadence_id=cadence_id, depth=2))
        cadence_path = page_dir / "index.html"
        cadence_path.write_text(
            cadence_template.render(
                cadence_id=cadence_id,
                target=payload.target,
                ra_text=_number(payload.ra_deg),
                dec_text=_number(payload.dec_deg),
                window_low=_number(payload.window_mhz[0]),
                window_high=_number(payload.window_mhz[1]),
                status=payload.status.value,
                on_source_text=_number(payload.on_source_seconds),
                command=manifest.command,
                manifest_href=_relative(f"runs/{manifest.run_id}/manifest.json", depth=2),
                plots=_plot_contexts(payload.hits, depth=2),
                hits=hits,
                check_names=CHECK_NAMES,
                stylesheet_href="../../styles.css",
                back_href="../../index.html",
                explorer_href="../../explorer.html"
                if manifest.run_id in (explorer_run_ids or set())
                else None,
            ),
            encoding="utf-8",
        )
        written.append(cadence_path)
        sitemap_paths.append(f"cadences/{cadence_id}/index.html")

        for hit in payload.hits:
            hit_id = _segment(hit.hit_id, "hit_id")
            hit_path = output_root / "hits" / f"{hit_id}.html"
            hit_path.parent.mkdir(parents=True, exist_ok=True)
            hit_path.write_text(
                hit_template.render(
                    hit=_hit_context(hit, cadence_id=cadence_id, depth=1),
                    cadence_id=cadence_id,
                    target=payload.target,
                    command=manifest.command,
                    manifest_href=_relative(f"runs/{manifest.run_id}/manifest.json", depth=1),
                    cadence_href=_relative(f"cadences/{cadence_id}/index.html", depth=1),
                    check_names=CHECK_NAMES,
                    stylesheet_href="../styles.css",
                    back_href="../index.html",
                    explorer_href=f"../explorer.html#hit={hit_id}"
                    if manifest.run_id in (explorer_run_ids or set())
                    else None,
                ),
                encoding="utf-8",
            )
            written.append(hit_path)
            sitemap_paths.append(f"hits/{hit_id}.html")

    sitemap_path = output_root / "sitemap.xml"
    sitemap_path.write_text(_sitemap(sitemap_paths, base_url=base_url), encoding="utf-8")
    written.append(sitemap_path)
    return tuple(written)


def render_experiments_index(manifests: Sequence[RunManifest]) -> str:
    """Markdown index of every manifest. The text is deterministic."""
    ordered = sorted(manifests, key=lambda item: (item.started_at, item.run_id))
    lines = [
        "# Experiments",
        "",
        "Generated by `xenia docs experiments` from every `manifest.json` under `runs/`.",
        "Do not edit this file by hand. `make docs` fails when it is stale.",
        "",
        f"Manifests indexed: {len(ordered)}.",
        "",
    ]
    if not ordered:
        lines.append("No manifests were found.")
        lines.append("")
    for manifest in ordered:
        experiment = manifest.experiment_id or "none"
        lines.extend(
            [
                f"## `{manifest.run_id}`",
                "",
                f"- Experiment: `{experiment}`",
                f"- Pillar: `{manifest.pillar}`",
                f"- Started: `{_stamp(manifest.started_at)}`",
                f"- Finished: `{_stamp(manifest.finished_at)}`",
                f"- Outcome: `{manifest.outcome}`",
                f"- Demo: `{str(manifest.demo).lower()}`",
                f"- Manifest: `runs/{manifest.run_id}/manifest.json`",
                "- Command:",
                "",
                _indent(manifest.command),
                "",
            ]
        )
    return "\n".join(lines)


def _latest_cadences(
    manifests: Sequence[RunManifest],
) -> tuple[tuple[RunManifest, CadencePayload], ...]:
    grouped: dict[str, tuple[RunManifest, CadencePayload]] = {}
    for manifest in manifests:
        payload = manifest.mission_control
        if not isinstance(payload, CadencePayload):
            continue
        current = grouped.get(payload.cadence_id)
        if current is None or manifest.finished_at >= current[0].finished_at:
            grouped[payload.cadence_id] = (manifest, payload)
    return tuple(grouped[key] for key in sorted(grouped))


def _hit_context(hit: CadenceHit, *, cadence_id: str, depth: int) -> dict[str, object]:
    hit_id = _segment(hit.hit_id, "hit_id")
    return {
        "hit_id": hit_id,
        "cadence_id": cadence_id,
        "freq_text": _number(hit.freq_mhz),
        "drift_text": _number(hit.drift_hz_s),
        "snr_text": _number(hit.snr),
        "verdict": hit.verdict.value,
        "explanation": hit.explanation,
        "checks_done": hit.checks_done,
        "known_source": hit.known_source,
        "thumbnail_href": _relative(hit.thumbnail_url, depth=depth),
        "plot_href": None if hit.plot_url is None else _relative(hit.plot_url, depth=depth),
        "page_href": _relative(f"hits/{hit_id}.html", depth=depth),
    }


def _plot_contexts(hits: tuple[CadenceHit, ...], *, depth: int) -> list[dict[str, str]]:
    plots: list[dict[str, str]] = []
    seen: set[str] = set()
    for hit in hits:
        if hit.plot_url is None or hit.plot_url in seen:
            continue
        seen.add(hit.plot_url)
        plots.append(
            {
                "href": _relative(hit.plot_url, depth=depth),
                "alt": f"Six-panel plot for {hit.hit_id}",
            }
        )
    return plots


def _relative(url: str, *, depth: int) -> str:
    prefix = "../" * depth
    return f"{prefix}{url.lstrip('/')}"


def _segment(value: str, kind: str) -> str:
    if _SEGMENT.fullmatch(value) is None:
        raise ValueError(f"{kind} is not a safe path segment: {value}")
    return value


def _number(value: float) -> str:
    """Render a stored float without adding a false trailing precision claim."""
    return format(value, ".10g")


def _stamp(value: datetime) -> str:
    text = value.astimezone(UTC).isoformat()
    return text.replace("+00:00", "Z")


def _indent(command: str) -> str:
    safe = command.replace("```", "'''")
    return "\n".join(f"    {line}" if line else "    " for line in safe.splitlines()) or "    "


def _sitemap(paths: Sequence[str], *, base_url: str | None = None) -> str:
    if base_url is not None:
        paths = [f"{base_url.rstrip('/')}/{path}" for path in paths]
    body = "\n".join(f"  <url><loc>{xml_escape(path)}</loc></url>" for path in paths)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


def sky_href(cadence_id: str) -> str:
    """Site-relative cadence page used by sky-map dots."""
    return f"cadences/{_segment(cadence_id, 'cadence_id')}/index.html"
