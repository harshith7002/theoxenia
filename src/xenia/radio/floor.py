"""Seeded setigen injection/recovery floor for Mission Control EXP-002."""

from __future__ import annotations

import importlib
import json
import os
import platform
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from xenia.live.models import (
    FloorDetectedHit,
    FloorDetectorArtifact,
    FloorPayload,
    FloorSearchTrial,
    RecoveryGridArtifact,
    RecoveryMeasurement,
    RunManifest,
)
from xenia.provenance import create_run_manifest, new_run_id, output_ref
from xenia.radio.detector import DetectorResult, DopplerHit, run_turboseti
from xenia.radio.floor_config import (
    DETECTOR_SNR_THRESHOLD,
    DRIFT_TOLERANCE_HZ_S,
    F_SUBSAMPLES,
    FRAME_CENTER_FREQUENCY_MHZ,
    FRAME_FCH1_MHZ,
    FRAME_MJD,
    FREQUENCY_CHANNELS,
    FREQUENCY_MARGIN_CHANNELS,
    FREQUENCY_RESOLUTION_HZ,
    FREQUENCY_SLOT_STRIDE_CHANNELS,
    FREQUENCY_TOLERANCE_HZ,
    FULL_DRIFT_GRID,
    FULL_SNR_GRID,
    FULL_TRIALS_PER_CELL,
    MAX_ABS_DRIFT_HZ_S,
    NOISE_MEAN,
    REDUCED_DRIFT_GRID,
    REDUCED_SNR_GRID,
    REDUCED_TRIALS_PER_CELL,
    SIGNAL_BOUND_MARGIN_HZ,
    SIGNAL_WIDTH_HZ,
    SMEARING_SUBSAMPLES,
    TIME_CHANNELS,
    TIME_RESOLUTION_SECONDS,
    GridMode,
)


@dataclass(frozen=True, slots=True)
class _InjectionPlan:
    """One line injected into a shared seeded frame."""

    snr: float
    drift_hz_s: float
    trial_index: int
    seed: int
    channel_index: int
    frequency_mhz: float
    start_frequency_mhz: float


def grid_values(mode: GridMode) -> tuple[tuple[float, ...], tuple[float, ...], int]:
    """Return the exact project-defined full or pull-request smoke grid."""
    if mode == "full":
        return FULL_SNR_GRID, FULL_DRIFT_GRID, FULL_TRIALS_PER_CELL
    if mode == "reduced":
        return REDUCED_SNR_GRID, REDUCED_DRIFT_GRID, REDUCED_TRIALS_PER_CELL
    raise ValueError(f"unsupported injection grid mode: {mode}")


def _ci_run_url_from_environment() -> str | None:
    """Build a public Actions run URL only when running inside GitHub Actions."""
    run_id = os.environ.get("GITHUB_RUN_ID")
    repository = os.environ.get("GITHUB_REPOSITORY")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    if not run_id or not repository:
        return None
    repository_parts = repository.split("/")
    if len(repository_parts) != 2 or any(
        re.fullmatch(r"[A-Za-z0-9_.-]+", part) is None or part in {".", ".."}
        for part in repository_parts
    ):
        raise ValueError("GITHUB_REPOSITORY must be an owner/repository pair")
    if re.fullmatch(r"[0-9]+", run_id) is None:
        raise ValueError("GITHUB_RUN_ID must contain decimal digits")
    server_url = urlsplit(server)
    if server_url.scheme != "https" or not server_url.netloc or server_url.path:
        raise ValueError("GITHUB_SERVER_URL must be an HTTPS origin")
    return f"{server.rstrip('/')}/{repository}/actions/runs/{run_id}"


def _science_api() -> tuple[Any, Any]:
    """Import the optional generator and units with an actionable install error."""
    try:
        return importlib.import_module("setigen"), importlib.import_module("astropy.units")
    except ImportError as exc:
        raise RuntimeError(
            "EXP-002 requires the locked optional dependency group xenia[radio]"
        ) from exc


def _runtime_versions() -> dict[str, str]:
    """Record versions that affect synthetic generation and detector output."""
    packages = ("setigen", "astropy", "numpy", "turbo-seti", "blimpy", "h5py")
    try:
        versions = {package: version(package) for package in packages}
    except PackageNotFoundError as exc:
        raise RuntimeError(f"required radio package metadata is unavailable: {exc}") from exc
    return {"python": platform.python_version(), **versions}


