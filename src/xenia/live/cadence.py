"""Run the synthetic EXP-004 ABACAD cadence and write its manifest."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from xenia.live.cadence_models import CadenceRecovery, CadenceTruth, RecoveryRow, TruthInjection
from xenia.live.known_sources import KnownCatalog, load_known_sources
from xenia.live.models import (
    CadenceHit,
    CadencePayload,
    CadenceStatus,
    InputRef,
    RunManifest,
    Verdict,
)
from xenia.live.search import CadenceSearch, FilterEvent, ScanDetection, search_cadence
from xenia.live.state import sha256_file
from xenia.live.verdict import SYNTHETIC_EXPLANATION_PREFIX, VerdictDecision, decide_verdict
from xenia.provenance import create_run_manifest, new_run_id, output_ref
from xenia.radio.cadence_synth import (
    CADENCE_ROLES,
    OFF_SCAN_INDEXES,
    ON_SCAN_INDEXES,
    CadenceMode,
    InjectionTruth,
    ScanTruth,
    frequency_channels,
    scan_duration_seconds,
    write_cadence,
)
from xenia.radio.floor_config import FRAME_FCH1_MHZ, FREQUENCY_RESOLUTION_HZ

# Association windows stay narrower than the 3.9 kHz gap between injection slots.
FREQUENCY_MATCH_HZ = 500.0
DRIFT_MATCH_HZ_S = 0.15
_THUMB_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="320" height="140" role="img"
  aria-label="Synthetic cadence waterfall placeholder">
  <rect width="320" height="140" fill="#0D1320"/>
  <line x1="36" y1="118" x2="284" y2="22" stroke="#E7B15A" stroke-width="2"/>
</svg>
"""


@dataclass(frozen=True, slots=True)
class _Assigned:
    injection: InjectionTruth
    detections: tuple[ScanDetection, ...]
    passed_filter: bool
    frequency_error_hz: float
    drift_error_hz_s: float


def run_synthetic_cadence(
    repository_root: Path,
    command: list[str],
    *,
    seed: int,
    experiment_id: str,
    mode: str,
    known_sources_path: Path,
) -> tuple[RunManifest, Path]:
    """Generate, search, label, and record one synthetic ABACAD cadence.

    Inputs are recorded as synthetic:// URIs. Filterbank files are deleted
    after the search. demo stays false; the hit explanation says the cadence
    is synthetic.
    """
    if mode not in {"full", "reduced"}:
        raise ValueError("mode must be full or reduced")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    root = repository_root.resolve()
    catalog = load_known_sources(known_sources_path)
    started_at = datetime.now(UTC)
    work = root / "data" / "tmp" / f"exp-004-{seed}-{mode}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    cadence_mode: CadenceMode = "full" if mode == "full" else "reduced"
    try:
        scans, truths = write_cadence(work / "frames", seed=seed, mode=cadence_mode)
        search = search_cadence(scans, work_dir=work / "search")
        inputs = _inputs(scans, seed, mode)
        assigned, unassigned_detections, unassigned_events = _assign(truths, search)
        decisions = _decisions(assigned, catalog, cadence_id=f"exp-004-{seed}-{mode}")
        recovery = _recovery(decisions, unassigned_detections, unassigned_events)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    finished_at = datetime.now(UTC)
    run_id = new_run_id(started_at, "exp-004-cadence")
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    truth_path = run_dir / "truth.json"
    recovery_path = run_dir / "recovery.json"
    hits_path = run_dir / "hits.parquet"
    truth_document = _truth_document(seed, mode, truths)
    truth_path.write_text(truth_document.model_dump_json(indent=2) + "\n", encoding="utf-8")
    recovery_path.write_text(recovery.model_dump_json(indent=2) + "\n", encoding="utf-8")
    _write_hits(hits_path, decisions, finished_at)
    thumb_urls = _write_thumbs(run_dir, decisions)
    hits = _cadence_hits(decisions, finished_at, thumb_urls)
    payload = _payload(seed, cadence_mode, started_at, hits)
    outcome = (
        "searched_with_survivors"
        if any(hit.verdict is Verdict.ON_ONLY for hit in hits)
        else "searched"
    )
    notes = _notes(recovery, search, catalog)
    thumb_paths = tuple(run_dir / "thumbs" / f"{hit_id}.svg" for hit_id in thumb_urls)
    outputs = tuple(
        output_ref(path, repository_root=root)
        for path in (truth_path, recovery_path, hits_path, *thumb_paths)
    )
    manifest, manifest_path = create_run_manifest(
        run_id=run_id,
        command=command,
        parameters={
            "synthetic": True,
            "seed": seed,
            "mode": mode,
            "experiment_id": experiment_id,
            "roles": list(CADENCE_ROLES),
            "frequency_channels": frequency_channels(cadence_mode),
            "known_sources_sha256": sha256_file(known_sources_path),
            "filter_threshold": 3,
            "minimum_snr": 10.0,
            "max_drift_hz_s": 4.0,
        },
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
        mission_control=payload,
    )
    return manifest, manifest_path


