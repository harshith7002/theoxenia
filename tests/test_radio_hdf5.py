"""Offline tests for the validated HDF5 filterbank slicer."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import h5py
import numpy as np
import pytest

from xenia.radio.hdf5 import slice_hdf5_filterbank


class _SizedFile:
    """Expose a local binary file through the sized, seekable source protocol."""

    def __init__(self, path: Path) -> None:
        self._stream: BinaryIO = path.open("rb")
        self.size = path.stat().st_size

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def readinto(self, buffer: bytearray) -> int:
        return self._stream.readinto(buffer)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._stream.seek(offset, whence)

    def tell(self) -> int:
        return self._stream.tell()

    def close(self) -> None:
        self._stream.close()


def _write_source(
    path: Path, *, integrations: int = 16, source_name: str = "Voyager1"
) -> np.ndarray:
    values = np.arange(integrations * 64, dtype="<f4").reshape(integrations, 1, 64)
    with h5py.File(path, "w") as h5:
        h5.attrs["CLASS"] = "FILTERBANK"
        h5.attrs["VERSION"] = "1.0"
        dataset = h5.create_dataset("data", data=values, chunks=(1, 1, 16))
        dataset.dims[0].label = "time"
        dataset.dims[1].label = "feed_id"
        dataset.dims[2].label = "frequency"
        dataset.attrs["source_name"] = source_name
        dataset.attrs["nchans"] = np.int64(64)
        dataset.attrs["nifs"] = np.int32(1)
        dataset.attrs["nbits"] = np.int32(32)
        dataset.attrs["fch1"] = np.float64(8420.0)
        dataset.attrs["foff"] = np.float64(-0.01)
        dataset.attrs["tsamp"] = np.float64(18.253611008)
        dataset.attrs["tstart"] = np.float64(57650.78209490741)
    return values


def _slice(
    source_path: Path,
    output_path: Path,
    *,
    frequency_low_mhz: float = 8419.7,
    frequency_high_mhz: float = 8419.9,
) -> object:
    source = _SizedFile(source_path)
    try:
        return slice_hdf5_filterbank(
            source,
            output_path=output_path,
            frequency_low_mhz=frequency_low_mhz,
            frequency_high_mhz=frequency_high_mhz,
            expected_source_name="Voyager1",
        )
    finally:
        source.close()


def test_slices_whole_channels_and_preserves_filterbank_metadata(tmp_path: Path) -> None:
    source_path = tmp_path / "source.h5"
    output_path = tmp_path / "slice.h5"
    expected_source = _write_source(source_path)

    info = _slice(source_path, output_path)

    assert info.channel_start == 10
    assert info.channel_count == 21
    assert info.first_center_mhz == pytest.approx(8419.9)
    assert info.last_center_mhz == pytest.approx(8419.7)
    assert info.header.integrations == 16
    assert info.header.chunk_shape == (1, 1, 16)
    assert info.output_size_bytes == output_path.stat().st_size
    assert len(info.output_sha256) == 64
    assert info.header.source_size_bytes == source_path.stat().st_size

    with h5py.File(output_path, "r") as h5:
        dataset = h5["data"]
        assert h5.attrs["CLASS"] == "FILTERBANK"
        assert h5.attrs["VERSION"] == "1.0"
        assert dataset.shape == (16, 1, 21)
        assert dataset.dtype == np.dtype("<f4")
        assert dataset.attrs["source_name"] == "Voyager1"
        assert dataset.attrs["nchans"] == 21
        assert dataset.attrs["nifs"] == 1
        assert dataset.attrs["nbits"] == 32
        assert dataset.attrs["fch1"] == pytest.approx(8419.9)
        assert dataset.attrs["foff"] == pytest.approx(-0.01)
        assert dataset[:].tobytes() == expected_source[:, :, 10:31].tobytes()
        assert tuple(dataset.dims[axis].label for axis in range(3)) == (
            "time",
            "feed_id",
            "frequency",
        )


def test_rejects_wrong_source_before_writing_a_slice(tmp_path: Path) -> None:
    source_path = tmp_path / "source.h5"
    output_path = tmp_path / "slice.h5"
    _write_source(source_path, source_name="HIP 12345")
    source = _SizedFile(source_path)
    try:
        with pytest.raises(ValueError, match="expected source_name='Voyager1'"):
            slice_hdf5_filterbank(
                source,
                output_path=output_path,
                frequency_low_mhz=8419.7,
                frequency_high_mhz=8419.9,
                expected_source_name="Voyager1",
            )
    finally:
        source.close()
    assert not output_path.exists()


def test_rejects_too_few_integrations_without_padding(tmp_path: Path) -> None:
    source_path = tmp_path / "two-integrations.h5"
    output_path = tmp_path / "slice.h5"
    _write_source(source_path, integrations=2)
    source = _SizedFile(source_path)
    try:
        with pytest.raises(ValueError, match="at least 4 integrations"):
            slice_hdf5_filterbank(
                source,
                output_path=output_path,
                frequency_low_mhz=8419.7,
                frequency_high_mhz=8419.9,
                expected_source_name="Voyager1",
            )
    finally:
        source.close()
    assert not output_path.exists()


def test_rejects_frequency_window_outside_source_band(tmp_path: Path) -> None:
    source_path = tmp_path / "source.h5"
    output_path = tmp_path / "slice.h5"
    _write_source(source_path)

    with pytest.raises(ValueError, match="contains no channel centers"):
        _slice(
            source_path,
            output_path,
            frequency_low_mhz=9000.0,
            frequency_high_mhz=9001.0,
        )
    assert not output_path.exists()
