"""Validated data contracts for run manifests and the Mission Control page."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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

    @model_validator(mode="after")
    def validate_grid_shape(self) -> FloorPayload:
        if len(self.recovered_fraction) != len(self.snr_grid):
            raise ValueError("recovered_fraction rows must match snr_grid")
        if any(len(row) != len(self.drift_grid) for row in self.recovered_fraction):
            raise ValueError("recovered_fraction columns must match drift_grid")
        if any(not 0 <= value <= 1 for row in self.recovered_fraction for value in row):
            raise ValueError("recovered fractions must be between zero and one")
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
