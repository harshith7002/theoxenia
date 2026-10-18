"""Immutable EXP-002 grid and generator constants, with no optional imports."""

from __future__ import annotations

from typing import Literal

FULL_SNR_GRID = (5.0, 8.0, 10.0, 12.0, 15.0, 20.0, 30.0, 40.0)
FULL_DRIFT_GRID = (-4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0)
REDUCED_SNR_GRID = (5.0, 15.0, 40.0)
REDUCED_DRIFT_GRID = (-4.0, 0.0, 4.0)
FULL_TRIALS_PER_CELL = 5
REDUCED_TRIALS_PER_CELL = 1

TIME_CHANNELS = 16
FREQUENCY_CHANNELS = 131_072
FREQUENCY_RESOLUTION_HZ = 2.7939677238464355
TIME_RESOLUTION_SECONDS = 18.253611008
FRAME_FCH1_MHZ = 6_000.0
FRAME_MJD = 60_000.0
FRAME_CENTER_FREQUENCY_MHZ = FRAME_FCH1_MHZ - (
    (FREQUENCY_CHANNELS - 1) * FREQUENCY_RESOLUTION_HZ / 2e6
)
FREQUENCY_SLOT_STRIDE_CHANNELS = 1_600
FREQUENCY_MARGIN_CHANNELS = 512
SIGNAL_WIDTH_HZ = 2.0 * FREQUENCY_RESOLUTION_HZ
SIGNAL_BOUND_MARGIN_HZ = 5.0 * SIGNAL_WIDTH_HZ
NOISE_MEAN = 1.0
MAX_ABS_DRIFT_HZ_S = 4.0
DETECTOR_SNR_THRESHOLD = 5.0
FREQUENCY_TOLERANCE_HZ = 3.0 * FREQUENCY_RESOLUTION_HZ
# turboSETI's own bin: |foff| / ((n_integrations - 1) * tsamp). See
# turbo_seti.find_doppler.data_handler.drift_rate_resolution.
DETECTOR_DRIFT_RESOLUTION_HZ_S = FREQUENCY_RESOLUTION_HZ / (
    (TIME_CHANNELS - 1) * TIME_RESOLUTION_SECONDS
)
# Three detector bins. A seed-20261012 full-width probe at SNR 40 put real
# |drift| <= 3 Hz/s hits 0, 1, 2, and 3 bins off the injected rate, so the
# previous two-bin window (and the n_integrations denominator) dropped them.
DRIFT_TOLERANCE_HZ_S = 3.0 * DETECTOR_DRIFT_RESOLUTION_HZ_S
F_SUBSAMPLES = 4
SMEARING_SUBSAMPLES = 64
MATCHING_VERSION: Literal[2] = 2
MATCHING_RULE_V1 = (
    "v1 compares uncorrected_frequency_mhz to the mid-observation centre frequency_mhz"
)
MATCHING_RULE_V2 = (
    "v2 accepts a hit whose uncorrected frequency lies within three fine channels of "
    "the injected path from start_frequency_mhz across the frame, and whose drift is "
    "within three turboSETI drift-resolution bins of the injected physical drift; "
    "one hit recovers at most one injection. turboSETI 2.3.2 writes the same channel "
    "for corrected and uncorrected frequency."
)


type GridMode = Literal["full", "reduced"]

__all__ = [
    "DETECTOR_DRIFT_RESOLUTION_HZ_S",
    "DETECTOR_SNR_THRESHOLD",
    "DRIFT_TOLERANCE_HZ_S",
    "FREQUENCY_CHANNELS",
    "FREQUENCY_MARGIN_CHANNELS",
    "FREQUENCY_RESOLUTION_HZ",
    "FREQUENCY_SLOT_STRIDE_CHANNELS",
    "FREQUENCY_TOLERANCE_HZ",
    "FULL_DRIFT_GRID",
    "FULL_SNR_GRID",
    "FULL_TRIALS_PER_CELL",
    "FRAME_CENTER_FREQUENCY_MHZ",
    "FRAME_FCH1_MHZ",
    "FRAME_MJD",
    "F_SUBSAMPLES",
    "GridMode",
    "MATCHING_RULE_V1",
    "MATCHING_RULE_V2",
    "MATCHING_VERSION",
    "MAX_ABS_DRIFT_HZ_S",
    "NOISE_MEAN",
    "REDUCED_DRIFT_GRID",
    "REDUCED_SNR_GRID",
    "REDUCED_TRIALS_PER_CELL",
    "SIGNAL_BOUND_MARGIN_HZ",
    "SIGNAL_WIDTH_HZ",
    "SMEARING_SUBSAMPLES",
    "TIME_CHANNELS",
    "TIME_RESOLUTION_SECONDS",
]
