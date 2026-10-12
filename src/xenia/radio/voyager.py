"""Reproducible Voyager 1 known-answer run and manifest-backed waterfall plot."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from xenia.live.models import HeroPayload, InputRef, RunManifest
from xenia.provenance import create_run_manifest, new_run_id, output_ref
from xenia.radio.detector import DetectorResult, DopplerHit, run_turboseti, select_known_answer_hit
from xenia.radio.remote import RangeMetrics, open_counted_http_file
from xenia.radio.sigproc import FilterbankSliceInfo, read_sigproc_header, slice_filterbank

OFFICIAL_SOURCE_URL = "https://storage.googleapis.com/gbt_fil/voyager_f1032192_t300_v2.fil"
OFFICIAL_SOURCE_SIZE_BYTES = 528_482_692
OFFICIAL_SOURCE_NAME = "VOYAGER1"
DEFAULT_FREQUENCY_LOW_MHZ = 8419.0
DEFAULT_FREQUENCY_HIGH_MHZ = 8420.0
DEFAULT_MAX_DRIFT_HZ_S = 4.0
DEFAULT_MINIMUM_SNR = 25.0
REFERENCE_FREQUENCY_MHZ = 8419.319368
REFERENCE_TOLERANCE_MHZ = 0.02
REMOTE_BLOCK_SIZE_BYTES = 1024 * 1024
REMOTE_TRANSFER_LIMIT_BYTES = 16 * 1024 * 1024
MINIMUM_DRIFT_HZ_S = 1e-5


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _render_waterfall_png(
    slice_path: Path,
    output_path: Path,
    slice_info: FilterbankSliceInfo,
    *,
    nbits: int,
    foff_mhz: float,
    tsamp_seconds: float,
    hit: DopplerHit | None,
) -> None:
    """Render an exact-size 16:9 plot from the temporary, already-sliced filterbank."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    if nbits != 32:
        raise ValueError(f"Voyager plot expects 32-bit SIGPROC samples, received {nbits}")
    if slice_info.nifs < 1 or slice_info.integrations < 1 or tsamp_seconds <= 0:
        raise ValueError("plot dimensions and sampling interval must be positive")

    expected_samples = slice_info.integrations * slice_info.nifs * slice_info.channel_count
    with slice_path.open("rb") as stream:
        stream.seek(slice_info.data_offset)
        sample_bytes = stream.read(expected_samples * 4 + 1)
    if len(sample_bytes) != expected_samples * 4:
        raise ValueError("temporary filterbank slice has an unexpected sample count")

    samples = np.frombuffer(sample_bytes, dtype="<f4")
    cube = samples.reshape(slice_info.integrations, slice_info.nifs, slice_info.channel_count)
    waterfall = np.nanmean(cube, axis=1)
    if not np.isfinite(waterfall).any():
        raise ValueError("Voyager slice contains no finite samples to plot")

    first_center = float(slice_info.first_center_mhz)
    last_center = float(slice_info.last_center_mhz)
    if first_center > last_center:
        waterfall = waterfall[:, ::-1]
    channel_width_mhz = abs(foff_mhz)
    frequency_min = min(first_center, last_center) - channel_width_mhz / 2
    frequency_max = max(first_center, last_center) + channel_width_mhz / 2
    elapsed_minutes = slice_info.integrations * tsamp_seconds / 60
    finite_values = waterfall[np.isfinite(waterfall)]
    vmin, vmax = np.percentile(finite_values, [2, 99.5]).astype(float)
    if not vmax > vmin:
        midpoint = float(finite_values[0])
        padding = max(abs(midpoint) * 1e-6, 1e-6)
        vmin, vmax = midpoint - padding, midpoint + padding

    background = "#070B14"
    panel = "#0D1320"
    foreground = "#EAF0FA"
    accent = "#4DE2D2"
    figure = plt.figure(figsize=(12.8, 7.2), dpi=100, facecolor=background)
    try:
        grid = figure.add_gridspec(4, 1, height_ratios=(1.0, 1.0, 1.0, 0.65), hspace=0.22)
        waterfall_axis = figure.add_subplot(grid[:3, 0])
        spectrum_axis = figure.add_subplot(grid[3, 0], sharex=waterfall_axis)
        for axis in (waterfall_axis, spectrum_axis):
            axis.set_facecolor(panel)
            axis.tick_params(colors=foreground, labelsize=9)
            for spine in axis.spines.values():
                spine.set_color("#1A2435")
            axis.grid(color="#1A2435", linewidth=0.5, alpha=0.8)

        image = waterfall_axis.imshow(
            waterfall,
            aspect="auto",
            origin="upper",
            extent=(frequency_min, frequency_max, elapsed_minutes, 0),
            interpolation="nearest",
            cmap="magma",
            vmin=vmin,
            vmax=vmax,
        )
        waterfall_axis.set_title(
            "Voyager 1 · Green Bank Telescope public recording",
            loc="left",
            color=foreground,
            fontsize=14,
            pad=10,
        )
        waterfall_axis.set_ylabel("Elapsed time (minutes)", color=foreground)
        waterfall_axis.tick_params(labelbottom=False)
        colorbar = figure.colorbar(image, ax=waterfall_axis, pad=0.012, fraction=0.025)
        colorbar.ax.tick_params(colors=foreground, labelsize=8)
        colorbar.set_label("Recorded sample value", color=foreground, fontsize=8)

        spectrum = np.nanmean(waterfall, axis=0)
        centers = np.linspace(
            frequency_min + channel_width_mhz / 2,
            frequency_max - channel_width_mhz / 2,
            slice_info.channel_count,
        )
        spectrum_axis.plot(centers, spectrum, color=accent, linewidth=0.65)
        spectrum_axis.set_ylabel("Mean value", color=foreground, fontsize=8)
        spectrum_axis.set_xlabel("Frequency (MHz)", color=foreground)

        if hit is None:
            waterfall_axis.text(
                0.012,
                0.94,
                "No hit passed the predeclared window and thresholds",
                transform=waterfall_axis.transAxes,
                color=foreground,
                fontsize=9,
                va="top",
                bbox={"facecolor": panel, "edgecolor": "#1A2435", "alpha": 0.9},
            )
        else:
            frequency = hit.uncorrected_frequency_mhz
            waterfall_axis.axvline(frequency, color=accent, linewidth=1.1, linestyle="--")
            spectrum_axis.axvline(frequency, color=accent, linewidth=1.0, linestyle="--")
            waterfall_axis.annotate(
                f"Observed carrier {frequency:.6f} MHz · SNR {hit.snr:.2f}",
                xy=(frequency, 0.06),
                xycoords=("data", "axes fraction"),
                xytext=(8, 0),
                textcoords="offset points",
                color=accent,
                fontsize=8,
                va="bottom",
            )

        figure.text(
            0.01,
            0.012,
            "Observed samples · no sidebands are asserted · source and run details in the manifest",
            color="#AAB7C9",
            fontsize=8,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, dpi=100, facecolor=background)
    finally:
        plt.close(figure)


