"""JSON records written beside an EXP-004 cadence manifest."""

from __future__ import annotations

from pydantic import Field

from xenia.live.models import StrictModel, Verdict


class TruthInjection(StrictModel):
    """One planted line and the verdict the fixture expects."""

    injection_id: str = Field(min_length=1)
    expected_verdict: Verdict
    channel_index: int = Field(ge=0)
    start_frequency_mhz: float = Field(gt=0)
    drift_hz_s: float
    snr: float = Field(gt=0)
    present_scan_indexes: tuple[int, ...]


class CadenceTruth(StrictModel):
    """The known-answer table for one synthetic cadence."""

    seed: int = Field(ge=0)
    mode: str = Field(min_length=1)
    roles: tuple[str, ...]
    injections: tuple[TruthInjection, ...]


class RecoveryRow(StrictModel):
    """Expected versus assigned verdict for one injection."""

    injection_id: str = Field(min_length=1)
    expected_verdict: Verdict
    assigned_verdict: Verdict | None
    matched: bool
    detected_frequency_mhz: float | None = None
    detected_drift_hz_s: float | None = None
    detected_snr: float | None = None
    on_count: int = Field(ge=0)
    off_count: int = Field(ge=0)
    passed_filter: bool
    frequency_error_hz: float | None = None
    drift_error_hz_s: float | None = None


class CadenceRecovery(StrictModel):
    """Per-injection recovery plus detections that matched no injection."""

    rows: tuple[RecoveryRow, ...]
    unassigned_detection_count: int = Field(ge=0)
    unassigned_event_count: int = Field(ge=0)
    all_matched: bool
