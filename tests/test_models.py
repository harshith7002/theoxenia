"""Focused validation tests for Mission Control's Pydantic contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from xenia.live.models import (
    CadenceHit,
    DetectionFloor,
    ReviewSignoff,
    SiteMeta,
    Totals,
    Verdict,
)

NOW = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


def _hit(**overrides: object) -> CadenceHit:
    """Create a small valid hit payload for validator tests."""
    values: dict[str, object] = {
        "hit_id": "test-hit",
        "found_at": NOW,
        "freq_mhz": 6000.1,
        "drift_hz_s": 0.0,
        "snr": 12.0,
        "verdict": Verdict.ON_ONLY,
        "explanation": "Synthetic test fixture.",
        "checks_done": 1,
        "thumbnail_url": "runs/test-run/thumbs/test.svg",
        "plot_url": None,
    }
    values.update(overrides)
    return CadenceHit.model_validate(values)


def test_fixture_manifests_validate(demo_manifests: list[object]) -> None:
    """All checked-in fixture documents must conform to the schema source."""
    assert len(demo_manifests) == 4


def test_unexplained_requires_five_checks_and_both_signoffs() -> None:
    """The worker cannot publish an unexplained verdict by itself."""
    with pytest.raises(ValidationError, match="UNEXPLAINED requires"):
        _hit(verdict=Verdict.UNEXPLAINED, checks_done=4)

    signoffs = (
        ReviewSignoff(reviewer="claude", signed_at=NOW, note="Independent review complete."),
        ReviewSignoff(reviewer="michael", signed_at=NOW, note="Approved for review status."),
    )
    hit = _hit(verdict=Verdict.UNEXPLAINED, checks_done=5, review_signoffs=signoffs)
    assert hit.verdict is Verdict.UNEXPLAINED


def test_site_asset_urls_reject_path_traversal() -> None:
    """Static page assets must stay within the page root."""
    with pytest.raises(ValidationError, match="traverse directories"):
        _hit(thumbnail_url="runs/../private.svg")


def test_public_repository_url_must_use_https() -> None:
    """Page metadata cannot expose a non-TLS repository link."""
    with pytest.raises(ValidationError, match="HTTPS"):
        SiteMeta(demo=True, repo_url="http://example.test", data_credit="synthetic")


def test_verdict_totals_must_sum_to_hit_count(demo_state) -> None:
    """The state schema rejects inconsistent summary counters."""
    values = demo_state.totals.model_dump()
    values["hits"] += 1
    with pytest.raises(ValidationError, match="verdict totals must sum to hits"):
        Totals.model_validate(values)


def test_floor_rejects_mismatched_grid_shape() -> None:
    """A recovery matrix must line up with the declared SNR and drift axes."""
    with pytest.raises(ValidationError, match="rows must match snr_grid"):
        DetectionFloor(
            run_id="floor-test",
            snr_grid=(6.0, 12.0),
            drift_grid=(-1.0, 1.0),
            trials_per_cell=5,
            recovered_fraction=((1.0, 1.0),),
            summary="Computed from the test grid.",
            manifest_url="runs/floor-test/manifest.json",
        )


def test_floor_rejects_fractions_outside_zero_to_one() -> None:
    """Recovery proportions cannot exceed their mathematical bounds."""
    with pytest.raises(ValidationError, match="between zero and one"):
        DetectionFloor(
            run_id="floor-test",
            snr_grid=(6.0,),
            drift_grid=(-1.0,),
            trials_per_cell=5,
            recovered_fraction=((1.2,),),
            summary="Computed from the test grid.",
            manifest_url="runs/floor-test/manifest.json",
        )


def test_floor_ci_url_requires_https() -> None:
    """Optional CI provenance cannot inject an insecure or relative link."""
    with pytest.raises(ValidationError, match="absolute HTTPS URLs"):
        DetectionFloor(
            run_id="floor-test",
            snr_grid=(5.0,),
            drift_grid=(0.0,),
            trials_per_cell=1,
            recovered_fraction=((0.0,),),
            summary="Computed from the test grid.",
            manifest_url="runs/floor-test/manifest.json",
            ci_run_url="http://github.com/mpetyx/theoxenia/actions/runs/1",
        )


def test_naive_hit_timestamp_is_rejected() -> None:
    """All event times must include a timezone."""
    with pytest.raises(ValidationError, match="timezone-aware"):
        _hit(found_at=datetime(2026, 10, 12, 10, 0))
