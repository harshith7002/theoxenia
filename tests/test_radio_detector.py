"""Tests for turboSETI result parsing and deterministic known-answer selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from xenia.radio import detector
from xenia.radio.detector import (
    DopplerHit,
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
    filterbank = tmp_path / "slice.h5"
    filterbank.write_bytes(b"synthetic HDF5 placeholder")
    output_directory = tmp_path / "detector"
    captured: dict[str, object] = {}

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
    assert captured["n_coarse_chan"] == 1
    assert result.turbo_seti_version == "turbo-seti-test"
    assert result.blimpy_version == "blimpy-test"
    assert len(result.hits) == 2
    assert result.artifacts[0].filename == "slice.dat"
    assert len(result.artifacts[0].sha256) == 64


def test_detector_wrapper_rejects_zero_coarse_channels(tmp_path: Path) -> None:
    filterbank = tmp_path / "slice.h5"
    filterbank.write_bytes(b"synthetic HDF5 placeholder")

    with pytest.raises(ValueError, match="coarse-channel count must be positive"):
        run_turboseti(
            filterbank,
            output_directory=tmp_path / "detector",
            max_drift_hz_s=4.0,
            minimum_snr=10.0,
            n_coarse_channels=0,
        )


def test_detector_wrapper_preserves_hits_after_final_logging_type_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filterbank = tmp_path / "slice.h5"
    filterbank.write_bytes(b"synthetic HDF5 placeholder")
    output_directory = tmp_path / "detector"

    class FinderWithPostSearchError:
        def __init__(self, path: str, **kwargs: object) -> None:
            self.out_dir = Path(str(kwargs["out_dir"]))

        def search(self, *, n_partitions: int, progress_bar: str) -> None:
            (self.out_dir / "slice.dat").write_text(DAT_TEXT, encoding="utf-8")
            raise TypeError("format argument: %i requires a real number, not numpy.ndarray")

    monkeypatch.setattr(detector, "_find_doppler_class", lambda: FinderWithPostSearchError)
    monkeypatch.setattr(detector, "version", lambda package: f"{package}-test")

    result = run_turboseti(
        filterbank,
        output_directory=output_directory,
        max_drift_hz_s=4.0,
        minimum_snr=10.0,
    )

    assert len(result.hits) == 2
    assert result.artifacts[0].size_bytes == (output_directory / "slice.dat").stat().st_size
    assert len(result.warnings) == 1
    assert "after writing parseable .dat hit rows" in result.warnings[0]


def _load_search_coarse_channel(source_path: Path):
    namespace: dict[str, object] = {}
    source = source_path.read_text(encoding="utf-8")
    exec(compile(source, str(source_path), "exec"), namespace)  # noqa: S102
    return namespace["search_coarse_channel"]


def test_detector_wrapper_keeps_empty_dat_after_hit_count_log_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filterbank = tmp_path / "slice.h5"
    filterbank.write_bytes(b"synthetic HDF5 placeholder")
    output_directory = tmp_path / "detector"
    source_path = tmp_path / "pkg" / "find_doppler.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "def search_coarse_channel():\n"
        "    total_n_hits = __import__('numpy').zeros(1)\n"
        "    'hit count %i' % total_n_hits\n",
        encoding="utf-8",
    )
    search_coarse_channel = _load_search_coarse_channel(source_path)
    empty_table = f"# {DAT_HEADER}\n"

    class FinderWithFinishedEmptyTable:
        def __init__(self, path: str, **kwargs: object) -> None:
            self.out_dir = Path(str(kwargs["out_dir"]))

        def search(self, *, n_partitions: int, progress_bar: str) -> None:
            (self.out_dir / "slice.dat").write_text(empty_table, encoding="utf-8")
            search_coarse_channel()

    monkeypatch.setattr(detector, "_find_doppler_class", lambda: FinderWithFinishedEmptyTable)
    monkeypatch.setattr(detector, "version", lambda package: f"{package}-test")

    result = run_turboseti(
        filterbank,
        output_directory=output_directory,
        max_drift_hz_s=4.0,
        minimum_snr=10.0,
    )

    assert result.hits == ()
    assert len(result.warnings) == 1
    assert "no hit rows" in result.warnings[0]
    assert result.artifacts[0].filename == "slice.dat"


def test_detector_wrapper_rejects_same_type_error_off_the_hit_count_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filterbank = tmp_path / "slice.h5"
    filterbank.write_bytes(b"synthetic HDF5 placeholder")
    output_directory = tmp_path / "detector"
    source_path = tmp_path / "pkg" / "find_doppler.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "def search_coarse_channel():\n"
        "    raise TypeError("
        "'format argument: %i requires a real number, not numpy.ndarray')\n",
        encoding="utf-8",
    )
    search_coarse_channel = _load_search_coarse_channel(source_path)
    empty_table = f"# {DAT_HEADER}\n"

    class FinderWithUnrelatedFormatError:
        def __init__(self, path: str, **kwargs: object) -> None:
            self.out_dir = Path(str(kwargs["out_dir"]))

        def search(self, *, n_partitions: int, progress_bar: str) -> None:
            (self.out_dir / "slice.dat").write_text(empty_table, encoding="utf-8")
            search_coarse_channel()

    monkeypatch.setattr(detector, "_find_doppler_class", lambda: FinderWithUnrelatedFormatError)
    monkeypatch.setattr(detector, "version", lambda package: f"{package}-test")

    with pytest.raises(TypeError, match="format argument: %i requires a real number"):
        run_turboseti(
            filterbank,
            output_directory=output_directory,
            max_drift_hz_s=4.0,
            minimum_snr=10.0,
        )


def test_detector_wrapper_rejects_post_search_error_without_hit_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filterbank = tmp_path / "slice.h5"
    filterbank.write_bytes(b"synthetic HDF5 placeholder")
    output_directory = tmp_path / "detector"
    empty_table = f"# {DAT_HEADER}\n"

    class FinderWithEmptyOutput:
        def __init__(self, path: str, **kwargs: object) -> None:
            self.out_dir = Path(str(kwargs["out_dir"]))

        def search(self, *, n_partitions: int, progress_bar: str) -> None:
            (self.out_dir / "slice.dat").write_text(empty_table, encoding="utf-8")
            raise TypeError("format argument: %i requires a real number, not numpy.ndarray")

    monkeypatch.setattr(detector, "_find_doppler_class", lambda: FinderWithEmptyOutput)
    monkeypatch.setattr(detector, "version", lambda package: f"{package}-test")

    with pytest.raises(TypeError, match="format argument: %i requires a real number"):
        run_turboseti(
            filterbank,
            output_directory=output_directory,
            max_drift_hz_s=4.0,
            minimum_snr=10.0,
        )
