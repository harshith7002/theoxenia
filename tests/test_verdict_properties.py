"""Property tests for the section 4.5 verdict order."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from xenia.live.known_sources import DOWNLINK_HALF_WIDTH_MHZ, Downlink, KnownCatalog, KnownRange
from xenia.live.models import Verdict
from xenia.live.verdict import SESSION_WINDOW_MHZ, CheckRecord, SessionHit, decide_verdict

EMPTY = KnownCatalog(ranges=(), downlinks=())
BAND = KnownCatalog(
    ranges=(
        KnownRange(
            name="fixture band",
            freq_min_mhz=1000.0,
            freq_max_mhz=1001.0,
            source="fixture",
        ),
    ),
    downlinks=(Downlink(name="fixture downlink", freq_mhz=8420.0),),
)
_COUNTS = st.integers(min_value=0, max_value=8)
_DRIFT = st.one_of(
    st.just(0.0),
    st.floats(min_value=-4.0, max_value=4.0, allow_nan=False, allow_infinity=False),
)
_FRACTION = st.floats(min_value=0.0, max_value=0.999, allow_nan=False, allow_infinity=False)
_OUTSIDE = st.floats(min_value=2000.0, max_value=2001.0, allow_nan=False, allow_infinity=False)


def _inside_catalog(frequency_mhz: float) -> bool:
    if 1000.0 <= frequency_mhz <= 1001.0:
        return True
    return abs(frequency_mhz - 8420.0) <= DOWNLINK_HALF_WIDTH_MHZ


def _expected(
    *,
    frequency_mhz: float,
    on_count: int,
    off_count: int,
    passed_filter: bool,
    nearby: bool,
) -> Verdict:
    """Independent reading of the published order. The first match wins."""
    if _inside_catalog(frequency_mhz):
        return Verdict.KNOWN_SOURCE
    if off_count > 0:
        return Verdict.IN_OFF
    if on_count < 3:
        return Verdict.SINGLE_POINTING
    if nearby:
        return Verdict.RFI_CENSUS
    if passed_filter and on_count >= 3 and off_count == 0:
        return Verdict.ON_ONLY
    return Verdict.SINGLE_POINTING


def _assert_common(
    decision_verdict: Verdict,
    drift_hz_s: float,
    checks: tuple[CheckRecord, ...],
) -> None:
    assert decision_verdict is not Verdict.UNEXPLAINED
    assert len(checks) == 5
    review = checks[-1]
    assert review.name == "review"
    assert review.passed is False
    drift = next(check for check in checks if check.name == "drift_sane")
    assert drift.passed is (drift_hz_s != 0.0)


@given(
    frequency_mhz=st.one_of(
        st.floats(min_value=1000.0, max_value=1001.0, allow_nan=False, allow_infinity=False),
        st.floats(
            min_value=8420.0 - DOWNLINK_HALF_WIDTH_MHZ,
            max_value=8420.0 + DOWNLINK_HALF_WIDTH_MHZ,
            allow_nan=False,
            allow_infinity=False,
        ),
    ),
    on_count=_COUNTS,
    off_count=_COUNTS,
    passed_filter=st.booleans(),
    drift_hz_s=_DRIFT,
)
def test_a_catalog_frequency_is_a_known_source(
    frequency_mhz: float,
    on_count: int,
    off_count: int,
    passed_filter: bool,
    drift_hz_s: float,
) -> None:
    """A catalog or downlink hit wins over every later label."""
    decision = decide_verdict(
        frequency_mhz=frequency_mhz,
        drift_hz_s=drift_hz_s,
        on_count=on_count,
        off_count=off_count,
        passed_filter=passed_filter,
        catalog=BAND,
    )
    assert decision.verdict is Verdict.KNOWN_SOURCE
    assert decision.checks_done == 4
    _assert_common(decision.verdict, drift_hz_s, decision.checks)


@given(
    frequency_mhz=_OUTSIDE,
    on_count=_COUNTS,
    off_count=st.integers(min_value=1, max_value=8),
    passed_filter=st.booleans(),
    drift_hz_s=_DRIFT,
    nearby=st.booleans(),
)
def test_an_off_scan_is_in_off_when_the_frequency_is_not_catalogued(
    frequency_mhz: float,
    on_count: int,
    off_count: int,
    passed_filter: bool,
    drift_hz_s: float,
    nearby: bool,
) -> None:
    """Presence in an OFF scan is the second label, before pointing and census."""
    hits = (SessionHit("other", frequency_mhz),) if nearby else ()
    decision = decide_verdict(
        frequency_mhz=frequency_mhz,
        drift_hz_s=drift_hz_s,
        on_count=on_count,
        off_count=off_count,
        passed_filter=passed_filter,
        catalog=EMPTY,
        session_hits=hits,
        this_cadence_id="this",
    )
    assert decision.verdict is Verdict.IN_OFF
    assert decision.checks_done == 4
    _assert_common(decision.verdict, drift_hz_s, decision.checks)


@given(
    frequency_mhz=_OUTSIDE,
    on_count=st.integers(min_value=0, max_value=2),
    passed_filter=st.booleans(),
    drift_hz_s=_DRIFT,
)
def test_fewer_than_three_on_scans_is_a_single_pointing(
    frequency_mhz: float,
    on_count: int,
    passed_filter: bool,
    drift_hz_s: float,
) -> None:
    """With no OFF scan, fewer than three ON scans stay a single pointing."""
    decision = decide_verdict(
        frequency_mhz=frequency_mhz,
        drift_hz_s=drift_hz_s,
        on_count=on_count,
        off_count=0,
        passed_filter=passed_filter,
        catalog=EMPTY,
    )
    assert decision.verdict is Verdict.SINGLE_POINTING
    _assert_common(decision.verdict, drift_hz_s, decision.checks)


@given(
    frequency_mhz=_OUTSIDE,
    on_count=st.integers(min_value=3, max_value=8),
    passed_filter=st.booleans(),
    drift_hz_s=_DRIFT,
    fraction=_FRACTION,
)
def test_another_cadence_inside_one_kilohertz_is_a_census_label(
    frequency_mhz: float,
    on_count: int,
    passed_filter: bool,
    drift_hz_s: float,
    fraction: float,
) -> None:
    """A different cadence inside the session window beats ON_ONLY."""
    other = frequency_mhz + fraction * SESSION_WINDOW_MHZ
    decision = decide_verdict(
        frequency_mhz=frequency_mhz,
        drift_hz_s=drift_hz_s,
        on_count=on_count,
        off_count=0,
        passed_filter=passed_filter,
        catalog=EMPTY,
        session_hits=(SessionHit("other", other),),
        this_cadence_id="this",
    )
    assert decision.verdict is Verdict.RFI_CENSUS
    assert (
        _expected(
            frequency_mhz=frequency_mhz,
            on_count=on_count,
            off_count=0,
            passed_filter=passed_filter,
            nearby=True,
        )
        is Verdict.RFI_CENSUS
    )


@given(
    frequency_mhz=_OUTSIDE,
    on_count=st.integers(min_value=3, max_value=8),
    drift_hz_s=_DRIFT,
)
def test_the_same_cadence_does_not_count_as_another_star(
    frequency_mhz: float,
    on_count: int,
    drift_hz_s: float,
) -> None:
    """A hit carrying this cadence id is not a session-census match."""
    decision = decide_verdict(
        frequency_mhz=frequency_mhz,
        drift_hz_s=drift_hz_s,
        on_count=on_count,
        off_count=0,
        passed_filter=True,
        catalog=EMPTY,
        session_hits=(SessionHit("this", frequency_mhz),),
        this_cadence_id="this",
    )
    assert decision.verdict is Verdict.ON_ONLY


@given(
    frequency_mhz=_OUTSIDE,
    on_count=st.integers(min_value=3, max_value=8),
    passed_filter=st.booleans(),
    drift_hz_s=_DRIFT,
    extra=st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_a_hit_outside_one_kilohertz_follows_the_filter(
    frequency_mhz: float,
    on_count: int,
    passed_filter: bool,
    drift_hz_s: float,
    extra: float,
) -> None:
    """Past the session window, the filter decides between ON_ONLY and a single pointing."""
    other = frequency_mhz + SESSION_WINDOW_MHZ + extra
    decision = decide_verdict(
        frequency_mhz=frequency_mhz,
        drift_hz_s=drift_hz_s,
        on_count=on_count,
        off_count=0,
        passed_filter=passed_filter,
        catalog=EMPTY,
        session_hits=(SessionHit("other", other),),
        this_cadence_id="this",
    )
    expected = Verdict.ON_ONLY if passed_filter else Verdict.SINGLE_POINTING
    assert decision.verdict is expected
    assert decision.verdict is not Verdict.UNEXPLAINED


@given(
    on_count=st.integers(min_value=-8, max_value=-1),
    off_count=st.integers(min_value=-8, max_value=3),
)
def test_a_negative_scan_count_is_rejected(on_count: int, off_count: int) -> None:
    """Negative scan counts are input errors, not a verdict."""
    with pytest.raises(ValueError, match="scan counts cannot be negative"):
        decide_verdict(
            frequency_mhz=2000.0,
            drift_hz_s=0.2,
            on_count=on_count,
            off_count=off_count,
            passed_filter=True,
            catalog=EMPTY,
        )


@given(off_count=st.integers(min_value=-8, max_value=-1))
def test_a_negative_off_count_is_rejected(off_count: int) -> None:
    """A negative OFF count is rejected even when the ON count is usable."""
    with pytest.raises(ValueError, match="scan counts cannot be negative"):
        decide_verdict(
            frequency_mhz=2000.0,
            drift_hz_s=0.2,
            on_count=3,
            off_count=off_count,
            passed_filter=False,
            catalog=EMPTY,
        )
