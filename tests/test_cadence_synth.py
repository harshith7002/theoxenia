"""The EXP-004 injection plan stays inside its own slots and the catalog range."""

from __future__ import annotations

from pathlib import Path

from xenia.live.known_sources import load_known_sources
from xenia.radio.cadence_synth import (
    CADENCE_ROLES,
    injection_truths,
    scan_duration_seconds,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_four_injections_keep_separated_paths() -> None:
    """Slot spacing is wider than each drifted path, so labels cannot swap."""
    truths = injection_truths()
    assert [item.injection_id for item in truths] == [
        "on_only",
        "in_off",
        "single_pointing",
        "known_source",
    ]
    assert [item.expected_verdict for item in truths] == [
        "ON_ONLY",
        "IN_OFF",
        "SINGLE_POINTING",
        "KNOWN_SOURCE",
    ]
    duration = scan_duration_seconds() * len(CADENCE_ROLES)
    intervals = []
    for item in truths:
        start_hz = item.start_frequency_mhz * 1e6
        stop_hz = start_hz + item.drift_hz_s * duration
        intervals.append((min(start_hz, stop_hz), max(start_hz, stop_hz), item.injection_id))
    intervals.sort()
    for earlier, later in zip(intervals, intervals[1:], strict=False):
        assert later[0] - earlier[1] > 1_000.0


def test_only_the_known_source_line_enters_the_catalog_range() -> None:
    catalog = load_known_sources(REPOSITORY_ROOT / "configs" / "known_sources.yaml")
    duration = scan_duration_seconds() * len(CADENCE_ROLES)
    for item in injection_truths():
        samples = [item.frequency_mhz_at(fraction * duration) for fraction in (0.0, 0.5, 1.0)]
        inside = [catalog.match(frequency) is not None for frequency in samples]
        if item.injection_id == "known_source":
            assert all(inside)
        else:
            assert not any(inside)
