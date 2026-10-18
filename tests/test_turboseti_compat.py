"""Actual detector witnesses for the 16-sample drift-range boundary correction."""

from __future__ import annotations

import importlib

import h5py
import numpy as np
import pytest

from xenia.radio.detector import run_turboseti
from xenia.radio.turboseti_compat import backport_source, compatible_search


@pytest.mark.parametrize("speed", [-26, 26])
def test_boundary_tracks_missing_from_legacy_search_are_recovered(tmp_path, speed):
    nfreq = 4096
    tsamp = 18.253611008
    foff = -2.7939677238464355e-6
    values = np.random.default_rng(92).normal(100, 1, (16, 1, nfreq)).astype("<f4")
    start = 1500
    for t in range(16):
        values[t, 0, start + speed * t] += 40
    source = tmp_path / "boundary.h5"
    with h5py.File(source, "w") as f:
        f.attrs["CLASS"] = "FILTERBANK"
        f.attrs["VERSION"] = "1.0"
        d = f.create_dataset("data", data=values)
        d.attrs.update(
            {
                "source_name": "SYNTHETIC_BOUNDARY",
                "nchans": nfreq,
                "nifs": 1,
                "nbits": 32,
                "fch1": 1381.0,
                "foff": foff,
                "tsamp": tsamp,
                "tstart": 57622.0,
                "src_raj": 0.0,
                "src_dej": 0.0,
                "telescope_id": 6,
            }
        )
    drift = speed * foff * 1e6 / tsamp
    frequency = 1381 + start * foff

    def matches(result):
        return [
            h
            for h in result.hits
            if abs(h.drift_hz_s - drift) < 0.03
            and abs(h.uncorrected_frequency_mhz - frequency) < 3 * abs(foff)
        ]

    original = run_turboseti(
        source,
        output_directory=tmp_path / "legacy",
        max_drift_hz_s=4,
        minimum_snr=10,
        apply_compatibility=False,
    )
    corrected = run_turboseti(
        source, output_directory=tmp_path / "corrected", max_drift_hz_s=4, minimum_snr=10
    )
    assert not matches(original)
    assert matches(corrected)
    assert not any("TypeError" in warning for warning in corrected.warnings)


def test_scoped_backport_restores_upstream_after_failure():
    module = importlib.import_module("turbo_seti.find_doppler.find_doppler")
    original = module.search_coarse_channel
    with pytest.raises(ValueError), compatible_search(enabled=True):
        assert module.search_coarse_channel is not original
        raise ValueError("simulated search failure")
    assert module.search_coarse_channel is original


def test_backport_refuses_unrecognized_source():
    with pytest.raises(RuntimeError, match="audited function"):
        backport_source("def different_function(): pass")
