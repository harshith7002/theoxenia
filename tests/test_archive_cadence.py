"""Known-answer tests for archive cadence labelling. The search is stubbed."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from xenia.live.archive_cadence import ScanClock, label_hits, project_hz, run_archive_cadence
from xenia.live.known_sources import KnownCatalog, KnownRange
from xenia.live.models import Verdict
from xenia.live.search import CadenceSearch, FilterEvent, ScanDetection
from xenia.live.slicer import CadenceFile

_EPOCH = 57622.0


def _clocks() -> tuple[ScanClock, ...]:
    roles = ("A", "B", "A", "C", "A", "D")
    return tuple(
        ScanClock(scan_index=index, role=role, tstart_mjd=_EPOCH + (300.0 * index) / 86400.0)
        for index, role in enumerate(roles)
    )


def _detection(
    scan_index: int, frequency_mhz: float, drift_hz_s: float, snr: float
) -> ScanDetection:
    role = ("A", "B", "A", "C", "A", "D")[scan_index]
    return ScanDetection(
        scan_index=scan_index,
        role=role,
        on_source=role == "A",
        frequency_mhz=frequency_mhz,
        drift_hz_s=drift_hz_s,
        snr=snr,
    )


def test_projection_removes_a_known_drift() -> None:
    later = _EPOCH + 600.0 / 86400.0
    projected = project_hz(1400.0006, 1.0, later, _EPOCH)
    assert projected == pytest.approx(1400.0 * 1_000_000.0)


def test_labels_follow_measured_membership_not_the_filter_flag() -> None:
    clocks = _clocks()
    detections = (
        _detection(0, 1400.0, 1.0, 30.0),
        _detection(2, 1400.0006, 1.0, 28.0),
        _detection(4, 1400.0012, 1.0, 25.0),
        _detection(0, 1401.0, 0.0, 40.0),
        _detection(1, 1401.0, 0.0, 39.0),
        _detection(0, 1402.0, 0.2, 12.0),
        _detection(0, 1392.0, 0.2, 22.0),
        _detection(2, 1392.0 + 600.0 / 1e6, 0.2, 21.0),
        _detection(4, 1392.0 + 1200.0 / 1e6, 0.2, 20.0),
    )
    events = (
        FilterEvent("on", 1400.0, 1.0, 30.0),
        FilterEvent("known", 1392.0, 0.2, 22.0),
        FilterEvent("orphan", 1403.0, 0.5, 50.0),
    )
    catalog = KnownCatalog(
        ranges=(
            KnownRange(
                name="test range",
                freq_min_mhz=1390.0,
                freq_max_mhz=1395.0,
                source="unit test",
            ),
        ),
        downlinks=(),
    )
    hits = label_hits(
        CadenceSearch(detections=detections, events=events, warnings=()),
        clocks,
        catalog,
        cadence_id="bl-test",
    )
    by_freq = {round(hit.frequency_mhz, 3): hit for hit in hits}

    on_only = by_freq[1400.0]
    assert on_only.decision.verdict is Verdict.ON_ONLY
    assert on_only.on_count == 3
    assert on_only.off_count == 0
    assert on_only.passed_filter is True

    in_off = by_freq[1401.0]
    assert in_off.decision.verdict is Verdict.IN_OFF
    assert in_off.off_count == 1
    assert in_off.passed_filter is False

    single = by_freq[1402.0]
    assert single.decision.verdict is Verdict.SINGLE_POINTING
    assert single.on_count == 1

    known = by_freq[1392.0]
    assert known.decision.verdict is Verdict.KNOWN_SOURCE
    assert known.decision.known_source == "test range"

    orphan = by_freq[1403.0]
    assert orphan.on_count == 0
    assert orphan.off_count == 0
    assert orphan.passed_filter is True
    assert orphan.decision.verdict is Verdict.SINGLE_POINTING
    assert "implied 3 and 0" in orphan.association_note
    assert all(hit.decision.verdict is not Verdict.UNEXPLAINED for hit in hits)
    assert all(hit.decision.checks_done == 4 for hit in hits)


def _local_files(directory: Path) -> tuple[CadenceFile, ...]:
    import h5py
    import numpy as np

    directory.mkdir(parents=True, exist_ok=True)
    names = ("HIP544", "HIP1024", "HIP544", "HIP114", "HIP544", "HIP1344")
    roles = ("A", "B", "A", "C", "A", "D")
    items: list[CadenceFile] = []
    for index, (role, name) in enumerate(zip(roles, names, strict=True)):
        path = directory / f"scan-{index}.h5"
        values = np.arange(16 * 64, dtype="<f4").reshape(16, 1, 64)
        with h5py.File(path, "w") as handle:
            handle.attrs["CLASS"] = "FILTERBANK"
            handle.attrs["VERSION"] = "1.0"
            dataset = handle.create_dataset("data", data=values, chunks=(1, 1, 16))
            dataset.attrs["source_name"] = name
            dataset.attrs["nchans"] = np.int64(64)
            dataset.attrs["nifs"] = np.int32(1)
            dataset.attrs["nbits"] = np.int32(32)
            dataset.attrs["fch1"] = np.float64(8420.0)
            dataset.attrs["foff"] = np.float64(-0.01)
            dataset.attrs["tsamp"] = np.float64(18.253611008)
            dataset.attrs["tstart"] = np.float64(57622.0 + index)
        items.append(CadenceFile(url=str(path), role=role, expected_source_name=name))
    return tuple(items)


def test_local_archive_run_writes_parquet_and_deletes_the_work_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = _local_files(tmp_path / "src")

    def fake_search(scans: tuple[object, ...], *, work_dir: Path) -> CadenceSearch:
        assert len(scans) == 6
        assert work_dir.name == "search"
        return CadenceSearch(
            detections=(_detection(0, 8419.8, 0.4, 20.0),),
            events=(),
            warnings=(),
        )

    monkeypatch.setattr("xenia.live.archive_cadence.search_cadence", fake_search)
    catalog_path = tmp_path / "known_sources.yaml"
    catalog_path.write_text("ranges: []\ndownlinks: []\n", encoding="utf-8")

    manifest, manifest_path = run_archive_cadence(
        tmp_path,
        ["xenia", "live", "cadence"],
        files=tuple(item.url for item in sources),
        sources=tuple(item.expected_source_name for item in sources),
        roles=tuple(item.role for item in sources),
        window_mhz=(8419.7, 8419.9),
        target="HIP544",
        ra_deg=1.6549208333,
        dec_deg=29.0205625,
        experiment_id="EXP-003",
        cadence_id="bl-test",
        known_sources_path=catalog_path,
    )

    assert manifest.demo is False
    assert manifest.outcome == "searched"
    assert manifest.experiment_id == "EXP-003"
    assert manifest.parameters["verdict_counts"] == {
        "KNOWN_SOURCE": 0,
        "IN_OFF": 0,
        "SINGLE_POINTING": 1,
        "RFI_CENSUS": 0,
        "ON_ONLY": 0,
        "UNEXPLAINED": 0,
    }
    assert manifest.mission_control is not None
    assert manifest.mission_control.kind == "cadence"
    assert manifest.mission_control.target == "HIP544"
    assert len(manifest.inputs) == 6
    frame = pl.read_parquet(manifest_path.parent / "hits.parquet")
    assert frame.height == 1
    assert frame["verdict"][0] == "SINGLE_POINTING"
    assert frame["checks_done"][0] == 4
    assert frame["review"][0] is False
    assert not (tmp_path / "data" / "tmp" / "exp-003-bl-test").exists()
    assert manifest_path.is_file()
    second, second_path = run_archive_cadence(
        tmp_path,
        ["xenia", "live", "cadence"],
        files=tuple(item.url for item in sources),
        sources=tuple(item.expected_source_name for item in sources),
        roles=tuple(item.role for item in sources),
        window_mhz=(8419.75, 8419.85),
        target="HIP544",
        ra_deg=1.6549208333,
        dec_deg=29.0205625,
        experiment_id="EXP-003",
        cadence_id="bl-test",
        known_sources_path=catalog_path,
    )
    second_frame = pl.read_parquet(second_path.parent / "hits.parquet")
    assert second.mission_control.cadence_id == manifest.mission_control.cadence_id
    assert set(frame["hit_id"]).isdisjoint(second_frame["hit_id"])


def test_archive_run_refuses_public_http_and_removes_its_work_tree(tmp_path: Path) -> None:
    catalog_path = tmp_path / "known_sources.yaml"
    catalog_path.write_text("ranges: []\ndownlinks: []\n", encoding="utf-8")
    urls = tuple(f"http://seti.berkeley.edu/opendata/file-{index}.h5" for index in range(6))
    with pytest.raises(ValueError, match="D-018 was not accepted"):
        run_archive_cadence(
            tmp_path,
            ["xenia", "live", "cadence"],
            files=urls,
            sources=("HIP544",) * 6,
            roles=("A", "B", "A", "C", "A", "D"),
            window_mhz=(1380.0, 1381.0),
            target="HIP544",
            ra_deg=1.65,
            dec_deg=29.0,
            experiment_id="EXP-003",
            cadence_id="bl-http",
            known_sources_path=catalog_path,
        )
    assert not (tmp_path / "data" / "tmp" / "exp-003-bl-http").exists()
