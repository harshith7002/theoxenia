"""Falsifying witnesses for the independent archive diagnostic calculation."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "archive_diagnosis", Path(__file__).parents[1] / "scripts" / "diagnose_archive.py"
)
assert _SPEC and _SPEC.loader
DIAG = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(DIAG)


@pytest.mark.parametrize("speed", [-1, 1])
def test_independent_grid_recovers_both_drift_signs_without_wrapping(speed):
    rng = np.random.default_rng(461)
    power = rng.normal(100, 1, (4, 128))
    for t in range(4):
        power[t, 40 + speed * t] += 40
    result = DIAG.direct_grid(power, -1, 1)
    best = max(result["trials"], key=lambda t: t["max_snr"])
    assert best["endpoint_channels"] == speed * 3
    assert best["drift_hz_s"] == -speed
    assert best["channel"] == 40
    assert best["max_snr"] > 40


def test_reference_rejects_constant_power():
    with pytest.raises(ValueError, match="normalization"):
        DIAG.stats(np.ones((16, 100)))


def test_selection_probe_distinguishes_threshold_from_neighbor_suppression():
    spec = importlib.util.spec_from_file_location(
        "control_selection", Path(__file__).parents[1] / "scripts" / "audit_control_selection.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scores = np.zeros(100)
    drifts = np.ones(100) * 0.15
    scores[40] = 40
    scores[49] = 100
    suppressed = module.inspect_selection(scores, drifts, 40, 0, 10)
    assert suppressed["candidate_snr"] == 40
    assert suppressed["neighbor_snr"] == 100
    assert suppressed["suppressed"]
    scores[49] = 0
    assert not module.inspect_selection(scores, drifts, 40, 0, 10)["suppressed"]