def _grid_cells(
    snr_grid: Sequence[float], drift_grid: Sequence[float]
) -> tuple[tuple[float, float], ...]:
    """Enumerate grid cells in stable row-major order."""
    return tuple((snr, drift) for snr in snr_grid for drift in drift_grid)


def _build_trial_frame(
    *,
    snr_grid: Sequence[float],
    drift_grid: Sequence[float],
    trial_index: int,
    seed: int,
    frequency_channels: int = FREQUENCY_CHANNELS,
) -> tuple[Any, tuple[_InjectionPlan, ...]]:
    """Create one independent radiometer-noise frame with all grid lines injected."""
    if trial_index < 1 or seed < 0:
        raise ValueError("trial_index must be positive and seed must be non-negative")
    cells = _grid_cells(snr_grid, drift_grid)
    last_channel = FREQUENCY_MARGIN_CHANNELS + (len(cells) - 1) * FREQUENCY_SLOT_STRIDE_CHANNELS
    if last_channel + FREQUENCY_MARGIN_CHANNELS >= frequency_channels:
        raise ValueError("frequency_channels is too small for separated injection slots")

    setigen, units = _science_api()
    frame = setigen.Frame(
        fchans=frequency_channels,
        tchans=TIME_CHANNELS,
        df=FREQUENCY_RESOLUTION_HZ * units.Hz,
        dt=TIME_RESOLUTION_SECONDS * units.s,
        fch1=FRAME_FCH1_MHZ * units.MHz,
        ascending=False,
        seed=seed,
        mjd=FRAME_MJD,
        source_name="XENIA-SYNTHETIC",
    )
    frame.add_noise(x_mean=NOISE_MEAN, noise_type="chi2")

    duration_seconds = TIME_CHANNELS * TIME_RESOLUTION_SECONDS
    plans: list[_InjectionPlan] = []
    for slot_index, (snr, drift_hz_s) in enumerate(cells):
        channel_index = FREQUENCY_MARGIN_CHANNELS + (slot_index * FREQUENCY_SLOT_STRIDE_CHANNELS)
        center_frequency_hz = float(frame.get_frequency(channel_index))
        start_frequency_hz = center_frequency_hz - drift_hz_s * duration_seconds / 2
        stop_frequency_hz = start_frequency_hz + drift_hz_s * duration_seconds
        lower_bound_hz = min(start_frequency_hz, stop_frequency_hz) - SIGNAL_BOUND_MARGIN_HZ
        upper_bound_hz = max(start_frequency_hz, stop_frequency_hz) + SIGNAL_BOUND_MARGIN_HZ
        intensity = float(frame.get_intensity(snr))
        frame.add_signal(
            path=setigen.constant_path(
                f_start=start_frequency_hz * units.Hz,
                drift_rate=drift_hz_s * units.Hz / units.s,
            ),
            t_profile=setigen.constant_t_profile(level=intensity),
            f_profile=setigen.gaussian_f_profile(width=SIGNAL_WIDTH_HZ * units.Hz),
            bp_profile=setigen.constant_bp_profile(level=1.0),
            bounding_f_range=(lower_bound_hz * units.Hz, upper_bound_hz * units.Hz),
            integrate_path=False,
            integrate_f_profile=True,
            doppler_smearing=True,
            f_subsamples=F_SUBSAMPLES,
            smearing_subsamples=SMEARING_SUBSAMPLES,
        )
        plans.append(
            _InjectionPlan(
                snr=float(snr),
                drift_hz_s=float(drift_hz_s),
                trial_index=trial_index,
                seed=seed,
                channel_index=channel_index,
                frequency_mhz=center_frequency_hz / 1e6,
                start_frequency_mhz=start_frequency_hz / 1e6,
            )
        )
    return frame, tuple(plans)


