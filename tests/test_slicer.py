"""Offline tests for the cadence slicer. No network."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from xenia.live.slicer import CADENCE_ROLES, CadenceFile, slice_cadence


def _write_filterbank(path: Path, *, source_name: str, tstart: float) -> None:
    values = np.arange(16 * 64, dtype="<f4").reshape(16, 1, 64)
    with h5py.File(path, "w") as handle:
        handle.attrs["CLASS"] = "FILTERBANK"
        handle.attrs["VERSION"] = "1.0"
        dataset = handle.create_dataset("data", data=values, chunks=(1, 1, 16))
        dataset.attrs["source_name"] = source_name
        dataset.attrs["nchans"] = np.int64(64)
        dataset.attrs["nifs"] = np.int32(1)
        dataset.attrs["nbits"] = np.int32(32)
        dataset.attrs["fch1"] = np.float64(8420.0)
        dataset.attrs["foff"] = np.float64(-0.01)
        dataset.attrs["tsamp"] = np.float64(18.253611008)
        dataset.attrs["tstart"] = np.float64(tstart)


def _files(directory: Path) -> tuple[CadenceFile, ...]:
    names = ("HIP544", "HIP1024", "HIP544", "HIP114", "HIP544", "HIP1344")
    directory.mkdir(parents=True, exist_ok=True)
    items: list[CadenceFile] = []
    for index, (role, name) in enumerate(zip(CADENCE_ROLES, names, strict=True)):
        path = directory / f"scan-{index}.h5"
        _write_filterbank(path, source_name=name, tstart=57622.0 + index)
        items.append(
            CadenceFile(
                url=str(path),
                role=role,
                expected_source_name=name,
                catalog_md5=f"{index:032x}",
                catalog_size_bytes=path.stat().st_size,
            )
        )
    return tuple(items)


def test_public_http_is_refused_before_any_connection(tmp_path: Path) -> None:
    files = tuple(
        CadenceFile(
            url=f"http://bldata.berkeley.edu/not-a-real-file-{index}.h5",
            role=role,
            expected_source_name="HIP544",
        )
        for index, role in enumerate(CADENCE_ROLES)
    )
    with pytest.raises(ValueError, match="allow_plain_http is false"):
        slice_cadence(
            files,
            output_dir=tmp_path / "out",
            frequency_low_mhz=8419.7,
            frequency_high_mhz=8419.9,
        )
    with pytest.raises(ValueError, match="does not permit public HTTP"):
        slice_cadence(
            files,
            output_dir=tmp_path / "out",
            frequency_low_mhz=8419.7,
            frequency_high_mhz=8419.9,
            allow_plain_http=True,
        )


def test_local_cadence_slices_record_checksums_without_transfer(tmp_path: Path) -> None:
    slices = slice_cadence(
        _files(tmp_path / "src"),
        output_dir=tmp_path / "out",
        frequency_low_mhz=8419.7,
        frequency_high_mhz=8419.9,
    )

    assert tuple(item.role for item in slices) == CADENCE_ROLES
    assert all(item.transfer.bytes_transferred == 0 for item in slices)
    assert all(item.transfer.ranges == [] for item in slices)
    assert all(len(item.info.output_sha256) == 64 for item in slices)
    assert all(item.info.channel_count == 21 for item in slices)
    assert slices[0].info.header.source_name == "HIP544"
    assert slices[1].info.header.source_name == "HIP1024"
    first = slices[0]
    assert first.catalog_size_bytes == Path(first.url).stat().st_size
