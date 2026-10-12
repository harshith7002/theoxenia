"""Tests for turboSETI result parsing and deterministic known-answer selection."""

from __future__ import annotations

from pathlib import Path

import h5py
import pytest

from xenia.radio import detector
from xenia.radio.detector import (
    DopplerHit,
    _examine_hdf5_with_two_integrations,
    parse_dat_text,
    run_turboseti,
    select_known_answer_hit,
)

DAT_HEADER = "\t".join(
    (
        "Top_Hit_#",
        "Drift_Rate",
        "SNR",
        "Uncorrected_Frequency",
        "Corrected_Frequency",
        "Index",
        "freq_start",
        "freq_end",
        "SEFD",
        "SEFD_freq",
        "Coarse_Channel_Number",
        "Full_number_of_hits",
    )
)
DAT_TEXT = f"""# --------------------------
# {DAT_HEADER}
# --------------------------
000001\t-0.392226\t30.612000\t8419.319368\t8419.319369\t101\t8419.319000\t8419.319700\t0.0\t0.0\t0\t4
000002\t1.250000\t12.500000\t8419.500000\t8419.500010\t205\t8419.499800\t8419.500200\t0.0\t0.0\t0\t4
"""


def test_parse_dat_rows_by_header_name() -> None:
    hits = parse_dat_text(DAT_TEXT)

    assert len(hits) == 2
    assert hits[0] == DopplerHit(
        top_hit=1,
        drift_hz_s=-0.392226,
        snr=30.612,
        uncorrected_frequency_mhz=8419.319368,
        corrected_frequency_mhz=8419.319369,
        frequency_start_mhz=8419.319,
        frequency_end_mhz=8419.3197,
    )


def test_select_known_answer_uses_observed_frequency_and_thresholds() -> None:
    hits = parse_dat_text(DAT_TEXT)

    selected = select_known_answer_hit(
        hits,
        frequency_low_mhz=8419.0,
        frequency_high_mhz=8420.0,
        max_abs_drift_hz_s=4.0,
        minimum_snr=10.0,
    )

    assert selected == hits[0]
    assert (
        select_known_answer_hit(
            hits,
            frequency_low_mhz=8419.4,
            frequency_high_mhz=8420.0,
            max_abs_drift_hz_s=1.0,
            minimum_snr=20.0,
        )
        is None
    )


def test_parse_rejects_incomplete_header_or_rows() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        parse_dat_text("# Top_Hit_# SNR\n")
    with pytest.raises(ValueError, match="expected"):
        parse_dat_text(
            "# Top_Hit_# Drift_Rate SNR Uncorrected_Frequency Corrected_Frequency "
            "freq_start freq_end\n1 2"
        )


def test_detector_wrapper_captures_versions_hits_and_output_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filterbank = tmp_path / "slice.fil"
    filterbank.write_bytes(b"synthetic filterbank placeholder")
    output_directory = tmp_path / "detector"
    captured: dict[str, object] = {}
    from blimpy.io import hdf_reader

    original_examine = hdf_reader.examine_h5

    class FakeFinder:
        def __init__(self, path: str, **kwargs: object) -> None:
            captured["path"] = path
            captured.update(kwargs)
            self.out_dir = Path(str(kwargs["out_dir"]))

        def search(self, *, n_partitions: int, progress_bar: str) -> None:
            assert n_partitions == 1
            assert progress_bar == "n"
            (self.out_dir / "slice.dat").write_text(DAT_TEXT, encoding="utf-8")

    monkeypatch.setattr(detector, "_find_doppler_class", lambda: FakeFinder)
    monkeypatch.setattr(detector, "version", lambda package: f"{package}-test")

    result = run_turboseti(
        filterbank,
        output_directory=output_directory,
        max_drift_hz_s=4.0,
        minimum_snr=10.0,
    )

    assert captured["path"] == str(filterbank)
    assert captured["max_drift"] == 4.0
    assert captured["snr"] == 10.0
    assert result.turbo_seti_version == "turbo-seti-test"
    assert result.blimpy_version == "blimpy-test"
    assert len(result.hits) == 2
    assert result.artifacts[0].filename == "slice.dat"
    assert len(result.artifacts[0].sha256) == 64
    assert hdf_reader.examine_h5 is original_examine


def test_two_integration_hdf5_is_structurally_checked(tmp_path: Path) -> None:
    """Two integrations are checked at valid endpoints instead of index 2."""
    hdf5_path = tmp_path / "two-integrations.h5"
    with h5py.File(hdf5_path, "w") as h5:
        h5.attrs["CLASS"] = "FILTERBANK"
        h5.attrs["VERSION"] = "2.0"
        h5.create_dataset("data", data=[[[1.0, 2.0, 3.0]], [[4.0, 5.0, 6.0]]])

    with h5py.File(hdf5_path, "r") as h5:
        assert _examine_hdf5_with_two_integrations(h5, lambda _h5: pytest.fail()) == 2.0


def test_other_hdf5_shapes_use_the_upstream_validator(tmp_path: Path) -> None:
    """The compatibility exception is restricted to exactly two integrations."""
    hdf5_path = tmp_path / "three-integrations.h5"
    with h5py.File(hdf5_path, "w") as h5:
        h5.attrs["CLASS"] = "FILTERBANK"
        h5.attrs["VERSION"] = "2.0"
        h5.create_dataset("data", shape=(3, 1, 3), dtype="f4")

    with h5py.File(hdf5_path, "r") as h5:
        assert _examine_hdf5_with_two_integrations(h5, lambda _h5: 7.0) == 7.0