def _assign(
    truths: tuple[InjectionTruth, ...], search: CadenceSearch
) -> tuple[tuple[_Assigned, ...], int, int]:
    groups: dict[str, list[ScanDetection]] = {item.injection_id: [] for item in truths}
    errors: dict[str, tuple[float, float]] = {item.injection_id: (0.0, 0.0) for item in truths}
    unassigned = 0
    for detection in search.detections:
        choice = _best_injection(detection, truths, scan_index=detection.scan_index)
        if choice is None:
            unassigned += 1
            continue
        injection, frequency_error, drift_error = choice
        groups[injection.injection_id].append(detection)
        errors[injection.injection_id] = (frequency_error, drift_error)
    passed: dict[str, bool] = {}
    unassigned_events = 0
    for event in search.events:
        choice = _best_injection_for_event(event, truths)
        if choice is None:
            unassigned_events += 1
            continue
        passed[choice.injection_id] = True
    assigned = tuple(
        _Assigned(
            injection=injection,
            detections=tuple(groups[injection.injection_id]),
            passed_filter=passed.get(injection.injection_id, False),
            frequency_error_hz=errors[injection.injection_id][0],
            drift_error_hz_s=errors[injection.injection_id][1],
        )
        for injection in truths
    )
    return assigned, unassigned, unassigned_events


def _best_injection(
    detection: ScanDetection, truths: tuple[InjectionTruth, ...], *, scan_index: int
) -> tuple[InjectionTruth, float, float] | None:
    best: tuple[InjectionTruth, float, float] | None = None
    for injection in truths:
        frequency_error = _scan_path_error_hz(injection, scan_index, detection.frequency_mhz)
        drift_error = abs(detection.drift_hz_s - injection.drift_hz_s)
        if frequency_error > FREQUENCY_MATCH_HZ or drift_error > DRIFT_MATCH_HZ_S:
            continue
        if best is None or (frequency_error, drift_error) < (best[1], best[2]):
            best = (injection, frequency_error, drift_error)
    return best


def _best_injection_for_event(
    event: FilterEvent, truths: tuple[InjectionTruth, ...]
) -> InjectionTruth | None:
    best: tuple[InjectionTruth, float, float] | None = None
    duration = scan_duration_seconds() * len(CADENCE_ROLES)
    for injection in truths:
        frequency_error = _interval_error_hz(
            injection.start_frequency_mhz * 1e6,
            injection.start_frequency_mhz * 1e6 + injection.drift_hz_s * duration,
            event.frequency_mhz * 1e6,
        )
        drift_error = abs(event.drift_hz_s - injection.drift_hz_s)
        if frequency_error > FREQUENCY_MATCH_HZ or drift_error > DRIFT_MATCH_HZ_S:
            continue
        if best is None or (frequency_error, drift_error) < (best[1], best[2]):
            best = (injection, frequency_error, drift_error)
    return None if best is None else best[0]


def _scan_path_error_hz(injection: InjectionTruth, scan_index: int, frequency_mhz: float) -> float:
    duration = scan_duration_seconds()
    start_hz = injection.frequency_mhz_at(scan_index * duration) * 1e6
    stop_hz = start_hz + injection.drift_hz_s * duration
    return _interval_error_hz(start_hz, stop_hz, frequency_mhz * 1e6)


def _interval_error_hz(start_hz: float, stop_hz: float, hit_hz: float) -> float:
    lower = min(start_hz, stop_hz)
    upper = max(start_hz, stop_hz)
    if hit_hz < lower:
        return lower - hit_hz
    if hit_hz > upper:
        return hit_hz - upper
    return 0.0


