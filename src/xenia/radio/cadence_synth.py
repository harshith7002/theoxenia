"""Seeded six-scan ABACAD frames for the EXP-004 known-answer cadence.

The generator writes temporary filterbanks and a truth table. It does not
search them and it does not claim a telescope sensitivity.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from xenia.radio.floor_config import (
    F_SUBSAMPLES,
    FRAME_FCH1_MHZ,
    FRAME_MJD,
    FREQUENCY_CHANNELS,
    FREQUENCY_RESOLUTION_HZ,
    NOISE_MEAN,
    SIGNAL_BOUND_MARGIN_HZ,
    SIGNAL_WIDTH_HZ,
    SMEARING_SUBSAMPLES,
    TIME_CHANNELS,
    TIME_RESOLUTION_SECONDS,
)

CADENCE_ROLES: tuple[str, ...] = ("A", "B", "A", "C", "A", "D")
ON_SCAN_INDEXES: tuple[int, ...] = (0, 2, 4)
OFF_SCAN_INDEXES: tuple[int, ...] = (1, 3, 5)
REDUCED_FREQUENCY_CHANNELS = 8_192
INJECTION_CHANNELS: dict[str, int] = {
    "on_only": 400,
    "in_off": 1_800,
    "single_pointing": 3_200,
    "known_source": 4_600,
}
# Drifts stay well below the 4 Hz/s search limit and far enough apart that a
# 0.15 Hz/s association window cannot swap two injections.
INJECTION_DRIFTS_HZ_S: dict[str, float] = {
    "on_only": 0.8,
    "in_off": 0.0,
    "single_pointing": 0.3,
    "known_source": 0.6,
}
INJECTION_SNR = 40.0
EXPECTED_VERDICTS: dict[str, str] = {
    "on_only": "ON_ONLY",
    "in_off": "IN_OFF",
    "single_pointing": "SINGLE_POINTING",
    "known_source": "KNOWN_SOURCE",
}

type CadenceMode = Literal["full", "reduced"]


@dataclass(frozen=True, slots=True)
class InjectionTruth:
    """One line planted in a known subset of the six scans."""

    injection_id: str
    expected_verdict: str
    channel_index: int
    start_frequency_mhz: float
    drift_hz_s: float
    snr: float
    present_scan_indexes: tuple[int, ...]

    def frequency_mhz_at(self, elapsed_seconds: float) -> float:
        """Return the injected frequency after this many seconds of cadence time."""
        return self.start_frequency_mhz + self.drift_hz_s * elapsed_seconds / 1e6


@dataclass(frozen=True, slots=True)
class ScanTruth:
    """One generated scan and the injections that were planted in it."""

    scan_index: int
    role: str
    on_source: bool
    seed: int
    mjd: float
    path: Path
    injection_ids: tuple[str, ...]


def scan_duration_seconds() -> float:
    """Return the length of one 16-integration frame."""
    return TIME_CHANNELS * TIME_RESOLUTION_SECONDS


def channel_frequency_mhz(channel_index: int) -> float:
    """Return the frequency of one channel at fch1 with descending channels."""
    if channel_index < 0:
        raise ValueError("channel_index cannot be negative")
    return FRAME_FCH1_MHZ - channel_index * FREQUENCY_RESOLUTION_HZ / 1e6


def frequency_channels(mode: CadenceMode) -> int:
    """Return the channel count for a full EXP-002 frame or the CI frame."""
    if mode == "full":
        return FREQUENCY_CHANNELS
    if mode == "reduced":
        return REDUCED_FREQUENCY_CHANNELS
    raise ValueError("mode must be full or reduced")


def injection_truths() -> tuple[InjectionTruth, ...]:
    """Return the four known-answer lines. Scan membership is the expected label."""
    present = {
        "on_only": ON_SCAN_INDEXES,
        "in_off": tuple(range(len(CADENCE_ROLES))),
        "single_pointing": (0,),
        "known_source": ON_SCAN_INDEXES,
    }
    truths: list[InjectionTruth] = []
    for injection_id in ("on_only", "in_off", "single_pointing", "known_source"):
        truths.append(
            InjectionTruth(
                injection_id=injection_id,
                expected_verdict=EXPECTED_VERDICTS[injection_id],
                channel_index=INJECTION_CHANNELS[injection_id],
                start_frequency_mhz=channel_frequency_mhz(INJECTION_CHANNELS[injection_id]),
                drift_hz_s=INJECTION_DRIFTS_HZ_S[injection_id],
                snr=INJECTION_SNR,
                present_scan_indexes=present[injection_id],
            )
        )
    return tuple(truths)


def write_cadence(
    directory: Path, *, seed: int, mode: CadenceMode
) -> tuple[tuple[ScanTruth, ...], tuple[InjectionTruth, ...]]:
    """Write six neutral-metadata HDF5 filterbanks and return their truth table.

    Each scan is one seeded frame. A line that continues across scans is
    injected at the frequency it would have reached by that scan's start.
    """
    if seed < 0:
        raise ValueError("seed must be non-negative")
    nchans = frequency_channels(mode)
    truths = injection_truths()
    last_channel = max(item.channel_index for item in truths)
    if last_channel + 1 >= nchans:
        raise ValueError("frame is too narrow for the injection channels")

    directory.mkdir(parents=True, exist_ok=True)
    duration = scan_duration_seconds()
    scans: list[ScanTruth] = []
    for scan_index, role in enumerate(CADENCE_ROLES):
        present = tuple(item for item in truths if scan_index in item.present_scan_indexes)
        frame_seed = seed + scan_index
        mjd = FRAME_MJD + (scan_index * duration) / 86400.0
        frame = _build_frame(
            nchans=nchans,
            seed=frame_seed,
            mjd=mjd,
            elapsed_seconds=scan_index * duration,
            injections=present,
        )
        path = directory / f"scan-{scan_index}-{role}.h5"
        _save_neutral_hdf5(frame, path, mjd=mjd)
        scans.append(
            ScanTruth(
                scan_index=scan_index,
                role=role,
                on_source=role == "A",
                seed=frame_seed,
                mjd=mjd,
                path=path,
                injection_ids=tuple(item.injection_id for item in present),
            )
        )
    return tuple(scans), truths


def _build_frame(
    *,
    nchans: int,
    seed: int,
    mjd: float,
    elapsed_seconds: float,
    injections: tuple[InjectionTruth, ...],
) -> Any:
    setigen, units = _science_api()
    frame = setigen.Frame(
        fchans=nchans,
        tchans=TIME_CHANNELS,
        df=FREQUENCY_RESOLUTION_HZ * units.Hz,
        dt=TIME_RESOLUTION_SECONDS * units.s,
        fch1=FRAME_FCH1_MHZ * units.MHz,
        ascending=False,
        seed=seed,
        mjd=mjd,
        source_name="XENIA-SYNTHETIC",
    )
    frame.add_noise(x_mean=NOISE_MEAN, noise_type="chi2")
    duration = scan_duration_seconds()
    for injection in injections:
        start_hz = injection.frequency_mhz_at(elapsed_seconds) * 1e6
        stop_hz = start_hz + injection.drift_hz_s * duration
        lower_hz = min(start_hz, stop_hz) - SIGNAL_BOUND_MARGIN_HZ
        upper_hz = max(start_hz, stop_hz) + SIGNAL_BOUND_MARGIN_HZ
        frame.add_signal(
            path=setigen.constant_path(
                f_start=start_hz * units.Hz,
                drift_rate=injection.drift_hz_s * units.Hz / units.s,
            ),
            t_profile=setigen.constant_t_profile(level=float(frame.get_intensity(injection.snr))),
            f_profile=setigen.gaussian_f_profile(width=SIGNAL_WIDTH_HZ * units.Hz),
            bp_profile=setigen.constant_bp_profile(level=1.0),
            bounding_f_range=(lower_hz * units.Hz, upper_hz * units.Hz),
            integrate_path=False,
            integrate_f_profile=True,
            doppler_smearing=True,
            f_subsamples=F_SUBSAMPLES,
            smearing_subsamples=SMEARING_SUBSAMPLES,
        )
    return frame


def _save_neutral_hdf5(frame: Any, path: Path, *, mjd: float) -> None:
    """Write HDF5 and replace bundled sample metadata with neutral values."""
    try:
        from astropy.coordinates import Angle
        from blimpy import Waterfall
    except ImportError as exc:  # pragma: no cover - radio extra installation failure
        raise RuntimeError("EXP-004 requires blimpy to write the detector input") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    frame.save_h5(str(path))
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
        "tstart": mjd,
    }
    waterfall.header.update(synthetic_metadata)
    waterfall.file_header.update(synthetic_metadata)
    waterfall.write_to_hdf5(str(path))
    verified = Waterfall(str(path), max_load=1)
    if verified.header.get("source_name") != "XENIA-SYNTHETIC":
        raise ValueError("temporary HDF5 metadata is not marked as synthetic")


def _science_api() -> tuple[Any, Any]:
    try:
        return importlib.import_module("setigen"), importlib.import_module("astropy.units")
    except ImportError as exc:
        raise RuntimeError("EXP-004 requires the locked optional extra xenia[radio]") from exc
