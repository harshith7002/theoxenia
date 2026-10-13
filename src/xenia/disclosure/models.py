"""Re-derived page-text contract for one OCR'd case file.

The fields are the ones this command measures: source identity, page text, and
an optional character error rate against a hand-checked reference. Dates and
places stay null unless a reference file supplies them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from xenia.live.models import StrictModel, _validate_https_url


class PageTranscript(StrictModel):
    """One page of OCR text, with an optional hand-checked comparison."""

    page_index: int = Field(ge=1)
    text: str
    reference_text: str | None = None
    character_error_rate: float | None = Field(default=None, ge=0)
    levenshtein: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def rate_requires_a_reference(self) -> PageTranscript:
        has_rate = self.character_error_rate is not None or self.levenshtein is not None
        if has_rate and self.reference_text is None:
            raise ValueError("a character error rate requires reference text")
        if (self.character_error_rate is None) != (self.levenshtein is None):
            raise ValueError("character error rate and levenshtein are recorded together")
        return self


class IncidentTelemetry(StrictModel):
    """OCR output for one PDF. This is not a filled incident conclusion."""

    schema_version: Literal["0.1"] = "0.1"
    source_url: str | None = None
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_bytes: int = Field(ge=0)
    page_count: int = Field(ge=1)
    pages_processed: int = Field(ge=0)
    case_date: str | None = None
    location: str | None = None
    tesseract_version: str = Field(min_length=1)
    pages: tuple[PageTranscript, ...]
    notes: tuple[str, ...] = ()

    @field_validator("source_url")
    @classmethod
    def url_is_https(cls, value: str | None) -> str | None:
        return _validate_https_url(value)

    @model_validator(mode="after")
    def pages_match_the_count(self) -> IncidentTelemetry:
        if self.pages_processed != len(self.pages):
            raise ValueError("pages_processed does not match the page list")
        if self.page_count != len(self.pages):
            raise ValueError("page_count does not match the page list")
        indexes = [page.page_index for page in self.pages]
        if indexes != list(range(1, len(self.pages) + 1)):
            raise ValueError("page indexes must be 1..n in order")
        return self
