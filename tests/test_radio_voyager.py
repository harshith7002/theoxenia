"""Offline tests for the EXP-001 orchestration and provenance behavior."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from xenia.live.models import HeroPayload
from xenia.radio import voyager
from xenia.radio.detector import DetectorArtifact, DetectorResult, DopplerHit
from xenia.radio.remote import ByteRange, RangeMetrics, RemoteReadError
from xenia.radio.sigproc import FilterbankSliceInfo, SigprocHeader


class _RemotePlaceholder:
    size = 528_482_692


def _install_fake_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    hit: DopplerHit | None,
) -> None:
    remote = _RemotePlaceholder()
    metrics = RangeMetrics(
        source_url=voyager.OFFICIAL_SOURCE_URL,
        source_size_bytes=remote.size,
        max_transfer_bytes=voyager.REMOTE_TRANSFER_LIMIT_BYTES,
        ranges=[ByteRange(start=0, end_exclusive=4096, bytes_received=4096)],
    )

    @contextmanager
    def fake_open(
        *args: object, **kwargs: object
    ) -> Iterator[tuple[_RemotePlaceholder, RangeMetrics]]:
        assert args[0] == voyager.OFFICIAL_SOURCE_URL
        assert kwargs["block_size"] == voyager.REMOTE_BLOCK_SIZE_BYTES
        yield remote, metrics

    header = SigprocHeader(
        fields={
            "source_name": "VOYAGER1",
            "nchans": 16,
            "nifs": 1,
            "nbits": 32,
            "fch1": 8588.964842330843,
            "foff": -2.838316417875744e-06,
            "tsamp": 105.6964608,
            "tstart": 57386.864907407406,
        },
        raw=b"header",
        data_offset=6,
        nchans_value_offset=0,
        fch1_value_offset=0,
    )

    def fake_slice(
        source: _RemotePlaceholder, *, output_path: Path, **kwargs: object
    ) -> FilterbankSliceInfo:
        output_path.write_bytes(b"temporary-slice-data")
        return FilterbankSliceInfo(
            channel_start=5,
            channel_count=2,
            first_center_mhz=8419.00001,
            last_center_mhz=8419.00000,
            integrations=2,
            nifs=1,
            data_offset=6,
            output_size_bytes=22,
            source_size_bytes=remote.size,
        )

    result_hit = () if hit is None else (hit,)
    result = DetectorResult(
        hits=result_hit,
        artifacts=(DetectorArtifact(filename="slice.dat", sha256="a" * 64, size_bytes=42),),
        turbo_seti_version="2.3.2",
        blimpy_version="2.1.4",
    )

    def fake_detector(*args: object, **kwargs: object) -> DetectorResult:
        assert kwargs["max_drift_hz_s"] == 4.0
        assert kwargs["minimum_snr"] == 25.0
        return result

    def fake_plot(slice_path: Path, output_path: Path, *args: object, **kwargs: object) -> None:
        assert slice_path.is_file()
        output_path.write_bytes(b"synthetic-png")

    monkeypatch.setattr(voyager, "open_counted_http_file", fake_open)
    monkeypatch.setattr(voyager, "read_sigproc_header", lambda _source: header)
    monkeypatch.setattr(voyager, "slice_filterbank", fake_slice)
    monkeypatch.setattr(voyager, "run_turboseti", fake_detector)
    monkeypatch.setattr(voyager, "_render_waterfall_png", fake_plot)


def test_voyager_run_writes_linked_hero_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hit = DopplerHit(
        top_hit=1,
        drift_hz_s=-0.392226,
        snr=30.612,
        uncorrected_frequency_mhz=8419.319368,
        corrected_frequency_mhz=8419.319369,
        frequency_start_mhz=8419.319,
        frequency_end_mhz=8419.320,
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
    assert manifest.inputs[0].uri == voyager.OFFICIAL_SOURCE_URL
    assert manifest.inputs[0].size_bytes == 528_482_692
    assert isinstance(manifest.mission_control, HeroPayload)
    assert manifest.mission_control.freq_mhz == pytest.approx(8419.319368)
    assert manifest.mission_control.image_url.endswith("/hero.png")
    assert all((tmp_path / item.path).is_file() for item in manifest.outputs if item.sha256)
    assert not list(tmp_path.rglob("*.fil"))


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
    from xenia.live.models import RunManifest

    failed = RunManifest.model_validate_json(manifests[0].read_text(encoding="utf-8"))
    assert failed.outcome == "failed"
    assert failed.experiment_id == "EXP-001"
    assert any(item.path.endswith("failure.json") for item in failed.outputs)


def test_waterfall_plot_is_exact_size_and_uses_synthetic_slice(tmp_path: Path) -> None:
    import struct

    slice_path = tmp_path / "tiny.fil"
    output_path = tmp_path / "hero.png"
    slice_path.write_bytes(b"header" + struct.pack("<4f", 1.0, 2.0, 3.0, 4.0))
    info = FilterbankSliceInfo(
        channel_start=0,
        channel_count=2,
        first_center_mhz=2.0,
        last_center_mhz=1.5,
        integrations=2,
        nifs=1,
        data_offset=6,
        output_size_bytes=22,
        source_size_bytes=22,
    )

    voyager._render_waterfall_png(
        slice_path,
        output_path,
        info,
        nbits=32,
        foff_mhz=-0.5,
        tsamp_seconds=1.0,
        hit=None,
    )

    png_header = output_path.read_bytes()[:24]
    assert png_header.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", png_header[16:24]) == (1280, 720)