def _serialized_hits(hits: Sequence[DopplerHit], *, limit: int = 100) -> dict[str, object]:
    ordered = sorted(hits, key=lambda hit: (-hit.snr, hit.top_hit))
    return {
        "count": len(ordered),
        "truncated": len(ordered) > limit,
        "hits": [hit.as_dict() for hit in ordered[:limit]],
    }


def _detector_artifacts(result: DetectorResult) -> list[dict[str, object]]:
    return [
        {
            "filename": artifact.filename,
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
        }
        for artifact in result.artifacts
    ]


def _manifest_outputs(paths: Sequence[Path], *, repository_root: Path):
    artifacts = []
    for path in paths:
        if path.is_file():
            artifact = output_ref(path, repository_root=repository_root)
            if path.suffix.lower() == ".png":
                artifact = artifact.model_copy(update={"media_type": "image/png"})
            artifacts.append(artifact)
    return tuple(artifacts)


def run_voyager(
    repository_root: Path,
    command: Sequence[str],
    *,
    source_url: str = OFFICIAL_SOURCE_URL,
    frequency_low_mhz: float = DEFAULT_FREQUENCY_LOW_MHZ,
    frequency_high_mhz: float = DEFAULT_FREQUENCY_HIGH_MHZ,
    max_drift_hz_s: float = DEFAULT_MAX_DRIFT_HZ_S,
    minimum_snr: float = DEFAULT_MINIMUM_SNR,
    experiment_id: str = "EXP-001",
) -> tuple[RunManifest, Path]:
    """Run EXP-001 from bounded source reads through a manifest-backed plot."""
    root = repository_root.resolve()
    started_at = datetime.now(UTC)
    run_id = new_run_id(started_at, "exp-001-voyager")
    run_directory = root / "runs" / run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    manifest_path = run_directory / "manifest.json"
    slice_summary_path = run_directory / "slice_summary.json"
    hits_path = run_directory / "hits.json"
    plot_path = run_directory / "hero.png"
    failure_path = run_directory / "failure.json"

    inputs = (InputRef(uri=source_url),)
    transfer_metrics: RangeMetrics | None = None
    parameters: dict[str, object] = {
        "source_url": source_url,
        "source_expected_size_bytes": OFFICIAL_SOURCE_SIZE_BYTES,
        "requested_window_mhz": [frequency_low_mhz, frequency_high_mhz],
        "max_drift_hz_s": max_drift_hz_s,
        "minimum_drift_hz_s": MINIMUM_DRIFT_HZ_S,
        "minimum_snr": minimum_snr,
        "detector_options": {
            "n_partitions": 1,
            "progress_bar": "n",
            "blank_dc": True,
            "precision": "single",
            "blimpy_two_integration_shim": (
                "Validate shape-(2, 1, nchan) endpoints; bypass only the upstream check's "
                "out-of-range data[2] probe."
            ),
        },
        "remote_block_size_bytes": REMOTE_BLOCK_SIZE_BYTES,
        "remote_transfer_limit_bytes": REMOTE_TRANSFER_LIMIT_BYTES,
    }

    try:
        with open_counted_http_file(
            source_url,
            block_size=REMOTE_BLOCK_SIZE_BYTES,
            max_transfer_bytes=REMOTE_TRANSFER_LIMIT_BYTES,
        ) as (remote_file, transfer_metrics):
            inputs = (InputRef(uri=source_url, size_bytes=transfer_metrics.source_size_bytes),)
            header = read_sigproc_header(remote_file)
            source_name = str(header.fields.get("source_name", "")).strip()
            nbits = int(header.fields.get("nbits", 0))
            nifs = int(header.fields.get("nifs", 0))
            if source_name != OFFICIAL_SOURCE_NAME:
                raise ValueError(
                    f"expected source_name={OFFICIAL_SOURCE_NAME}, found {source_name!r}"
                )
            if nbits != 32 or nifs != 1:
                raise ValueError(
                    f"expected a 32-bit, single-IF Voyager file; found nbits={nbits}, nifs={nifs}"
                )
            try:
                tsamp_seconds = float(header.fields["tsamp"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Voyager header is missing a valid tsamp") from exc
            foff_mhz = float(header.fields["foff"])

            parameters["source_header"] = {
                "source_name": source_name,
                "nchans": int(header.fields["nchans"]),
                "nifs": nifs,
                "nbits": nbits,
                "fch1_mhz": float(header.fields["fch1"]),
                "foff_mhz": foff_mhz,
                "tsamp_seconds": tsamp_seconds,
                "tstart_mjd": float(header.fields["tstart"]),
            }
            inputs = (InputRef(uri=source_url, size_bytes=transfer_metrics.source_size_bytes),)

            with tempfile.TemporaryDirectory(prefix="xenia-exp001-") as temporary_directory:
                temporary_root = Path(temporary_directory)
                slice_path = temporary_root / "voyager-window.fil"
                slice_info = slice_filterbank(
                    remote_file,
                    output_path=slice_path,
                    frequency_low_mhz=frequency_low_mhz,
                    frequency_high_mhz=frequency_high_mhz,
                )
                slice_sha256 = _sha256_file(slice_path)
                slice_summary = {
                    "source_url": source_url,
                    "source_name": source_name,
                    "requested_window_mhz": [frequency_low_mhz, frequency_high_mhz],
                    "channel_start": slice_info.channel_start,
                    "channel_count": slice_info.channel_count,
                    "first_center_mhz": float(slice_info.first_center_mhz),
                    "last_center_mhz": float(slice_info.last_center_mhz),
                    "integrations": slice_info.integrations,
                    "nifs": slice_info.nifs,
                    "data_offset_bytes": slice_info.data_offset,
                    "slice_size_bytes": slice_info.output_size_bytes,
                    "slice_sha256": slice_sha256,
                    "remote_transfer": transfer_metrics.as_dict(),
                }
                _write_json(slice_summary_path, slice_summary)
                parameters.update(
                    {
                        "source_size_bytes": transfer_metrics.source_size_bytes,
                        "remote_transfer": transfer_metrics.as_dict(),
                        "slice": slice_summary,
                    }
                )
                detector_result = run_turboseti(
                    slice_path,
                    output_directory=temporary_root / "detector",
                    max_drift_hz_s=max_drift_hz_s,
                    minimum_snr=minimum_snr,
                )
                match_low_mhz = max(
                    frequency_low_mhz, REFERENCE_FREQUENCY_MHZ - REFERENCE_TOLERANCE_MHZ
                )
                match_high_mhz = min(
                    frequency_high_mhz, REFERENCE_FREQUENCY_MHZ + REFERENCE_TOLERANCE_MHZ
                )
                hit = (
                    None
                    if match_low_mhz > match_high_mhz
                    else select_known_answer_hit(
                        detector_result.hits,
                        frequency_low_mhz=match_low_mhz,
                        frequency_high_mhz=match_high_mhz,
                        max_abs_drift_hz_s=max_drift_hz_s,
                        minimum_snr=minimum_snr,
                    )
                )
                _render_waterfall_png(
                    slice_path,
                    plot_path,
                    slice_info,
                    nbits=nbits,
                    foff_mhz=foff_mhz,
                    tsamp_seconds=tsamp_seconds,
                    hit=hit,
                )

                detector_summary = {
                    "turbo_seti_version": detector_result.turbo_seti_version,
                    "blimpy_version": detector_result.blimpy_version,
                    "max_drift_hz_s": max_drift_hz_s,
                    "minimum_drift_hz_s": MINIMUM_DRIFT_HZ_S,
                    "minimum_snr": minimum_snr,
                    "known_answer_reference_frequency_mhz": REFERENCE_FREQUENCY_MHZ,
                    "known_answer_tolerance_mhz": REFERENCE_TOLERANCE_MHZ,
                    "known_answer_match_window_mhz": [match_low_mhz, match_high_mhz],
                    "dat_outputs": _detector_artifacts(detector_result),
                    "selected_hit_top_hit": None if hit is None else hit.top_hit,
                }

        _write_json(slice_summary_path, slice_summary)
        _write_json(
            hits_path,
            {
                **_serialized_hits(detector_result.hits),
                "selected_known_answer_hit": None if hit is None else hit.as_dict(),
            },
        )
        parameters.update(
            {
                "source_size_bytes": transfer_metrics.source_size_bytes,
                "remote_transfer": transfer_metrics.as_dict(),
                "slice": slice_summary,
                "detector": detector_summary,
                "hit_count": len(detector_result.hits),
            }
        )
        outputs = _manifest_outputs(
            (slice_summary_path, hits_path, plot_path), repository_root=root
        )
        hero_payload = None
        if hit is not None:
            hero_payload = HeroPayload(
                kind="hero",
                experiment="EXP-001",
                run_id=run_id,
                image_url=plot_path.relative_to(root).as_posix(),
                freq_mhz=hit.uncorrected_frequency_mhz,
                drift_hz_s=hit.drift_hz_s,
                snr=hit.snr,
            )
        finished_at = datetime.now(UTC)
        outcome = "known_answer_detected" if hit is not None else "no_expected_hit"
        if hit is not None:
            notes = (
                "A turboSETI hit passed the predeclared source, frequency, drift, and SNR checks.",
            )
        else:
            notes = (
                "Null known-answer result: no hit passed the predeclared thresholds. "
                "This is not a scientific non-detection conclusion.",
            )
        manifest, written_path = create_run_manifest(
            run_id=run_id,
            command=command,
            parameters=parameters,
            inputs=inputs,
            outputs=outputs,
            started_at=started_at,
            finished_at=finished_at,
            outcome=outcome,
            notes=notes,
            repository_root=root,
            demo=False,
            pillar="I · Sensor",
            experiment_id=experiment_id,
            mission_control=hero_payload,
            manifest_path=manifest_path,
        )
        return manifest, written_path
    except Exception as exc:
        if transfer_metrics is not None:
            parameters["remote_transfer"] = transfer_metrics.as_dict()
        _write_json(
            failure_path,
            {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "remote_transfer": None if transfer_metrics is None else transfer_metrics.as_dict(),
            },
        )
        finished_at = datetime.now(UTC)
        failure_outputs = _manifest_outputs(
            (slice_summary_path, hits_path, plot_path, failure_path), repository_root=root
        )
        create_run_manifest(
            run_id=run_id,
            command=command,
            parameters=parameters,
            inputs=inputs,
            outputs=failure_outputs,
            started_at=started_at,
            finished_at=finished_at,
            outcome="failed",
            notes=(f"Operational failure: {type(exc).__name__}: {exc}",),
            repository_root=root,
            demo=False,
            pillar="I · Sensor",
            experiment_id=experiment_id,
            mission_control=None,
            manifest_path=manifest_path,
        )
        raise


def _sha256_file(path: Path) -> str:
    """Hash the small temporary slice without retaining its bytes in memory."""
    from hashlib import sha256

    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
