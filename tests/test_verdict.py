"""Section 4.5 verdict order. UNEXPLAINED is unreachable from the worker."""

from __future__ import annotations

from pathlib import Path

import pytest

from xenia.live.known_sources import Downlink, KnownCatalog, KnownRange, load_known_sources
from xenia.live.models import Verdict
from xenia.live.verdict import SYNTHETIC_EXPLANATION_PREFIX, SessionHit, decide_verdict

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CATALOG = KnownCatalog(
    ranges=(
        KnownRange(
            name="synthetic known-answer band",
            freq_min_mhz=5999.986,
            freq_max_mhz=5999.989,
            source="fixture",
        ),
    ),
    downlinks=(),
)


def _decide(**overrides: object):
    values = {
        "frequency_mhz": 5999.99,
        "drift_hz_s": 0.8,
        "on_count": 3,
        "off_count": 0,
        "passed_filter": True,
        "catalog": CATALOG,
        "synthetic": True,
    }
    values.update(overrides)
    return decide_verdict(**values)  # type: ignore[arg-type]


def test_known_source_wins_over_an_on_only_pattern() -> None:
    """A catalog hit is labelled before the ON/OFF filter is considered."""
    decision = _decide(frequency_mhz=5999.987)
    assert decision.verdict is Verdict.KNOWN_SOURCE
    assert decision.known_source == "synthetic known-answer band"
    assert decision.badge_text == "Known transmitter: synthetic known-answer band"
    assert decision.checks_done == 4
    assert SYNTHETIC_EXPLANATION_PREFIX in decision.explanation


def test_off_scan_beats_a_single_on_scan() -> None:
    decision = _decide(on_count=1, off_count=1, passed_filter=False)
    assert decision.verdict is Verdict.IN_OFF
    assert decision.badge_text == "Also present in OFF scans"


def test_single_pointing_is_fewer_than_three_on_scans() -> None:
    decision = _decide(on_count=1, off_count=0, passed_filter=False)
    assert decision.verdict is Verdict.SINGLE_POINTING
    assert decision.badge_text == "Missing from one or more ON scans"


def test_session_census_beats_on_only() -> None:
    decision = _decide(session_hits=(SessionHit(cadence_id="other-star", frequency_mhz=5999.9904),))
    assert decision.verdict is Verdict.RFI_CENSUS
    assert decision.badge_text == "Same frequency in another star the same day"


def test_on_only_is_the_last_worker_verdict() -> None:
    decision = _decide()
    assert decision.verdict is Verdict.ON_ONLY
    assert decision.badge_text == "Survivor, 4 of 5 checks done"
    assert decision.checks[-1].name == "review"
    assert decision.checks[-1].passed is False


def test_zero_drift_fails_the_drift_check_without_a_width_measurement() -> None:
    decision = _decide(drift_hz_s=0.0, on_count=0, off_count=6, passed_filter=False)
    drift = next(check for check in decision.checks if check.name == "drift_sane")
    assert decision.verdict is Verdict.IN_OFF
    assert drift.passed is False
    assert "3-sigma" in drift.note


def test_downlink_window_is_fifty_kilohertz() -> None:
    catalog = KnownCatalog(
        ranges=(),
        downlinks=(Downlink(name="synthetic downlink", freq_mhz=8420.0),),
    )
    inside = _decide(frequency_mhz=8420.04, catalog=catalog, synthetic=False)
    outside = _decide(frequency_mhz=8420.06, catalog=catalog, synthetic=False)
    assert inside.verdict is Verdict.KNOWN_SOURCE
    assert outside.verdict is Verdict.ON_ONLY
    assert SYNTHETIC_EXPLANATION_PREFIX not in outside.explanation


def test_worker_cannot_return_unexplained() -> None:
    """Every combination the worker can see stays at or before ON_ONLY."""
    catalog = CATALOG
    for on_count in (0, 1, 3):
        for off_count in (0, 1):
            for passed in (False, True):
                for frequency in (5999.987, 5999.99):
                    decision = decide_verdict(
                        frequency_mhz=frequency,
                        drift_hz_s=0.2,
                        on_count=on_count,
                        off_count=off_count,
                        passed_filter=passed,
                        catalog=catalog,
                    )
                    assert decision.verdict is not Verdict.UNEXPLAINED


def test_known_sources_file_loads_the_fixture_band() -> None:
    catalog = load_known_sources(
        REPOSITORY_ROOT / "configs" / "fixtures" / "exp004_known_sources.yaml"
    )
    assert catalog.match(5999.987) == "synthetic known-answer band"
    assert catalog.match(5999.991) is None
    assert catalog.downlinks == ()


def test_verified_catalog_uses_sourced_ranges_only() -> None:
    catalog = load_known_sources(REPOSITORY_ROOT / "configs" / "known_sources.yaml")
    assert catalog.match(5999.987) is None
    assert catalog.match(1575.42) == "GPS L1"
    assert catalog.match(1227.6) == "GPS L2"
    assert catalog.match(1602.0) == "GLONASS L1 FDMA"
    assert catalog.match(8419.297028) == "Voyager 1 X-band"
    assert catalog.match(8419.0) is None
    assert all(item.source_url and item.checked for item in catalog.ranges)
    assert all(item.source_url and item.checked for item in catalog.downlinks)


def test_known_sources_file_rejects_a_reversed_range(tmp_path: Path) -> None:
    path = tmp_path / "known_sources.yaml"
    path.write_text(
        "ranges:\n  - name: backwards\n    freq_min_mhz: 2\n    freq_max_mhz: 1\n"
        "    source: fixture\n    source_url: synthetic://test\n    checked: '2026-10-12'\n"
        "downlinks: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must increase"):
        load_known_sources(path)
