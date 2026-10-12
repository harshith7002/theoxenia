"""Validated data contracts for run manifests and the Mission Control page."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from math import isclose, isfinite
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from xenia.radio.floor_config import (
    FULL_DRIFT_GRID,
    FULL_SNR_GRID,
    FULL_TRIALS_PER_CELL,
    REDUCED_DRIFT_GRID,
    REDUCED_SNR_GRID,
    REDUCED_TRIALS_PER_CELL,
)


class StrictModel(BaseModel):
    """Base model that rejects unknown input fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _validate_relative_url(value: str) -> str:
    """Reject absolute URLs and path traversal for site-local assets."""
    if not value or "\\" in value or value.startswith(("/", "//")):
        raise ValueError("asset URL must be a non-empty site-relative path")
    if "://" in value:
        raise ValueError("asset URL must not contain a URL scheme")
    path = PurePosixPath(value)
    if ".." in path.parts or "." in path.parts:
        raise ValueError("asset URL must not traverse directories")
    return value


def _validate_aware_datetime(value: datetime) -> datetime:
    """Require timestamps to carry an explicit timezone."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value


def _validate_https_url(value: str | None) -> str | None:
    """Require optional external links to use an absolute HTTPS URL."""
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("external links must be absolute HTTPS URLs")
    return value


class WorkerStatus(StrEnum):
    """Publicly displayed worker states."""

    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class CadenceStatus(StrEnum):
    """Queue status for a (cadence, window) search pair."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Verdict(StrEnum):
    """Mechanical, prosaic-first public verdict taxonomy."""

    KNOWN_SOURCE = "KNOWN_SOURCE"
    IN_OFF = "IN_OFF"
    SINGLE_POINTING = "SINGLE_POINTING"
    RFI_CENSUS = "RFI_CENSUS"
    ON_ONLY = "ON_ONLY"
    UNEXPLAINED = "UNEXPLAINED"


