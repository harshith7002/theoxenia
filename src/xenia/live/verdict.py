"""Prosaic verdicts from spec section 4.5. The worker never emits UNEXPLAINED."""

from __future__ import annotations

from dataclasses import dataclass

from xenia.live.known_sources import KnownCatalog
from xenia.live.models import Verdict
from xenia.live.state import verdict_badge

SESSION_WINDOW_MHZ = 0.001  # ±1 kHz
SYNTHETIC_EXPLANATION_PREFIX = "Synthetic ABACAD cadence, not a telescope observation."


@dataclass(frozen=True, slots=True)
class SessionHit:
    """One hit from a different cadence in the same observing session."""

    cadence_id: str
    frequency_mhz: float


@dataclass(frozen=True, slots=True)
class CheckRecord:
    """One of the five section 8.6 checks, recorded even when it fails."""

    name: str
    passed: bool
    note: str


@dataclass(frozen=True, slots=True)
class VerdictDecision:
    """A verdict the worker is allowed to write, plus the five check records."""

    verdict: Verdict
    known_source: str | None
    checks: tuple[CheckRecord, ...]
    checks_done: int
    badge_text: str
    explanation: str

    def __post_init__(self) -> None:
        if self.verdict is Verdict.UNEXPLAINED:
            raise RuntimeError("verdict assignment cannot return UNEXPLAINED")


def decide_verdict(
    *,
    frequency_mhz: float,
    drift_hz_s: float,
    on_count: int,
    off_count: int,
    passed_filter: bool,
    catalog: KnownCatalog,
    session_hits: tuple[SessionHit, ...] = (),
    this_cadence_id: str = "",
    synthetic: bool = False,
) -> VerdictDecision:
    """Apply section 4.5 in order. The first match wins.

    This function cannot return UNEXPLAINED. A line that passes the filter and
    matches nothing earlier stays ON_ONLY until a reviewer signs it.
    """
    if on_count < 0 or off_count < 0:
        raise ValueError("scan counts cannot be negative")
    known_name = catalog.match(frequency_mhz)
    session_match = _session_match(
        frequency_mhz, session_hits=session_hits, this_cadence_id=this_cadence_id
    )

    if known_name is not None:
        verdict = Verdict.KNOWN_SOURCE
        reason = f"The frequency falls inside {known_name}."
    elif off_count > 0:
        verdict = Verdict.IN_OFF
        reason = "The line is present in an OFF scan, so the ON/OFF filter does not pass."
    elif on_count < 3:
        verdict = Verdict.SINGLE_POINTING
        reason = "The line is present in fewer than all three ON scans."
    elif session_match is not None:
        verdict = Verdict.RFI_CENSUS
        reason = (
            "A hit within 1 kHz appears in another cadence from the same session "
            f"({session_match.cadence_id})."
        )
    elif passed_filter and on_count >= 3 and off_count == 0:
        verdict = Verdict.ON_ONLY
        reason = "The line passed the ON/OFF filter and none of the earlier prosaic labels fit."
    else:
        verdict = Verdict.SINGLE_POINTING
        reason = "The line did not pass the three-ON filter."

    checks = _checks(
        drift_hz_s=drift_hz_s,
        off_count=off_count,
        passed_filter=passed_filter,
        known_name=known_name,
        session_match=session_match,
        session_hits=session_hits,
    )
    recorded = sum(check.name != "review" for check in checks)
    prefix = f"{SYNTHETIC_EXPLANATION_PREFIX} " if synthetic else ""
    return VerdictDecision(
        verdict=verdict,
        known_source=known_name,
        checks=checks,
        checks_done=recorded,
        badge_text=verdict_badge(verdict, recorded, known_name),
        explanation=f"{prefix}{reason}",
    )


def _session_match(
    frequency_mhz: float,
    *,
    session_hits: tuple[SessionHit, ...],
    this_cadence_id: str,
) -> SessionHit | None:
    for hit in session_hits:
        if hit.cadence_id == this_cadence_id:
            continue
        if abs(hit.frequency_mhz - frequency_mhz) <= SESSION_WINDOW_MHZ:
            return hit
    return None


def _checks(
    *,
    drift_hz_s: float,
    off_count: int,
    passed_filter: bool,
    known_name: str | None,
    session_match: SessionHit | None,
    session_hits: tuple[SessionHit, ...],
) -> tuple[CheckRecord, ...]:
    filter_passed = passed_filter and off_count == 0
    if filter_passed:
        off_note = "The ABACAD filter passed: the line is in the ON scans and not in an OFF scan."
    elif off_count > 0:
        off_note = f"The line is present in {off_count} OFF scan(s)."
    else:
        off_note = "The filter-3 event list does not contain this line."

    if known_name is None:
        known_note = "Frequency is outside every catalog range and every downlink window."
    else:
        known_note = f"Frequency falls inside {known_name}."

    if drift_hz_s != 0:
        drift_note = f"Drift is {drift_hz_s:+.6f} Hz/s, not zero."
        drift_ok = True
    else:
        drift_note = (
            "Drift is 0 Hz/s. A perfectly zero-drift line is suspicious because "
            "terrestrial sources do not drift. Line width was not measured, so the "
            "3-sigma width alternative was not applied."
        )
        drift_ok = False

    if session_match is not None:
        session_note = (
            f"A hit in {session_match.cadence_id} is within 1 kHz "
            f"({session_match.frequency_mhz:.6f} MHz)."
        )
        session_ok = False
    elif not session_hits:
        session_note = "No other cadence from this observing session was supplied."
        session_ok = True
    else:
        session_note = "No hit within 1 kHz appears in another cadence of this session."
        session_ok = True

    return (
        CheckRecord("not_in_off", filter_passed, off_note),
        CheckRecord("not_known_transmitter", known_name is None, known_note),
        CheckRecord("drift_sane", drift_ok, drift_note),
        CheckRecord("session_census_clear", session_ok, session_note),
        CheckRecord(
            "review",
            False,
            "Review is not done. The worker cannot sign a reviewed verdict.",
        ),
    )
