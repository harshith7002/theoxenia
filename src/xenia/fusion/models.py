"""Pydantic contract for one EXP-020 public-record baseline."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from xenia.live.models import StrictModel, _validate_aware_datetime, _validate_https_url


class FusionBaseline(StrictModel):
    """Measured CNEOS fireball count and GFZ Kp for one time window.

    The fireball request is the time window only. ``radius_km`` is recorded and
    is not sent to the API. ``kp_max`` is the planetary index, not a local value.
    """

    schema_version: Literal["0.1"] = "0.1"
    lat_deg: float = Field(ge=-90, le=90)
    lon_deg: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0)
    start: datetime
    end: datetime
    fireball_count_raw: str = Field(min_length=1)
    fireball_count: int = Field(ge=0)
    fireball_count_json_type: Literal["string", "integer"]
    fireball_request_limited_to_radius: Literal[False] = False
    kp_max: float
    kp_values: tuple[float, ...] = Field(min_length=1)
    kp_times: tuple[str, ...] = Field(min_length=1)
    kp_is_planetary: Literal[True] = True
    space_track_queried: Literal[False] = False
    cneos_url: str
    cneos_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cneos_bytes: int = Field(ge=0)
    cneos_http_status: int | None = None
    cneos_via: Literal["urllib", "curl", "recorded_response"]
    cneos_numbers_from: Literal["live", "recorded_response"]
    gfz_url: str
    gfz_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gfz_bytes: int = Field(ge=0)
    gfz_http_status: int | None = None
    gfz_via: Literal["urllib", "curl", "recorded_response"]
    gfz_numbers_from: Literal["live", "recorded_response"]
    notes: tuple[str, ...] = ()

    @field_validator("start", "end")
    @classmethod
    def timestamps_are_aware(cls, value: datetime) -> datetime:
        return _validate_aware_datetime(value)

    @field_validator("cneos_url", "gfz_url")
    @classmethod
    def urls_are_https(cls, value: str) -> str:
        checked = _validate_https_url(value)
        if checked is None:
            raise ValueError("source URL is required")
        return checked

    @model_validator(mode="after")
    def measurements_agree(self) -> FusionBaseline:
        if self.end < self.start:
            raise ValueError("end must not precede start")
        if self.fireball_count != int(self.fireball_count_raw):
            raise ValueError("fireball_count does not match fireball_count_raw")
        if len(self.kp_values) != len(self.kp_times):
            raise ValueError("Kp values and times differ in length")
        if self.kp_max != max(self.kp_values):
            raise ValueError("kp_max is not the maximum of kp_values")
        if self.cneos_numbers_from == "live" and self.cneos_via == "recorded_response":
            raise ValueError("a live CNEOS count cannot cite the recorded body")
        if self.cneos_numbers_from == "recorded_response" and self.cneos_via != "recorded_response":
            raise ValueError("a recorded CNEOS count must cite the recorded body")
        if self.gfz_numbers_from == "live" and self.gfz_via == "recorded_response":
            raise ValueError("a live Kp series cannot cite the recorded body")
        if self.gfz_numbers_from == "recorded_response" and self.gfz_via != "recorded_response":
            raise ValueError("a recorded Kp series must cite the recorded body")
        return self