def _save_neutral_filterbank(frame: Any, path: Path) -> None:
    """Write a temporary .fil and replace bundled sample metadata with neutral values."""
    try:
        from astropy.coordinates import Angle
        from blimpy import Waterfall
    except ImportError as exc:  # pragma: no cover - radio extra installation failure
        raise RuntimeError("EXP-002 requires blimpy to write the detector input") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    frame.save_fil(str(path), max_load=1)
    waterfall = Waterfall(str(path), max_load=1)
    synthetic_metadata: dict[str, object] = {
        "source_name": "XENIA-SYNTHETIC",
        "rawdatafile": "Synthetic setigen injection; not telescope data",
        "telescope_id": 0,
        "machine_id": 0,
        "src_raj": Angle(0.0, unit="hourangle"),
        "src_dej": Angle(0.0, unit="deg"),
        "nbeams": 1,
        "ibeam": 0,
    }
    waterfall.header.update(synthetic_metadata)
    waterfall.file_header.update(synthetic_metadata)
    waterfall.write_to_fil(str(path))

    verified = Waterfall(str(path), max_load=1)
    if (
        verified.header.get("source_name") != "XENIA-SYNTHETIC"
        or int(verified.header.get("telescope_id", -1)) != 0
        or int(verified.header.get("machine_id", -1)) != 0
    ):
        raise ValueError("temporary FILTERBANK metadata is not marked as synthetic")


def _as_floor_hit(hit: DopplerHit) -> FloorDetectedHit:
    """Convert the shared detector type into the artifact schema."""
    return FloorDetectedHit.model_validate(hit.as_dict())


def _as_search_trial(
    result: DetectorResult,
    *,
    trial_index: int,
    seed: int,
    injected_signal_count: int,
) -> FloorSearchTrial:
    """Capture all parsed hits, temporary table hashes, and compatibility warnings."""
    return FloorSearchTrial(
        trial_index=trial_index,
        seed=seed,
        injected_signal_count=injected_signal_count,
        detected_hits=tuple(_as_floor_hit(hit) for hit in result.hits),
        detector_artifacts=tuple(
            FloorDetectorArtifact(
                filename=artifact.filename,
                sha256=artifact.sha256,
                size_bytes=artifact.size_bytes,
            )
            for artifact in result.artifacts
        ),
        warnings=result.warnings,
    )


def _match_trial(
    plans: Sequence[_InjectionPlan],
    hits: Sequence[DopplerHit],
    *,
    frequency_tolerance_hz: float = FREQUENCY_TOLERANCE_HZ,
    drift_tolerance_hz_s: float = DRIFT_TOLERANCE_HZ_S,
    minimum_snr: float = DETECTOR_SNR_THRESHOLD,
) -> tuple[RecoveryMeasurement, ...]:
    """Match detector hits one-to-one to the nearest injected frequency/drift pair."""
    available_hits = set(range(len(hits)))
    measurements: list[RecoveryMeasurement] = []
    for plan in plans:
        candidates: list[tuple[tuple[float, float, float, int], int, float, float]] = []
        for hit_index in available_hits:
            hit = hits[hit_index]
            frequency_error_hz = abs(hit.uncorrected_frequency_mhz - plan.frequency_mhz) * 1e6
            drift_error_hz_s = abs(hit.drift_hz_s - plan.drift_hz_s)
            if (
                frequency_error_hz <= frequency_tolerance_hz
                and drift_error_hz_s <= drift_tolerance_hz_s
                and hit.snr >= minimum_snr
            ):
                score = (
                    frequency_error_hz / frequency_tolerance_hz,
                    drift_error_hz_s / drift_tolerance_hz_s,
                    -hit.snr,
                    hit.top_hit,
                )
                candidates.append((score, hit_index, frequency_error_hz, drift_error_hz_s))
        if not candidates:
            measurements.append(
                RecoveryMeasurement(
                    snr=plan.snr,
                    drift_hz_s=plan.drift_hz_s,
                    trial_index=plan.trial_index,
                    seed=plan.seed,
                    frequency_mhz=plan.frequency_mhz,
                    injected_start_frequency_mhz=plan.start_frequency_mhz,
                    recovered=False,
                )
            )
            continue

        _, hit_index, frequency_error_hz, drift_error_hz_s = min(candidates)
        available_hits.remove(hit_index)
        hit = hits[hit_index]
        measurements.append(
            RecoveryMeasurement(
                snr=plan.snr,
                drift_hz_s=plan.drift_hz_s,
                trial_index=plan.trial_index,
                seed=plan.seed,
                frequency_mhz=plan.frequency_mhz,
                injected_start_frequency_mhz=plan.start_frequency_mhz,
                recovered=True,
                matched_hit=_as_floor_hit(hit),
                frequency_error_hz=frequency_error_hz,
                drift_error_hz_s=drift_error_hz_s,
            )
        )
    return tuple(measurements)