def _decisions(
    assigned: tuple[_Assigned, ...], catalog: KnownCatalog, *, cadence_id: str
) -> tuple[tuple[_Assigned, VerdictDecision | None], ...]:
    rows = []
    for item in assigned:
        if not item.detections:
            rows.append((item, None))
            continue
        best = max(item.detections, key=lambda detection: detection.snr)
        on_count = len(
            {hit.scan_index for hit in item.detections if hit.scan_index in ON_SCAN_INDEXES}
        )
        off_count = len(
            {hit.scan_index for hit in item.detections if hit.scan_index in OFF_SCAN_INDEXES}
        )
        decision = decide_verdict(
            frequency_mhz=best.frequency_mhz,
            drift_hz_s=best.drift_hz_s,
            on_count=on_count,
            off_count=off_count,
            passed_filter=item.passed_filter,
            catalog=catalog,
            session_hits=(),
            this_cadence_id=cadence_id,
            synthetic=True,
        )
        rows.append((item, decision))
    return tuple(rows)


def _recovery(
    decisions: tuple[tuple[_Assigned, VerdictDecision | None], ...],
    unassigned_detections: int,
    unassigned_events: int,
) -> CadenceRecovery:
    rows: list[RecoveryRow] = []
    for item, decision in decisions:
        truth = item.injection
        best = (
            max(item.detections, key=lambda detection: detection.snr) if item.detections else None
        )
        on_count = len(
            {hit.scan_index for hit in item.detections if hit.scan_index in ON_SCAN_INDEXES}
        )
        off_count = len(
            {hit.scan_index for hit in item.detections if hit.scan_index in OFF_SCAN_INDEXES}
        )
        assigned_verdict = None if decision is None else decision.verdict
        rows.append(
            RecoveryRow(
                injection_id=truth.injection_id,
                expected_verdict=Verdict(truth.expected_verdict),
                assigned_verdict=assigned_verdict,
                matched=assigned_verdict is not None
                and assigned_verdict.value == truth.expected_verdict,
                detected_frequency_mhz=None if best is None else best.frequency_mhz,
                detected_drift_hz_s=None if best is None else best.drift_hz_s,
                detected_snr=None if best is None else best.snr,
                on_count=on_count,
                off_count=off_count,
                passed_filter=item.passed_filter,
                frequency_error_hz=None if best is None else item.frequency_error_hz,
                drift_error_hz_s=None if best is None else item.drift_error_hz_s,
            )
        )
    return CadenceRecovery(
        rows=tuple(rows),
        unassigned_detection_count=unassigned_detections,
        unassigned_event_count=unassigned_events,
        all_matched=all(row.matched for row in rows),
    )


def _truth_document(seed: int, mode: str, truths: tuple[InjectionTruth, ...]) -> CadenceTruth:
    return CadenceTruth(
        seed=seed,
        mode=mode,
        roles=CADENCE_ROLES,
        injections=tuple(
            TruthInjection(
                injection_id=item.injection_id,
                expected_verdict=Verdict(item.expected_verdict),
                channel_index=item.channel_index,
                start_frequency_mhz=item.start_frequency_mhz,
                drift_hz_s=item.drift_hz_s,
                snr=item.snr,
                present_scan_indexes=item.present_scan_indexes,
            )
            for item in truths
        ),
    )


def _write_hits(
    path: Path,
    decisions: tuple[tuple[_Assigned, VerdictDecision | None], ...],
    found_at: datetime,
) -> None:
    try:
        import polars as pl
    except ImportError as exc:  # pragma: no cover - radio extra installation failure
        raise RuntimeError("hits.parquet requires polars from the radio extra") from exc

    records: list[dict[str, object]] = []
    for item, decision in decisions:
        if decision is None:
            continue
        best = max(item.detections, key=lambda detection: detection.snr)
        checks = {check.name: check for check in decision.checks}
        row: dict[str, object] = {
            "hit_id": f"exp004-{item.injection.injection_id}",
            "injection_id": item.injection.injection_id,
            "freq_mhz": best.frequency_mhz,
            "drift_hz_s": best.drift_hz_s,
            "snr": best.snr,
            "verdict": decision.verdict.value,
            "explanation": decision.explanation,
            "checks_done": decision.checks_done,
            "known_source": decision.known_source,
            "found_at": found_at.isoformat(),
        }
        for name in (
            "not_in_off",
            "not_known_transmitter",
            "drift_sane",
            "session_census_clear",
            "review",
        ):
            row[name] = checks[name].passed
            row[f"note_{name}"] = checks[name].note
        records.append(row)
    if not records:
        raise ValueError("synthetic cadence produced no matched hits")
    pl.DataFrame(records).write_parquet(path)