class ArtifactRef(StrictModel):
    """Small output artifact recorded in a run manifest."""

    path: str = Field(min_length=1)
    sha256: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    media_type: str | None = None

    @field_validator("path")
    @classmethod
    def path_is_relative(cls, value: str) -> str:
        if "\\" in value or value.startswith("/") or ".." in PurePosixPath(value).parts:
            raise ValueError("artifact path must be relative and may not traverse directories")
        return value

    @field_validator("sha256")
    @classmethod
    def checksum_is_sha256(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("sha256 must contain exactly 64 lowercase hexadecimal characters")
        return value


class InputRef(StrictModel):
    """Source URI and optional checksum for one run input."""

    uri: str = Field(min_length=1)
    sha256: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)

    @field_validator("sha256")
    @classmethod
    def checksum_is_sha256(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("sha256 must contain exactly 64 lowercase hexadecimal characters")
        return value


class ReviewSignoff(StrictModel):
    """Explicit human review attached to a future unexplained verdict."""

    reviewer: Literal["claude", "michael"]
    signed_at: datetime
    note: str = Field(min_length=1)

    @field_validator("signed_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)


class CurrentSearch(StrictModel):
    """Worker ticker data for the cadence currently being processed."""

    cadence_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    ra_deg: float = Field(ge=0, le=360)
    dec_deg: float = Field(ge=-90, le=90)
    receiver: str = Field(min_length=1)
    window_mhz: tuple[float, float]
    scan_index: int = Field(ge=1)
    scan_count: int = Field(ge=1)
    started_at: datetime

    @field_validator("started_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)

    @model_validator(mode="after")
    def validate_window_and_scans(self) -> CurrentSearch:
        if self.window_mhz[0] >= self.window_mhz[1]:
            raise ValueError("window_mhz must be an increasing pair")
        if self.scan_index > self.scan_count:
            raise ValueError("scan_index cannot exceed scan_count")
        return self


class NextSearch(StrictModel):
    """Next queued cadence shown while the worker is idle."""

    cadence_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    eta: datetime | None = None

    @field_validator("eta")
    @classmethod
    def timestamp_is_aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _validate_aware_datetime(value)


class WorkerPayload(StrictModel):
    """Heartbeat snapshot stored in a run manifest."""

    kind: Literal["worker"]
    status: WorkerStatus
    last_heartbeat: datetime | None
    host: str = Field(min_length=1)
    current: CurrentSearch | None = None
    next: NextSearch | None = None

    @field_validator("last_heartbeat")
    @classmethod
    def timestamp_is_aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _validate_aware_datetime(value)


class CadenceHit(StrictModel):
    """One hit entry recorded with its cadence manifest."""

    hit_id: str = Field(min_length=1)
    found_at: datetime
    freq_mhz: float = Field(gt=0)
    drift_hz_s: float
    snr: float = Field(ge=0)
    verdict: Verdict
    explanation: str = Field(min_length=1)
    checks_done: int = Field(default=0, ge=0, le=5)
    known_source: str | None = None
    thumbnail_url: str
    plot_url: str | None = None
    review_signoffs: tuple[ReviewSignoff, ...] = ()

    @field_validator("found_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)

    @field_validator("thumbnail_url", "plot_url")
    @classmethod
    def asset_urls_are_relative(cls, value: str | None) -> str | None:
        return None if value is None else _validate_relative_url(value)

    @model_validator(mode="after")
    def require_signoff_for_unexplained(self) -> CadenceHit:
        if self.verdict is Verdict.UNEXPLAINED:
            reviewers = {signoff.reviewer for signoff in self.review_signoffs}
            if self.checks_done != 5 or not {"claude", "michael"}.issubset(reviewers):
                raise ValueError(
                    "UNEXPLAINED requires all five checks and sign-off from Claude and Michael"
                )
        return self


class CadencePayload(StrictModel):
    """Completed or queued (cadence, window) snapshot."""

    kind: Literal["cadence"]
    cadence_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    ra_deg: float = Field(ge=0, le=360)
    dec_deg: float = Field(ge=-90, le=90)
    status: CadenceStatus
    windows_done: int = Field(ge=0)
    window_mhz: tuple[float, float]
    on_source_seconds: float = Field(default=0, ge=0)
    started_at: datetime
    hits: tuple[CadenceHit, ...] = ()

    @field_validator("started_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)

    @model_validator(mode="after")
    def validate_window_and_completion(self) -> CadencePayload:
        if self.window_mhz[0] >= self.window_mhz[1]:
            raise ValueError("window_mhz must be an increasing pair")
        if self.status is CadenceStatus.FAILED and self.windows_done != 0:
            raise ValueError("failed cadence payloads cannot report completed windows")
        return self


class HeroPayload(StrictModel):
    """Manifest-backed Voyager hero; absent until EXP-001 runs."""

    kind: Literal["hero"]
    experiment: Literal["EXP-001"]
    run_id: str = Field(min_length=1)
    image_url: str
    freq_mhz: float = Field(gt=0)
    drift_hz_s: float
    snr: float = Field(ge=0)

    @field_validator("image_url")
    @classmethod
    def image_url_is_relative(cls, value: str) -> str:
        return _validate_relative_url(value)


class FloorPayload(StrictModel):
    """Manifest-backed injection recovery floor; absent until EXP-002."""

    kind: Literal["detection_floor"]
    experiment: Literal["EXP-002"]
    snr_grid: tuple[float, ...] = Field(min_length=1)
    drift_grid: tuple[float, ...] = Field(min_length=1)
    trials_per_cell: int = Field(gt=0)
    recovered_fraction: tuple[tuple[float, ...], ...]
    ci_run_url: str | None = None

    @field_validator("ci_run_url")
    @classmethod
    def ci_link_is_https(cls, value: str | None) -> str | None:
        return _validate_https_url(value)

    @model_validator(mode="after")
    def validate_grid_shape(self) -> FloorPayload:
        if len(self.recovered_fraction) != len(self.snr_grid):
            raise ValueError("recovered_fraction rows must match snr_grid")
        if any(len(row) != len(self.drift_grid) for row in self.recovered_fraction):
            raise ValueError("recovered_fraction columns must match drift_grid")
        if any(not 0 <= value <= 1 for row in self.recovered_fraction for value in row):
            raise ValueError("recovered fractions must be between zero and one")
        return self


class FloorDetectedHit(StrictModel):
    """Small, typed subset of one turboSETI top-hit row."""

    top_hit: int = Field(ge=1)
    drift_hz_s: float = Field(allow_inf_nan=False)
    snr: float = Field(ge=0, allow_inf_nan=False)
    uncorrected_frequency_mhz: float = Field(gt=0, allow_inf_nan=False)
    corrected_frequency_mhz: float = Field(gt=0, allow_inf_nan=False)
    frequency_start_mhz: float = Field(gt=0, allow_inf_nan=False)
    frequency_end_mhz: float = Field(gt=0, allow_inf_nan=False)


class FloorDetectorArtifact(StrictModel):
    """Checksum record for a temporary turboSETI output table."""

    filename: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)

    @field_validator("filename")
    @classmethod
    def filename_is_local(cls, value: str) -> str:
        if "\\" in value or PurePosixPath(value).name != value:
            raise ValueError("detector artifact filename must be a local basename")
        return value


class FloorSearchTrial(StrictModel):
    """One seeded synthetic frame and its complete parsed detector output."""

    trial_index: int = Field(ge=1)
    seed: int = Field(ge=0)
    injected_signal_count: int = Field(ge=1)
    detected_hits: tuple[FloorDetectedHit, ...] = ()
    detector_artifacts: tuple[FloorDetectorArtifact, ...] = ()
    warnings: tuple[str, ...] = ()


class RecoveryMeasurement(StrictModel):
    """One injected signal’s deterministic recovery decision and matched hit."""

    snr: float = Field(gt=0, allow_inf_nan=False)
    drift_hz_s: float = Field(allow_inf_nan=False)
    trial_index: int = Field(ge=1)
    seed: int = Field(ge=0)
    frequency_mhz: float = Field(gt=0, allow_inf_nan=False)
    injected_start_frequency_mhz: float = Field(gt=0, allow_inf_nan=False)
    recovered: bool
    matched_hit: FloorDetectedHit | None = None
    frequency_error_hz: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    drift_error_hz_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def match_fields_follow_recovery(self) -> RecoveryMeasurement:
        has_match = self.matched_hit is not None
        has_errors = self.frequency_error_hz is not None and self.drift_error_hz_s is not None
        if self.recovered != has_match or self.recovered != has_errors:
            raise ValueError("recovered measurements must include a matched hit and both errors")
        if not self.recovered and (
            self.frequency_error_hz is not None or self.drift_error_hz_s is not None
        ):
            raise ValueError("unrecovered measurements cannot report match errors")
        return self


class RecoveryGridArtifact(StrictModel):
    """Schema-validated synthetic EXP-002 per-trial recovery artifact."""

    schema_version: Literal["0.1"] = "0.1"
    source_kind: Literal["synthetic_setigen"] = "synthetic_setigen"
    run_id: str = Field(min_length=1)
    experiment_id: Literal["EXP-002"] = "EXP-002"
    mode: Literal["full", "reduced"]
    seed: int = Field(ge=0)
    snr_grid: tuple[float, ...] = Field(min_length=1)
    drift_grid: tuple[float, ...] = Field(min_length=1)
    trials_per_cell: int = Field(gt=0)
    max_abs_drift_hz_s: float = Field(gt=0, allow_inf_nan=False)
    detector_snr_threshold: float = Field(ge=0, allow_inf_nan=False)
    frequency_tolerance_hz: float = Field(gt=0, allow_inf_nan=False)
    drift_tolerance_hz_s: float = Field(gt=0, allow_inf_nan=False)
    frequency_channels: int = Field(ge=2)
    time_channels: int = Field(ge=2)
    frame_bandwidth_hz: float = Field(gt=0, allow_inf_nan=False)
    frequency_resolution_hz: float = Field(gt=0, allow_inf_nan=False)
    time_resolution_seconds: float = Field(gt=0, allow_inf_nan=False)
    frame_center_frequency_mhz: float = Field(gt=0, allow_inf_nan=False)
    frequency_slot_spacing_hz: float = Field(gt=0, allow_inf_nan=False)
    signal_width_hz: float = Field(gt=0, allow_inf_nan=False)
    noise_distribution: Literal["chi2"] = "chi2"
    noise_mean: float = Field(gt=0, allow_inf_nan=False)
    ci_run_url: str | None = None
    runtime_versions: dict[str, str] = Field(min_length=1)
    searches: tuple[FloorSearchTrial, ...] = Field(min_length=1)
    measurements: tuple[RecoveryMeasurement, ...] = Field(min_length=1)
    recovered_count: tuple[tuple[int, ...], ...]
    recovered_fraction: tuple[tuple[float, ...], ...]

    @field_validator("ci_run_url")
    @classmethod
    def ci_link_is_https(cls, value: str | None) -> str | None:
        return _validate_https_url(value)

    @model_validator(mode="after")
    def validate_grid_results(self) -> RecoveryGridArtifact:
        expected_snr, expected_drift, expected_trials = (
            (FULL_SNR_GRID, FULL_DRIFT_GRID, FULL_TRIALS_PER_CELL)
            if self.mode == "full"
            else (REDUCED_SNR_GRID, REDUCED_DRIFT_GRID, REDUCED_TRIALS_PER_CELL)
        )
        if (self.snr_grid, self.drift_grid, self.trials_per_cell) != (
            expected_snr,
            expected_drift,
            expected_trials,
        ):
            raise ValueError("grid axes and trial count do not match the declared mode")
        if any(not isfinite(value) for value in (*self.snr_grid, *self.drift_grid)):
            raise ValueError("grid values must be finite")
        if tuple(sorted(set(self.snr_grid))) != self.snr_grid:
            raise ValueError("snr_grid must be strictly increasing and contain no duplicates")
        if tuple(sorted(set(self.drift_grid))) != self.drift_grid:
            raise ValueError("drift_grid must be strictly increasing and contain no duplicates")
        if max(abs(value) for value in self.drift_grid) > self.max_abs_drift_hz_s:
            raise ValueError("max_abs_drift_hz_s must cover every configured drift")
        expected_shape = (len(self.snr_grid), len(self.drift_grid))
        for name, matrix in (
            ("recovered_count", self.recovered_count),
            ("recovered_fraction", self.recovered_fraction),
        ):
            if len(matrix) != expected_shape[0] or any(
                len(row) != expected_shape[1] for row in matrix
            ):
                raise ValueError(f"{name} must match the SNR-by-drift grid shape")

        if len(self.searches) != self.trials_per_cell:
            raise ValueError("there must be one detector search per independent trial")
        search_by_index = {search.trial_index: search for search in self.searches}
        if set(search_by_index) != set(range(1, self.trials_per_cell + 1)):
            raise ValueError("detector search trial indices must cover each trial exactly once")
        signals_per_trial = len(self.snr_grid) * len(self.drift_grid)
        for search in self.searches:
            if search.seed != self.seed + search.trial_index - 1:
                raise ValueError("search seeds must be consecutive from the artifact seed")
            if search.injected_signal_count != signals_per_trial:
                raise ValueError("each search must contain one signal for every grid cell")

        expected_measurements = signals_per_trial * self.trials_per_cell
        if len(self.measurements) != expected_measurements:
            raise ValueError("measurement count must equal SNR × drift × trials_per_cell")
        observed_keys: set[tuple[float, float, int]] = set()
        matched_hit_keys: set[tuple[int, int]] = set()
        counts = [[0 for _ in self.drift_grid] for _ in self.snr_grid]
        snr_indices = {value: index for index, value in enumerate(self.snr_grid)}
        drift_indices = {value: index for index, value in enumerate(self.drift_grid)}
        for measurement in self.measurements:
            if measurement.snr not in snr_indices or measurement.drift_hz_s not in drift_indices:
                raise ValueError("measurement coordinates must exist in the configured grid")
            matched_search = search_by_index.get(measurement.trial_index)
            if matched_search is None or matched_search.seed != measurement.seed:
                raise ValueError("measurement seed and trial must match a detector search")
            key = (measurement.snr, measurement.drift_hz_s, measurement.trial_index)
            if key in observed_keys:
                raise ValueError("grid contains a duplicate SNR/drift/trial measurement")
            observed_keys.add(key)
            row_index = snr_indices[measurement.snr]
            column_index = drift_indices[measurement.drift_hz_s]
            if measurement.recovered:
                counts[row_index][column_index] += 1
                hit = measurement.matched_hit
                if hit is None:
                    raise ValueError("recovered measurement is missing its matched hit")
                hit_key = (measurement.trial_index, hit.top_hit)
                if hit_key in matched_hit_keys:
                    raise ValueError("one detector hit cannot recover multiple injected signals")
                matched_hit_keys.add(hit_key)
                if hit not in matched_search.detected_hits:
                    raise ValueError("matched hit must be present in the same trial's output")

        for row_index, row in enumerate(counts):
            for column_index, count in enumerate(row):
                if count != self.recovered_count[row_index][column_index]:
                    raise ValueError("recovered_count does not match per-trial measurements")
                expected_fraction = count / self.trials_per_cell
                if not isclose(
                    expected_fraction,
                    self.recovered_fraction[row_index][column_index],
                    rel_tol=0,
                    abs_tol=1e-12,
                ):
                    raise ValueError("recovered_fraction does not match per-trial measurements")
        return self


type ManifestPayload = Annotated[
    WorkerPayload | CadencePayload | HeroPayload | FloorPayload,
    Field(discriminator="kind"),
]


class RunManifest(StrictModel):
    """Provenance record for any result-producing project command."""

    schema_version: Literal["0.1"] = "0.1"
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
    pillar: str = Field(min_length=1)
    command: str = Field(min_length=1)
    parameters: dict[str, object] = Field(default_factory=dict)
    inputs: tuple[InputRef, ...] = ()
    outputs: tuple[ArtifactRef, ...] = ()
    git_sha: str = Field(min_length=1)
    package_version: str = Field(min_length=1)
    started_at: datetime
    finished_at: datetime
    outcome: str = Field(min_length=1)
    notes: tuple[str, ...] = ()
    experiment_id: str | None = None
    demo: bool = False
    mission_control: ManifestPayload | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def timestamps_are_aware(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)

    @model_validator(mode="after")
    def finish_follows_start(self) -> RunManifest:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self


class SiteMeta(StrictModel):
    """Static page metadata and publishing state."""

    demo: bool
    repo_url: str
    mirror_url: str | None = None
    data_credit: str
    is_mirror: bool = False
    mirror_updated_at: datetime | None = None

    @field_validator("repo_url", "mirror_url")
    @classmethod
    def public_urls_are_https(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("public URLs must use HTTPS")
        return value

    @field_validator("mirror_updated_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _validate_aware_datetime(value)


class WorkerState(StrictModel):
    """Worker information consumed by the status pill and ticker."""

    status: WorkerStatus
    last_heartbeat: datetime | None
    host: str
    current: CurrentSearch | None = None
    next: NextSearch | None = None

    @field_validator("last_heartbeat")
    @classmethod
    def timestamp_is_aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _validate_aware_datetime(value)


class Totals(StrictModel):
    """Aggregate counts derived from the run manifests."""

    cadences_searched: int = Field(ge=0)
    windows_searched: int = Field(ge=0)
    mhz_hours_on_target: float = Field(ge=0)
    hits: int = Field(ge=0)
    known_source: int = Field(ge=0)
    in_off: int = Field(ge=0)
    single_pointing: int = Field(ge=0)
    rfi_census: int = Field(ge=0)
    survivors: int = Field(ge=0)
    unexplained: int = Field(ge=0)
    targets_distinct: int = Field(ge=0)
    failed: int = Field(ge=0)

    @model_validator(mode="after")
    def verdicts_sum_to_hits(self) -> Totals:
        verdict_total = (
            self.known_source
            + self.in_off
            + self.single_pointing
            + self.rfi_census
            + self.survivors
            + self.unexplained
        )
        if verdict_total != self.hits:
            raise ValueError("verdict totals must sum to hits")
        return self


class Pointing(StrictModel):
    """One sky-map point with a direct provenance link."""

    cadence_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    ra_deg: float = Field(ge=0, le=360)
    dec_deg: float = Field(ge=-90, le=90)
    status: CadenceStatus
    windows_done: int = Field(ge=0)
    hits: int = Field(ge=0)
    survivors: int = Field(ge=0)
    started_at: datetime
    manifest_url: str

    @field_validator("started_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)

    @field_validator("manifest_url")
    @classmethod
    def manifest_link_is_relative(cls, value: str) -> str:
        return _validate_relative_url(value)


class VoyagerHero(StrictModel):
    """Manifest-backed known-answer-test details."""

    kind: Literal["voyager1"] = "voyager1"
    image_url: str
    freq_mhz: float = Field(gt=0)
    drift_hz_s: float
    snr: float = Field(ge=0)
    run_id: str = Field(min_length=1)
    manifest_url: str
    experiment: Literal["EXP-001"] = "EXP-001"

    @field_validator("image_url", "manifest_url")
    @classmethod
    def asset_urls_are_relative(cls, value: str) -> str:
        return _validate_relative_url(value)


class DetectionFloor(StrictModel):
    """Manifest-backed sensitivity grid, added by EXP-002."""

    run_id: str = Field(min_length=1)
    experiment: Literal["EXP-002"] = "EXP-002"
    snr_grid: tuple[float, ...] = Field(min_length=1)
    drift_grid: tuple[float, ...] = Field(min_length=1)
    trials_per_cell: int = Field(gt=0)
    recovered_fraction: tuple[tuple[float, ...], ...]
    summary: str = Field(min_length=1)
    manifest_url: str
    ci_run_url: str | None = None

    @field_validator("ci_run_url")
    @classmethod
    def ci_link_is_https(cls, value: str | None) -> str | None:
        return _validate_https_url(value)

    @field_validator("manifest_url")
    @classmethod
    def manifest_link_is_relative(cls, value: str) -> str:
        return _validate_relative_url(value)

    @model_validator(mode="after")
    def validate_grid_shape(self) -> DetectionFloor:
        if len(self.recovered_fraction) != len(self.snr_grid):
            raise ValueError("recovered_fraction rows must match snr_grid")
        if any(len(row) != len(self.drift_grid) for row in self.recovered_fraction):
            raise ValueError("recovered_fraction columns must match drift_grid")
        if any(not 0 <= value <= 1 for row in self.recovered_fraction for value in row):
            raise ValueError("recovered fractions must be between zero and one")
        return self


class GalleryItem(StrictModel):
    """Page card for one hit, with manifest and plot references."""

    hit_id: str = Field(min_length=1)
    cadence_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    freq_mhz: float = Field(gt=0)
    drift_hz_s: float
    snr: float = Field(ge=0)
    verdict: Verdict
    badge_text: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    checks_done: int = Field(ge=0, le=5)
    thumbnail_url: str
    plot_url: str | None = None
    manifest_url: str
    found_at: datetime

    @field_validator("thumbnail_url", "plot_url", "manifest_url")
    @classmethod
    def asset_urls_are_relative(cls, value: str | None) -> str | None:
        return None if value is None else _validate_relative_url(value)

    @field_validator("found_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)


class LogEntry(StrictModel):
    """Compact status log entry, retained for diagnostics."""

    ts: datetime
    level: Literal["info", "warn", "error"]
    msg: str = Field(min_length=1)

    @field_validator("ts")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)


class LiveState(StrictModel):
    """Complete state document used to render Mission Control."""

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    git_sha: str = Field(min_length=1)
    package_version: str = Field(min_length=1)
    meta: SiteMeta
    worker: WorkerState
    totals: Totals
    hero: VoyagerHero | None = None
    detection_floor: DetectionFloor | None = None
    pointings: tuple[Pointing, ...] = ()
    gallery: tuple[GalleryItem, ...] = ()
    log: tuple[LogEntry, ...] = ()

    @field_validator("generated_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)