def _runtime_grid_counts(
    measurements: Sequence[RecoveryMeasurement],
    snr_grid: Sequence[float],
    drift_grid: Sequence[float],
    trials_per_cell: int,
) -> tuple[tuple[tuple[int, ...], ...], tuple[tuple[float, ...], ...]]:
    """Aggregate per-injection decisions into count and fraction matrices."""
    count_rows: list[tuple[int, ...]] = []
    fraction_rows: list[tuple[float, ...]] = []
    for snr in snr_grid:
        counts: list[int] = []
        fractions: list[float] = []
        for drift in drift_grid:
            recovered = sum(
                measurement.recovered
                for measurement in measurements
                if measurement.snr == snr and measurement.drift_hz_s == drift
            )
            counts.append(recovered)
            fractions.append(recovered / trials_per_cell)
        count_rows.append(tuple(counts))
        fraction_rows.append(tuple(fractions))
    return tuple(count_rows), tuple(fraction_rows)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _initial_parameters(
    *,
    mode: GridMode,
    seed: int,
    snr_grid: Sequence[float],
    drift_grid: Sequence[float],
    trials_per_cell: int,
    ci_run_url: str | None,
) -> dict[str, object]:
    """Describe all deterministic generator, grid, detector, and matching choices."""
    return {
        "mode": mode,
        "seed": seed,
        "seed_strategy": "base seed + trial index - 1; one independent seeded frame per trial",
        "snr_grid": list(snr_grid),
        "drift_grid_hz_s": list(drift_grid),
        "trials_per_cell": trials_per_cell,
        "signals_per_trial": len(snr_grid) * len(drift_grid),
        "generator": {
            "package": "setigen",
            "distribution": "chi2",
            "noise_mean": NOISE_MEAN,
            "intensity_calibration": "Frame.get_intensity(snr) = snr * noise_std / sqrt(tchans)",
            "frequency_profile": "Gaussian",
            "time_profile": "constant",
            "path": "linear constant drift",
            "path_sampling": (
                "integration starts; Doppler smearing averages across each integration"
            ),
            "signal_width_hz": SIGNAL_WIDTH_HZ,
            "frequency_slot_stride_channels": FREQUENCY_SLOT_STRIDE_CHANNELS,
            "frequency_slot_spacing_hz": FREQUENCY_SLOT_STRIDE_CHANNELS * FREQUENCY_RESOLUTION_HZ,
            "f_subsamples": F_SUBSAMPLES,
            "smearing_subsamples": SMEARING_SUBSAMPLES,
            "temporary_metadata": {
                "source_name": "XENIA-SYNTHETIC",
                "telescope_id": 0,
                "machine_id": 0,
                "source_coordinates_deg": [0.0, 0.0],
            },
        },
        "frame": {
            "frequency_channels": FREQUENCY_CHANNELS,
            "time_channels": TIME_CHANNELS,
            "frequency_resolution_hz": FREQUENCY_RESOLUTION_HZ,
            "time_resolution_seconds": TIME_RESOLUTION_SECONDS,
            "frame_center_frequency_mhz": FRAME_CENTER_FREQUENCY_MHZ,
            "frame_fch1_mhz": FRAME_FCH1_MHZ,
            "mjd": FRAME_MJD,
        },
        "detector": {
            "package": "turbo-seti",
            "minimum_snr": DETECTOR_SNR_THRESHOLD,
            "max_abs_drift_hz_s": MAX_ABS_DRIFT_HZ_S,
            "n_coarse_chan": 1,
            "n_partitions": 1,
            "precision": 1,
        },
        "recovery_match": {
            "frequency_reference": "setigen frame channel center at the observation midpoint",
            "frequency_tolerance_hz": FREQUENCY_TOLERANCE_HZ,
            "drift_tolerance_hz_s": DRIFT_TOLERANCE_HZ_S,
            "one_detector_hit_can_recover_at_most_one_injection": True,
        },
        "ci_run_url": ci_run_url,
        "temporary_filterbanks_and_detector_tables": "removed after each trial",
    }