def _write_thumbs(
    run_dir: Path, decisions: tuple[tuple[_Assigned, VerdictDecision | None], ...]
) -> dict[str, str]:
    thumb_dir = run_dir / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    urls: dict[str, str] = {}
    for item, decision in decisions:
        if decision is None:
            continue
        hit_id = f"exp004-{item.injection.injection_id}"
        relative = f"runs/{run_dir.name}/thumbs/{hit_id}.svg"
        (run_dir / "thumbs" / f"{hit_id}.svg").write_text(_THUMB_SVG, encoding="utf-8")
        urls[hit_id] = relative
    return urls


def _cadence_hits(
    decisions: tuple[tuple[_Assigned, VerdictDecision | None], ...],
    found_at: datetime,
    thumb_urls: dict[str, str],
) -> tuple[CadenceHit, ...]:
    hits: list[CadenceHit] = []
    for item, decision in decisions:
        if decision is None:
            continue
        best = max(item.detections, key=lambda detection: detection.snr)
        hit_id = f"exp004-{item.injection.injection_id}"
        if SYNTHETIC_EXPLANATION_PREFIX not in decision.explanation:
            raise RuntimeError("synthetic cadence explanations must say the cadence is synthetic")
        hits.append(
            CadenceHit(
                hit_id=hit_id,
                found_at=found_at,
                freq_mhz=best.frequency_mhz,
                drift_hz_s=best.drift_hz_s,
                snr=best.snr,
                verdict=decision.verdict,
                explanation=decision.explanation,
                checks_done=decision.checks_done,
                known_source=decision.known_source,
                thumbnail_url=thumb_urls[hit_id],
                plot_url=None,
                review_signoffs=(),
            )
        )
    return tuple(hits)


def _payload(
    seed: int,
    mode: CadenceMode,
    started_at: datetime,
    hits: tuple[CadenceHit, ...],
) -> CadencePayload:
    nchans = frequency_channels(mode)
    low_mhz = FRAME_FCH1_MHZ - nchans * FREQUENCY_RESOLUTION_HZ / 1e6
    return CadencePayload(
        kind="cadence",
        cadence_id=f"exp-004-{seed}-{mode}",
        target="Synthetic ABACAD",
        ra_deg=0.0,
        dec_deg=0.0,
        status=CadenceStatus.DONE,
        windows_done=1,
        window_mhz=(low_mhz, FRAME_FCH1_MHZ),
        on_source_seconds=3 * scan_duration_seconds(),
        started_at=started_at,
        hits=hits,
    )


def _notes(
    recovery: CadenceRecovery, search: CadenceSearch, catalog: KnownCatalog
) -> tuple[str, ...]:
    counts: dict[str, int] = {}
    for row in recovery.rows:
        label = "undetected" if row.assigned_verdict is None else row.assigned_verdict.value
        counts[label] = counts.get(label, 0) + 1
    summary = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    return (
        "Synthetic setigen ABACAD cadence. Not a telescope observation. demo is false.",
        f"Verdict counts: {summary}.",
        f"Unassigned detections: {recovery.unassigned_detection_count}. "
        f"Unassigned filter-3 events: {recovery.unassigned_event_count}.",
        f"Filter-3 events retained: {len(search.events)}. "
        f"Known-source ranges loaded: {len(catalog.ranges)}.",
        *(search.warnings[:4]),
    )


def _inputs(scans: tuple[ScanTruth, ...], seed: int, mode: str) -> tuple[InputRef, ...]:
    refs: list[InputRef] = []
    for scan in scans:
        refs.append(
            InputRef(
                uri=f"synthetic://exp-004/{mode}/seed-{seed}/scan-{scan.scan_index}-{scan.role}",
                sha256=sha256_file(scan.path),
                size_bytes=scan.path.stat().st_size,
            )
        )
    return tuple(refs)
