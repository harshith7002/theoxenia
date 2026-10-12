"""Validated HDF5 filterbank metadata and bounded frequency-window slicing."""

from __future__ import annotations

import importlib
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Any

from xenia.radio.remote import SeekableByteReader
from xenia.radio.sigproc import _channel_interval


@dataclass(frozen=True, slots=True)
class Hdf5FilterbankHeader:
    """Schema-relevant metadata read from one Breakthrough Listen filterbank."""

    source_name: str
    integrations: int
    nifs: int
    nchans: int
    nbits: int
    fch1_mhz: float
    foff_mhz: float
    tsamp_seconds: float
    tstart_mjd: float
    dtype: str
    chunk_shape: tuple[int, int, int] | None
    source_size_bytes: int
    file_class: str
    file_version: str
    root_members: tuple[str, ...]
    data_attributes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return JSON-compatible source metadata for the experiment manifest."""
        return {
            "source_name": self.source_name,
            "integrations": self.integrations,
            "nifs": self.nifs,
            "nchans": self.nchans,
            "nbits": self.nbits,
            "fch1_mhz": self.fch1_mhz,
            "foff_mhz": self.foff_mhz,
            "tsamp_seconds": self.tsamp_seconds,
            "tstart_mjd": self.tstart_mjd,
            "dtype": self.dtype,
            "chunk_shape": None if self.chunk_shape is None else list(self.chunk_shape),
            "source_size_bytes": self.source_size_bytes,
            "file_class": self.file_class,
            "file_version": self.file_version,
            "root_members": list(self.root_members),
            "data_attributes": list(self.data_attributes),
        }


@dataclass(frozen=True, slots=True)
class Hdf5SliceInfo:
    """Metadata and checksum for a local, frequency-sliced HDF5 filterbank."""

    header: Hdf5FilterbankHeader
    channel_start: int
    channel_count: int
    first_center_mhz: float
    last_center_mhz: float
    output_size_bytes: int
    output_sha256: str

    def as_dict(self) -> dict[str, object]:
        """Return the compact slice provenance recorded with EXP-001."""
        return {
            "channel_start": self.channel_start,
            "channel_count": self.channel_count,
            "first_center_mhz": self.first_center_mhz,
            "last_center_mhz": self.last_center_mhz,
            "integrations": self.header.integrations,
            "nifs": self.header.nifs,
            "nbits": self.header.nbits,
            "dtype": self.header.dtype,
            "slice_size_bytes": self.output_size_bytes,
            "slice_sha256": self.output_sha256,
        }


def _text_attribute(value: Any, *, name: str) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"HDF5 attribute {name!r} must be a non-empty string")
    return value.strip()


def _number_attribute(value: Any, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"HDF5 attribute {name!r} must be numeric") from exc
    if not isfinite(result):
        raise ValueError(f"HDF5 attribute {name!r} must be finite")
    return result


def _integer_attribute(value: Any, *, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"HDF5 attribute {name!r} must be an integer") from exc
    if result <= 0:
        raise ValueError(f"HDF5 attribute {name!r} must be positive")
    return result


def _data_attribute(dataset: Any, file: Any, name: str) -> Any:
    if name in dataset.attrs:
        return dataset.attrs[name]
    if name in file.attrs:
        return file.attrs[name]
    raise ValueError(f"HDF5 filterbank is missing required attribute {name!r}")


def _read_header(file: Any, *, source_size_bytes: int) -> Hdf5FilterbankHeader:
    """Validate a filterbank file and extract its immutable source metadata."""
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - installed by the radio extra
        raise RuntimeError("HDF5 radio support requires NumPy; install xenia[radio]") from exc

    if "data" not in file:
        raise ValueError("HDF5 filterbank is missing /data")
    dataset = file["data"]
    if dataset.ndim != 3:
        raise ValueError(f"HDF5 /data must have rank 3; found rank {dataset.ndim}")
    integrations, nifs_in_shape, nchans_in_shape = (int(value) for value in dataset.shape)
    if nifs_in_shape != 1:
        raise ValueError(f"Voyager known-answer sample requires one IF; found {nifs_in_shape}")

    file_class = _text_attribute(file.attrs.get("CLASS"), name="CLASS")
    file_version = _text_attribute(file.attrs.get("VERSION"), name="VERSION")
    if file_class != "FILTERBANK":
        raise ValueError(f"expected HDF5 CLASS='FILTERBANK'; found {file_class!r}")
    try:
        float(file_version)
    except ValueError as exc:
        raise ValueError(f"HDF5 VERSION must be numeric; found {file_version!r}") from exc

    source_name = _text_attribute(_data_attribute(dataset, file, "source_name"), name="source_name")
    nchans = _integer_attribute(_data_attribute(dataset, file, "nchans"), name="nchans")
    nifs = _integer_attribute(_data_attribute(dataset, file, "nifs"), name="nifs")
    nbits = _integer_attribute(_data_attribute(dataset, file, "nbits"), name="nbits")
    if nchans != nchans_in_shape or nifs != nifs_in_shape:
        raise ValueError(
            "HDF5 shape and metadata disagree: "
            f"shape=({integrations}, {nifs_in_shape}, {nchans_in_shape}), "
            f"attributes=(nifs={nifs}, nchans={nchans})"
        )
    if nbits != 32 or np.dtype(dataset.dtype) != np.dtype("<f4"):
        raise ValueError(
            f"Voyager known-answer data must be 32-bit float; found nbits={nbits}, "
            f"dtype={dataset.dtype}"
        )

    fch1 = _number_attribute(_data_attribute(dataset, file, "fch1"), name="fch1")
    foff = _number_attribute(_data_attribute(dataset, file, "foff"), name="foff")
    if foff == 0:
        raise ValueError("HDF5 attribute 'foff' must be non-zero")
    tsamp = _number_attribute(_data_attribute(dataset, file, "tsamp"), name="tsamp")
    if tsamp <= 0:
        raise ValueError("HDF5 attribute 'tsamp' must be positive")
    tstart = _number_attribute(_data_attribute(dataset, file, "tstart"), name="tstart")
    chunks = None if dataset.chunks is None else tuple(int(value) for value in dataset.chunks)
    if chunks is not None and len(chunks) != 3:
        raise ValueError(f"HDF5 data chunks must be 3-dimensional, got {len(chunks)}")
    chunk_shape = None if chunks is None else (chunks[0], chunks[1], chunks[2])

    return Hdf5FilterbankHeader(
        source_name=source_name,
        integrations=integrations,
        nifs=nifs,
        nchans=nchans,
        nbits=nbits,
        fch1_mhz=fch1,
        foff_mhz=foff,
        tsamp_seconds=tsamp,
        tstart_mjd=tstart,
        dtype=np.dtype(dataset.dtype).str,
        chunk_shape=chunk_shape,
        source_size_bytes=source_size_bytes,
        file_class=file_class,
        file_version=file_version,
        root_members=tuple(sorted(str(name) for name in file)),
        data_attributes=tuple(sorted(str(name) for name in dataset.attrs)),
    )


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_attributes(source: Any, target: Any) -> None:
    """Copy attributes with their original HDF5 datatype and array shape."""
    for name in source.attrs:
        attribute = source.attrs.get_id(name)
        target.attrs.create(name, source.attrs[name], dtype=attribute.dtype)


def slice_hdf5_filterbank(
    source: SeekableByteReader,
    *,
    output_path: Path,
    frequency_low_mhz: Decimal | str | float,
    frequency_high_mhz: Decimal | str | float,
    expected_source_name: str,
    on_header: Callable[[Hdf5FilterbankHeader], None] | None = None,
) -> Hdf5SliceInfo:
    """Read only whole HDF5 frequency channels and write a temporary FILTERBANK slice.

    The original remote file is never downloaded. h5py reads through the supplied
    seekable range reader, and the new uncompressed HDF5 file is written atomically
    outside the repository by the caller.
    """
    try:
        importlib.import_module("hdf5plugin")
        import h5py
        import numpy as np
    except ImportError as exc:  # pragma: no cover - installed by the radio extra
        raise RuntimeError("HDF5 radio support requires h5py, hdf5plugin, and NumPy") from exc

    try:
        source_size_bytes = int(source.size)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("HDF5 source reader must expose a positive .size") from exc
    if source_size_bytes <= 0:
        raise ValueError("HDF5 source reader must expose a positive .size")

    low = Decimal(str(frequency_low_mhz))
    high = Decimal(str(frequency_high_mhz))
    if not low.is_finite() or not high.is_finite() or low > high:
        raise ValueError("frequency limits must be finite and low must not exceed high")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with h5py.File(source, "r") as input_file:
            header = _read_header(input_file, source_size_bytes=source_size_bytes)
            if on_header is not None:
                on_header(header)
            if header.source_name.casefold() != expected_source_name.casefold():
                raise ValueError(
                    f"expected source_name={expected_source_name!r}, found {header.source_name!r}"
                )
            if header.integrations < 4:
                raise ValueError(
                    f"turboSETI requires at least 4 integrations; "
                    f"HDF5 source has {header.integrations}"
                )
            data = input_file["data"]
            channel_start, channel_stop = _channel_interval(
                fch1=Decimal(str(header.fch1_mhz)),
                foff=Decimal(str(header.foff_mhz)),
                nchans=header.nchans,
                low=low,
                high=high,
            )
            channel_count = channel_stop - channel_start
            first_center = Decimal(str(header.fch1_mhz)) + channel_start * Decimal(
                str(header.foff_mhz)
            )
            last_center = Decimal(str(header.fch1_mhz)) + (channel_stop - 1) * Decimal(
                str(header.foff_mhz)
            )
            selected_data = np.asarray(data[:, :, channel_start:channel_stop])
            expected_shape = (header.integrations, header.nifs, channel_count)
            if selected_data.shape != expected_shape:
                raise ValueError(
                    f"selected HDF5 shape {selected_data.shape} does not match {expected_shape}"
                )

            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{output_path.name}.", suffix=".partial", dir=output_path.parent
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            with h5py.File(temporary_path, "w") as output_file:
                _copy_attributes(input_file, output_file)
                output_data = output_file.create_dataset(
                    "data",
                    data=selected_data,
                    chunks=(1, 1, min(header.chunk_shape[2], channel_count))
                    if header.chunk_shape is not None
                    else None,
                    dtype=data.dtype,
                )
                _copy_attributes(data, output_data)
                output_data.attrs.modify(
                    "fch1",
                    np.asarray(float(first_center), dtype=data.attrs["fch1"].dtype)[()],
                )
                output_data.attrs.modify(
                    "nchans",
                    np.asarray(channel_count, dtype=data.attrs["nchans"].dtype)[()],
                )
                output_file.flush()

        # Validate the generated file with the same reader used by turboSETI.
        from blimpy.io.hdf_reader import H5Reader

        validation_reader = H5Reader(str(temporary_path), load_data=False)
        try:
            if (
                validation_reader.n_ints_in_file != header.integrations
                or validation_reader.n_channels_in_file != channel_count
                or validation_reader.header["nifs"] != header.nifs
                or validation_reader.header["nbits"] != header.nbits
            ):
                raise ValueError("blimpy H5Reader reports inconsistent sliced filterbank metadata")
        finally:
            validation_reader.h5.close()

        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return Hdf5SliceInfo(
        header=header,
        channel_start=channel_start,
        channel_count=channel_count,
        first_center_mhz=float(first_center),
        last_center_mhz=float(last_center),
        output_size_bytes=output_path.stat().st_size,
        output_sha256=_hash_file(output_path),
    )