def _write_failure_record(
    *,
    run_directory: Path,
    run_id: str,
    repository_root: Path,
    command: Sequence[str],
    parameters: dict[str, object],
    started_at: datetime,
    experiment_id: str,
    error: Exception,
    trial_index: int | None,
    completed_searches: Sequence[FloorSearchTrial],
    completed_measurements: Sequence[RecoveryMeasurement],
    runtime_versions: dict[str, str],
) -> tuple[RunManifest, Path]:
    """Persist partial typed evidence and a failed manifest before surfacing an error."""
    finished_at = datetime.now(UTC)
    failure_path = run_directory / "failure.json"
    details = {
        "run_id": run_id,
        "experiment_id": experiment_id,
        "failed_trial_index": trial_index,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "runtime_versions": runtime_versions,
        "completed_searches": [search.model_dump(mode="json") for search in completed_searches],
        "completed_measurements": [
            measurement.model_dump(mode="json") for measurement in completed_measurements
        ],
    }
    _write_json(failure_path, details)
    parameters.update(
        {
            "runtime_versions": runtime_versions,
            "failed_trial_index": trial_index,
            "failure_type": type(error).__name__,
            "failure_message": str(error),
        }
    )
    return create_run_manifest(
        run_id=run_id,
        command=command,
        parameters=parameters,
        inputs=(),
        outputs=(output_ref(failure_path, repository_root=repository_root),),
        started_at=started_at,
        finished_at=finished_at,
        outcome="failed",
        notes=(
            "EXP-002 stopped before completion; partial trial results are retained.",
            "All generated inputs were synthetic setigen data, not telescope observations.",
        ),
        repository_root=repository_root,
        demo=False,
        pillar="I · Sensor",
        experiment_id=experiment_id,
        manifest_path=run_directory / "manifest.json",
    )


