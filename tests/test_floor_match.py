"""Property tests for the one-to-one floor matcher."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from xenia.radio.detector import DopplerHit
from xenia.radio.floor import _InjectionPlan, _match_trial
from xenia.radio.floor_config import (
    DETECTOR_SNR_THRESHOLD,
    DRIFT_TOLERANCE_HZ_S,
    FREQUENCY_TOLERANCE_HZ,
)

_FRACTION = st.floats(min_value=0.0, max_value=0.999, allow_nan=False, allow_infinity=False)
_OVER = st.floats(min_value=1e-3, max_value=10.0, allow_nan=False, allow_infinity=False)


def _plan(frequency_mhz: float = 6000.0, drift_hz_s: float = 0.0) -> _InjectionPlan:
    return _InjectionPlan(
        snr=20.0,
        drift_hz_s=drift_hz_s,
        trial_index=1,
        seed=1,
        channel_index=0,
        frequency_mhz=frequency_mhz,
        start_frequency_mhz=frequency_mhz,
    )


def _hit(frequency_mhz: float, drift_hz_s: float, snr: float) -> DopplerHit:
    return DopplerHit(
        top_hit=1,
        drift_hz_s=drift_hz_s,
        snr=snr,
        uncorrected_frequency_mhz=frequency_mhz,
        corrected_frequency_mhz=frequency_mhz,
        frequency_start_mhz=frequency_mhz,
        frequency_end_mhz=frequency_mhz,
    )


@given(freq_fraction=_FRACTION, drift_fraction=_FRACTION, snr_extra=_FRACTION)
def test_a_hit_inside_both_tolerances_is_recovered(
    freq_fraction: float, drift_fraction: float, snr_extra: float
) -> None:
    """Errors up to just under the published tolerances recover that one plan."""
    plan = _plan()
    frequency_error_hz = freq_fraction * FREQUENCY_TOLERANCE_HZ
    drift_error = drift_fraction * DRIFT_TOLERANCE_HZ_S
    hit = _hit(
        plan.frequency_mhz + frequency_error_hz / 1e6,
        plan.drift_hz_s + drift_error,
        DETECTOR_SNR_THRESHOLD + snr_extra,
    )
    measured = _match_trial((plan,), (hit,))
    assert measured[0].recovered is True


@given(extra=_OVER)
def test_a_frequency_error_past_the_tolerance_is_not_recovered(extra: float) -> None:
    """One hertz past the frequency tolerance is a miss."""
    plan = _plan()
    frequency_error_hz = FREQUENCY_TOLERANCE_HZ + extra
    hit = _hit(
        plan.frequency_mhz + frequency_error_hz / 1e6,
        plan.drift_hz_s,
        DETECTOR_SNR_THRESHOLD,
    )
    measured = _match_trial((plan,), (hit,))
    assert measured[0].recovered is False


@given(extra=_OVER)
def test_a_drift_error_past_the_tolerance_is_not_recovered(extra: float) -> None:
    """Drift past the tolerance is a miss even when the frequency matches."""
    plan = _plan()
    hit = _hit(plan.frequency_mhz, plan.drift_hz_s + DRIFT_TOLERANCE_HZ_S + extra, 30.0)
    measured = _match_trial((plan,), (hit,))
    assert measured[0].recovered is False


def test_one_hit_can_recover_only_one_plan() -> None:
    """The matcher assigns a detector hit to at most one injection."""
    first = _plan()
    second = _InjectionPlan(
        snr=20.0,
        drift_hz_s=0.0,
        trial_index=2,
        seed=2,
        channel_index=1,
        frequency_mhz=first.frequency_mhz,
        start_frequency_mhz=first.frequency_mhz,
    )
    hit = _hit(first.frequency_mhz, 0.0, 40.0)
    measured = _match_trial((first, second), (hit,))
    assert tuple(item.recovered for item in measured) == (True, False)
