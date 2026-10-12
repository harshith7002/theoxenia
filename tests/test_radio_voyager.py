"""Offline tests for the EXP-001 HDF5 orchestration and provenance behavior."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import h5py
import numpy as np
import pytest

from xenia.live.models import HeroPayload, RunManifest
from xenia.radio import voyager
from xenia.radio.detector import DetectorArtifact, DetectorResult, DopplerHit
from xenia.radio.hdf5 import Hdf5FilterbankHeader, Hdf5SliceInfo
from xenia.radio.remote import ByteRange, RangeMetrics, RemoteReadError


class _RemotePlaceholder:
    size = voyager.SOURCE_SIZE_BYTES


def _synthetic_header() -> Hdf5FilterbankHeader:
    return Hdf5FilterbankHeader(
        source_name=voyager.SOURCE_NAME,
        integrations=16,
        nifs=1,
        nchans=1_048_576,
        nbits=32,
        fch1_mhz=8421.386717353016,
        foff_mhz=-2.7939677238464355e-06,
        tsamp_seconds=18.253611008,
        tstart_mjd=57650.78209490741,
        dtype="<f4",
        chunk_shape=(1, 1, 16384),
        source_size_bytes=voyager.SOURCE_SIZE_BYTES,
        file_class="FILTERBANK",
        file_version="1.0",
        root_members=("data",),
        data_attributes=(
            "fch1",
            "foff",
            "nbits",
            "nchans",
            "nifs",
            "source_name",
            "tsamp",
            "tstart",
        ),
    )


def _install_fake_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    hit: DopplerHit | None,
) -> None:
    remote = _RemotePlaceholder()
    metrics = RangeMetrics(
        source_url=voyager.DEFAULT_SOURCE_URL,
        source_size_bytes=remote.size,
        max_transfer_bytes=voyager.REMOTE_TRANSFER_LIMIT_BYTES,
        ranges=[ByteRange(start=0, end_exclusive=4096, bytes_received=4096)],
    )

    @contextmanager
    def fake_open(
        *args: object, **kwargs: object
    ) -> Iterator[tuple[_RemotePlaceholder, RangeMetrics]]:
        assert args[0] == voyager.DEFAULT_SOURCE_URL
        assert kwargs["block_size"] == voyager.REMOTE_BLOCK_SIZE_BYTES
        assert kwargs["max_transfer_bytes"] == voyager.REMOTE_TRANSFER_LIMIT_BYTES
        yield remote, metrics

    header = _synthetic_header()

    def fake_slice(
        source: _RemotePlaceholder, *, output_path: Path, **kwargs: object
    ) -> Hdf5SliceInfo:
        assert source is remote
        assert kwargs["frequency_low_mhz"] == voyager.DEFAULT_FREQUENCY_LOW_MHZ
        assert kwargs["frequency_high_mhz"] == voyager.DEFAULT_FREQUENCY_HIGH_MHZ
        assert kwargs["expected_source_name"] == voyager.SOURCE_NAME
        on_header = kwargs["on_header"]
        assert callable(on_header)
        on_header(header)
        output_path.write_bytes(b"synthetic-temporary-hdf5-slice")
        return Hdf5SliceInfo(
            header=header,
            channel_start=12_000,
            channel_count=39_370,
            first_center_mhz=8419.349,
            last_center_mhz=8419.240,
            output_size_bytes=31,
            output_sha256="b" * 64,
        )

    result_hit = () if hit is None else (hit,)
    result = DetectorResult(
        hits=result_hit,
        artifacts=(DetectorArtifact(filename="slice.dat", sha256="a" * 64, size_bytes=42),),
        turbo_seti_version="2.3.2",
        blimpy_version="2.1.4",
    )

    def fake_detector(
        filterbank_path: Path, *, output_directory: Path, **kwargs: object
    ) -> DetectorResult:
        assert filterbank_path.suffix == ".h5"
        assert filterbank_path.is_file()
        assert output_directory.name == "detector"
        assert kwargs["max_drift_hz_s"] == voyager.DEFAULT_MAX_DRIFT_HZ_S
        assert kwargs["minimum_snr"] == voyager.DEFAULT_MINIMUM_SNR
        return result

    def fake_plot(
        slice_path: Path,
        output_path: Path,
        slice_info: Hdf5SliceInfo,
        *,
        hit: DopplerHit | None,
    ) -> None:
        assert slice_path.is_file()
        assert slice_info.header.integrations == 16
        assert hit is None or hit.uncorrected_frequency_mhz == pytest.approx(8419.297028)
        output_path.write_bytes(b"synthetic-png")

    monkeypatch.setattr(voyager, "open_counted_http_file", fake_open)
    monkeypatch.setattr(voyager, "slice_hdf5_filterbank", fake_slice)
    monkeypatch.setattr(voyager, "run_turboseti", fake_detector)
    monkeypatch.setattr(voyager, "_render_waterfall_png", fake_plot)


def test_voyager_run_writes_linked_hero_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hit = DopplerHit(
        top_hit=1,
        drift_hz_s=-0.373093,
        snr=245.708,
        uncorrected_frequency_mhz=8419.297028,
        corrected_frequency_mhz=8419.297029,
        frequency_start_mhz=8419.2969,
        frequency_end_mhz=8419.2971,
    )
    _install_fake_pipeline(monkeypatch, hit=hit)

    manifest, manifest_path = voyager.run_voyager(
        tmp_path,
        ["xenia", "live", "hero", "--voyager"],
    )

    assert manifest_path.is_file()
    assert manifest.experiment_id == "EXP-001"
    assert manifest.pillar == "I · Sensor"
    assert manifest.outcome == "known_answer_detected"
    assert manifest.inputs[0].uri == voyager.DEFAULT_SOURCE_URL
    assert manifest.inputs[0].size_bytes == voyager.SOURCE_SIZE_BYTES
    assert isinstance(manifest.mission_control, HeroPayload)
    assert manifest.mission_control.freq_mhz == pytest.approx(8419.297028)
    assert manifest.mission_control.image_url.endswith("/hero.png")
    assert manifest.parameters["canonical_source_url"] == voyager.CANONICAL_SOURCE_URL
    assert manifest.parameters["known_answer_window_mhz"] == [8419.296, 8419.298]
    assert manifest.parameters["source_header"]["integrations"] == 16
    assert manifest.parameters["remote_transfer"]["bytes_transferred"] == 4096
    assert manifest.parameters["mirror_provenance"]["commit"] == voyager.SOURCE_MIRROR_COMMIT
    assert all((tmp_path / item.path).is_file() for item in manifest.outputs if item.sha256)
    assert not list(tmp_path.rglob("*.h5"))
    assert not list(tmp_path.rglob("*.fil"))

    hits_path = next(tmp_path.glob("runs/*/hits.json"))
    hits = json.loads(hits_path.read_text(encoding="utf-8"))
    assert hits["selected_known_answer_hit"]["snr"] == pytest.approx(245.708)


def test_voyager_null_result_is_recorded_without_hero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_pipeline(monkeypatch, hit=None)

    manifest, manifest_path = voyager.run_voyager(
        tmp_path,
        ["xenia", "live", "hero", "--voyager"],
    )

    assert manifest_path.is_file()
    assert manifest.outcome == "no_expected_hit"
    assert manifest.mission_control is None
    assert any("Null known-answer result" in note for note in manifest.notes)
    assert any(item.path.endswith("hero.png") for item in manifest.outputs)
    assert any(item.path.endswith("hits.json") for item in manifest.outputs)


def test_voyager_open_failure_still_writes_failure_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def fail_open(*args: object, **kwargs: object):
        raise RemoteReadError("synthetic range failure")
        yield  # pragma: no cover - makes this function a context manager

    monkeypatch.setattr(voyager, "open_counted_http_file", fail_open)

    with pytest.raises(RemoteReadError, match="synthetic range failure"):
        voyager.run_voyager(
            tmp_path,
            ["xenia", "live", "hero", "--voyager"],
        )

    manifests = tuple(tmp_path.glob("runs/*/manifest.json"))
    assert len(manifests) == 1
    failed = RunManifest.model_validate_json(manifests[0].read_text(encoding="utf-8"))
    assert failed.outcome == "failed"
    assert failed.experiment_id == "EXP-001"
    assert failed.parameters["mirror_provenance"]["git_blob_sha1"] == (
        voyager.SOURCE_MIRROR_BLOB_SHA1
    )
    assert any(item.path.endswith("failure.json") for item in failed.outputs)
    failure = json.loads((manifests[0].parent / "failure.json").read_text(encoding="utf-8"))
    assert failure["error_type"] == "RemoteReadError"
    assert failure["source_header"] is None


def test_waterfall_plot_is_exact_size_and_uses_hdf5_slice(tmp_path: Path) -> None:
    slice_path = tmp_path / "tiny.h5"
    output_path = tmp_path / "hero.png"
    values = np.arange(16 * 8, dtype="<f4").reshape(16, 1, 8)
    with h5py.File(slice_path, "w") as h5:
        dataset = h5.create_dataset("data", data=values)
        dataset.attrs["fch1"] = np.float64(8420.0)
        dataset.attrs["foff"] = np.float64(-0.5)

    header = Hdf5FilterbankHeader(
        source_name="Voyager1",
        integrations=16,
        nifs=1,
        nchans=8,
        nbits=32,
        fch1_mhz=8420.0,
        foff_mhz=-0.5,
        tsamp_seconds=1.0,
        tstart_mjd=57650.0,
        dtype="<f4",
        chunk_shape=None,
        source_size_bytes=slice_path.stat().st_size,
        file_class="FILTERBANK",
        file_version="1.0",
        root_members=("data",),
        data_attributes=("fch1", "foff"),
    )
    info = Hdf5SliceInfo(
        header=header,
        channel_start=0,
        channel_count=8,
        first_center_mhz=8420.0,
        last_center_mhz=8416.5,
        output_size_bytes=slice_path.stat().st_size,
        output_sha256="c" * 64,
    )

    voyager._render_waterfall_png(slice_path, output_path, info, hit=None)

    png_header = output_path.read_bytes()[:24]
    assert png_header.startswith(b"\x89PNG\r\n\x1a\n")
    assert tuple(int.from_bytes(png_header[index : index + 4], "big") for index in (16, 20)) == (
        1280,
        720,
    )


def test_detector_failure_keeps_completed_slice_and_header_in_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_pipeline(monkeypatch, hit=None)

    def fail_detector(*args: object, **kwargs: object) -> DetectorResult:
        raise RuntimeError("synthetic detector failure")

    monkeypatch.setattr(voyager, "run_turboseti", fail_detector)

    with pytest.raises(RuntimeError, match="synthetic detector failure"):
        voyager.run_voyager(
            tmp_path,
            ["xenia", "live", "hero", "--voyager"],
        )

    manifest_path = next(tmp_path.glob("runs/*/manifest.json"))
    manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    slice_path = next(
        item.path for item in manifest.outputs if item.path.endswith("slice_summary.json")
    )
    slice_summary = json.loads((tmp_path / slice_path).read_text(encoding="utf-8"))
    failure = json.loads((manifest_path.parent / "failure.json").read_text(encoding="utf-8"))
    assert manifest.outcome == "failed"
    assert manifest.parameters["source_header"]["integrations"] == 16
    assert len(slice_summary["slice_sha256"]) == 64
    assert slice_summary["remote_transfer"]["bytes_transferred"] == 4096
    assert failure["source_header"]["integrations"] == 16
    assert failure["runtime"]["h5py"]