def run_floor(
    repository_root: Path,
    command: Sequence[str],
    *,
    mode: GridMode = "full",
    seed: int = 20261012,
    experiment_id: str = "EXP-002",
) -> tuple[RunManifest, Path]:
    """Run a full or reduced synthetic injection grid and record complete provenance."""
    if mode not in {"full", "reduced"}:
        raise ValueError("mode must be either 'full' or 'reduced'")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    if not experiment_id.strip():
        raise ValueError("experiment_id must not be empty")

    root = repository_root.resolve()
    started_at = datetime.now(UTC)
    run_id = new_run_id(started_at, "exp-002-floor")
    run_directory = root / "runs" / run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    grid_path = run_directory / "recovery_grid.json"
    snr_grid, drift_grid, trials_per_cell = grid_values(mode)
    ci_run_url: str | None = None
    parameters = _initial_parameters(
        mode=mode,
        seed=seed,
        snr_grid=snr_grid,
        drift_grid=drift_grid,
        trials_per_cell=trials_per_cell,
        ci_run_url=ci_run_url,
    )
    runtime_versions: dict[str, str] = {}
    searches: list[FloorSearchTrial] = []
    measurements: list[RecoveryMeasurement] = []
    current_trial: int | None = None

    try:
        ci_run_url = _ci_run_url_from_environment()
        parameters["ci_run_url"] = ci_run_url
        runtime_versions = _runtime_versions()
        parameters["runtime_versions"] = runtime_versions
        cells = _grid_cells(snr_grid, drift_grid)
        with tempfile.TemporaryDirectory(prefix="xenia-exp002-") as temporary_directory:
            temporary_root = Path(temporary_directory)
            for current_trial in range(1, trials_per_cell + 1):
                trial_seed = seed + current_trial - 1
                frame, plans = _build_trial_frame(
                    snr_grid=snr_grid,
                    drift_grid=drift_grid,
                    trial_index=current_trial,
                    seed=trial_seed,
                )
                filterbank_path = temporary_root / f"trial-{current_trial:02d}.fil"
                _save_neutral_filterbank(frame, filterbank_path)
                detector_result = run_turboseti(
                    filterbank_path,
                    output_directory=temporary_root / f"detector-{current_trial:02d}",
                    max_drift_hz_s=MAX_ABS_DRIFT_HZ_S,
                    minimum_snr=DETECTOR_SNR_THRESHOLD,
                    n_coarse_channels=1,
                )
                searches.append(
                    _as_search_trial(
                        detector_result,
                        trial_index=current_trial,
                        seed=trial_seed,
                        injected_signal_count=len(cells),
                    )
                )
                measurements.extend(_match_trial(plans, detector_result.hits))

        recovered_count, recovered_fraction = _runtime_grid_counts(
            measurements,
            snr_grid,
            drift_grid,
            trials_per_cell,
        )
        grid = RecoveryGridArtifact(
            run_id=run_id,
            mode=mode,
            seed=seed,
            snr_grid=snr_grid,
            drift_grid=drift_grid,
            trials_per_cell=trials_per_cell,
            max_abs_drift_hz_s=MAX_ABS_DRIFT_HZ_S,
            detector_snr_threshold=DETECTOR_SNR_THRESHOLD,
            frequency_tolerance_hz=FREQUENCY_TOLERANCE_HZ,
            drift_tolerance_hz_s=DRIFT_TOLERANCE_HZ_S,
            frequency_channels=FREQUENCY_CHANNELS,
            time_channels=TIME_CHANNELS,
            frame_bandwidth_hz=FREQUENCY_CHANNELS * FREQUENCY_RESOLUTION_HZ,
            frequency_resolution_hz=FREQUENCY_RESOLUTION_HZ,
            time_resolution_seconds=TIME_RESOLUTION_SECONDS,
            frame_center_frequency_mhz=FRAME_CENTER_FREQUENCY_MHZ,
            frequency_slot_spacing_hz=FREQUENCY_SLOT_STRIDE_CHANNELS * FREQUENCY_RESOLUTION_HZ,
            signal_width_hz=SIGNAL_WIDTH_HZ,
            noise_mean=NOISE_MEAN,
            ci_run_url=ci_run_url,
            runtime_versions=runtime_versions,
            searches=tuple(searches),
            measurements=tuple(measurements),
            recovered_count=recovered_count,
            recovered_fraction=recovered_fraction,
        )
        _write_json(grid_path, grid.model_dump(mode="json"))
        payload = FloorPayload(
            kind="detection_floor",
            experiment="EXP-002",
            snr_grid=snr_grid,
            drift_grid=drift_grid,
            trials_per_cell=trials_per_cell,
            recovered_fraction=recovered_fraction,
            ci_run_url=ci_run_url,
        )
        warnings = tuple(warning for search in searches for warning in search.warnings)
        notes = (
            "Synthetic setigen calibration; not telescope observations.",
            "Trials use deterministic seeds and one-to-one frequency/drift hit matching.",
            *warnings,
        )
        manifest, manifest_path = create_run_manifest(
            run_id=run_id,
            command=command,
            parameters=parameters,
            inputs=(),
            outputs=(output_ref(grid_path, repository_root=root),),
            started_at=started_at,
            finished_at=datetime.now(UTC),
            outcome="recovery_grid_completed",
            notes=notes,
            repository_root=root,
            demo=False,
            pillar="I · Sensor",
            experiment_id=experiment_id,
            mission_control=payload,
            manifest_path=run_directory / "manifest.json",
        )
        return manifest, manifest_path
    except Exception as exc:
        failure_manifest, failure_manifest_path = _write_failure_record(
            run_directory=run_directory,
            run_id=run_id,
            repository_root=root,
            command=command,
            parameters=parameters,
            started_at=started_at,
            experiment_id=experiment_id,
            error=exc,
            trial_index=current_trial,
            completed_searches=searches,
            completed_measurements=measurements,
            runtime_versions=runtime_versions,
        )
        raise RuntimeError(
            f"EXP-002 failed in trial {current_trial}: {type(exc).__name__}: {exc}; "
            f"run_id={failure_manifest.run_id}; "
            f"manifest={failure_manifest_path}"
        ) from exc


__all__ = [
    "DETECTOR_SNR_THRESHOLD",
    "DRIFT_TOLERANCE_HZ_S",
    "FULL_DRIFT_GRID",
    "FULL_SNR_GRID",
    "FULL_TRIALS_PER_CELL",
    "FREQUENCY_TOLERANCE_HZ",
    "MAX_ABS_DRIFT_HZ_S",
    "REDUCED_DRIFT_GRID",
    "REDUCED_SNR_GRID",
    "REDUCED_TRIALS_PER_CELL",
    "GridMode",
    "grid_values",
    "run_floor",
]
