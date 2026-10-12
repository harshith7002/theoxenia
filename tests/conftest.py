"""Shared, deterministic fixtures for Mission Control M0 tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from xenia.live.models import (
    FloorSearchTrial,
    LiveState,
    RecoveryGridArtifact,
    RecoveryMeasurement,
    RunManifest,
)
from xenia.live.state import build_state, load_manifests
from xenia.radio.floor_config import (
    DETECTOR_SNR_THRESHOLD,
    DRIFT_TOLERANCE_HZ_S,
    FRAME_CENTER_FREQUENCY_MHZ,
    FREQUENCY_CHANNELS,
    FREQUENCY_RESOLUTION_HZ,
    FREQUENCY_SLOT_STRIDE_CHANNELS,
    FREQUENCY_TOLERANCE_HZ,
    MAX_ABS_DRIFT_HZ_S,
    NOISE_MEAN,
    REDUCED_DRIFT_GRID,
    REDUCED_SNR_GRID,
    REDUCED_TRIALS_PER_CELL,
    SIGNAL_WIDTH_HZ,
    TIME_CHANNELS,
    TIME_RESOLUTION_SECONDS,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEMO_RUNS = REPOSITORY_ROOT / "tests" / "fixtures" / "live"
FIXED_TIME = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


@pytest.fixture
def demo_manifests() -> list[RunManifest]:
    """Return all checked-in synthetic fixture manifests."""
    return load_manifests(DEMO_RUNS)


@pytest.fixture
def demo_state(demo_manifests: list[RunManifest]) -> LiveState:
    """Return a reproducible state document from the synthetic fixtures."""
    return build_state(
        demo_manifests,
        generated_at=FIXED_TIME,
        git_sha="test-sha",
        package_version="0.1.0",
    )


@pytest.fixture
def fixed_time() -> datetime:
    """Return the fixed UTC test clock."""
    return FIXED_TIME


@pytest.fixture
def reduced_recovery_grid() -> RecoveryGridArtifact:
    """Return a complete 3×3 null-result grid with one seeded trial."""
    seed = 20261012
    measurements = tuple(
        RecoveryMeasurement(
            snr=snr,
            drift_hz_s=drift,
            trial_index=1,
            seed=seed,
            frequency_mhz=FRAME_CENTER_FREQUENCY_MHZ + (index + 1) * 0.001,
            injected_start_frequency_mhz=FRAME_CENTER_FREQUENCY_MHZ + (index + 1) * 0.001,
            recovered=False,
        )
        for index, (snr, drift) in enumerate(
            (snr, drift) for snr in REDUCED_SNR_GRID for drift in REDUCED_DRIFT_GRID
        )
    )
    zeros = tuple(tuple(0 for _ in REDUCED_DRIFT_GRID) for _ in REDUCED_SNR_GRID)
    zero_fractions = tuple(tuple(0.0 for _ in REDUCED_DRIFT_GRID) for _ in REDUCED_SNR_GRID)
    return RecoveryGridArtifact(
        run_id="reduced-grid-fixture",
        mode="reduced",
        seed=seed,
        snr_grid=REDUCED_SNR_GRID,
        drift_grid=REDUCED_DRIFT_GRID,
        trials_per_cell=REDUCED_TRIALS_PER_CELL,
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
        ci_run_url=None,
        runtime_versions={"python": "3.15.0"},
        searches=(
            FloorSearchTrial(
                trial_index=1,
                seed=seed,
                injected_signal_count=len(REDUCED_SNR_GRID) * len(REDUCED_DRIFT_GRID),
            ),
        ),
        measurements=measurements,
        recovered_count=zeros,
        recovered_fraction=zero_fractions,
    )
