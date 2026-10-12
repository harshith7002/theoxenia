"""Search one ABACAD cadence: FindDoppler on each file, then find_event_pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xenia.radio.cadence_synth import ScanTruth
from xenia.radio.detector import DopplerHit, run_turboseti

FILTER_THRESHOLD = 3
MAX_DRIFT_HZ_S = 4.0
MINIMUM_SNR = 10.0
N_COARSE_CHAN = 1
_TURBOSETI_LOG_ERROR = "format argument: %i requires a real number, not numpy.ndarray"


@dataclass(frozen=True, slots=True)
class ScanDetection:
    """One turboSETI hit from one scan."""

    scan_index: int
    role: str
    on_source: bool
    frequency_mhz: float
    drift_hz_s: float
    snr: float


@dataclass(frozen=True, slots=True)
class FilterEvent:
    """One event that passed find_event filter threshold 3."""

    event_id: str
    frequency_mhz: float
    drift_hz_s: float
    snr: float


@dataclass(frozen=True, slots=True)
class CadenceSearch:
    """Per-scan hits plus the events that survived the ON/OFF filter."""

    detections: tuple[ScanDetection, ...]
    events: tuple[FilterEvent, ...]
    warnings: tuple[str, ...]


def search_cadence(scans: tuple[ScanTruth, ...], *, work_dir: Path) -> CadenceSearch:
    """Run the spec search. Temporary `.dat` tables stay under work_dir.

    FindDoppler uses max drift 4 Hz/s, SNR 10, and one coarse channel. The
    event step uses filter threshold 3 and keeps zero-drift hits so an OFF
    detection can still be labelled. turboSETI's known hit-count log TypeError
    is retained as a warning when the `.dat` file exists. An empty table is a
    completed search.
    """
    if len(scans) != 6:
        raise ValueError("an ABACAD cadence has six scans")
    work_dir.mkdir(parents=True, exist_ok=True)
    detections: list[ScanDetection] = []
    warnings: list[str] = []
    dat_paths: list[Path] = []
    for scan in scans:
        scan_dir = work_dir / f"scan-{scan.scan_index}"
        result = run_turboseti(
            scan.path,
            output_directory=scan_dir,
            max_drift_hz_s=MAX_DRIFT_HZ_S,
            minimum_snr=MINIMUM_SNR,
            n_coarse_channels=N_COARSE_CHAN,
        )
        warnings.extend(result.warnings)
        dat_files = tuple(sorted(scan_dir.glob("*.dat")))
        if len(dat_files) != 1:
            raise RuntimeError(
                f"scan {scan.scan_index} produced {len(dat_files)} .dat files; expected one"
            )
        dat_paths.append(dat_files[0])
        _link_header_sibling(scan.path, dat_files[0])
        detections.extend(_detections(scan, result.hits))

    events = _find_events(dat_paths, work_dir)
    return CadenceSearch(
        detections=tuple(detections),
        events=events,
        warnings=tuple(warnings),
    )


def _detections(scan: ScanTruth, hits: tuple[DopplerHit, ...]) -> tuple[ScanDetection, ...]:
    return tuple(
        ScanDetection(
            scan_index=scan.scan_index,
            role=scan.role,
            on_source=scan.on_source,
            frequency_mhz=hit.uncorrected_frequency_mhz,
            drift_hz_s=hit.drift_hz_s,
            snr=hit.snr,
        )
        for hit in hits
    )


def _link_header_sibling(h5_path: Path, dat_path: Path) -> None:
    """Place the HDF5 header where find_event_pipeline looks it up from the `.dat`."""
    sibling = dat_path.with_suffix(".h5")
    if sibling.exists():
        return
    sibling.symlink_to(h5_path.resolve())


def _find_events(dat_paths: list[Path], work_dir: Path) -> tuple[FilterEvent, ...]:
    try:
        from turbo_seti.find_event.find_event_pipeline import find_event_pipeline
    except ImportError as exc:  # pragma: no cover - radio extra installation failure
        raise RuntimeError("cadence search requires turbo-seti from the radio extra") from exc

    list_path = work_dir / "cadence.lst"
    list_path.write_text("".join(f"{path}\n" for path in dat_paths), encoding="utf-8")
    try:
        table = find_event_pipeline(
            str(list_path),
            h5_file_list_str=None,
            check_zero_drift=True,
            filter_threshold=FILTER_THRESHOLD,
            on_off_first="ON",
            number_in_cadence=6,
            saving=False,
            user_validation=False,
            sortby_tstart=True,
        )
    except TypeError as exc:
        if _TURBOSETI_LOG_ERROR not in str(exc):
            raise
        raise RuntimeError(
            "turboSETI find_event raised its known logging TypeError before returning events"
        ) from exc
    if table is None or len(table) == 0:
        return ()
    return _collapse_events(table)


def _collapse_events(table: object) -> tuple[FilterEvent, ...]:
    """Keep one row per Hit_ID. The pipeline emits one row per ON scan."""
    import pandas as pd

    frame = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)
    if "Hit_ID" not in frame.columns:
        frame = frame.copy()
        frame["Hit_ID"] = [
            f"{float(row.Freq):.6f}:{float(row.DriftRate):.6f}" for row in frame.itertuples()
        ]
    events: list[FilterEvent] = []
    for event_id, group in frame.groupby("Hit_ID", sort=False):
        best = group.loc[group["SNR"].idxmax()]
        events.append(
            FilterEvent(
                event_id=str(event_id),
                frequency_mhz=float(best["Freq"]),
                drift_hz_s=float(best["DriftRate"]),
                snr=float(best["SNR"]),
            )
        )
    return tuple(events)
