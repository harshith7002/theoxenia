"""Slice one six-file cadence to a local frequency window.

The remote file is never downloaded whole. Each file is read through
``open_counted_http_file`` and ``slice_hdf5_filterbank``. The SHA-256 recorded
with a slice is the local slice, not the remote object. Public HTTP is refused.
This module does not decide whether a hit is a transmitter.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from xenia.radio.hdf5 import Hdf5SliceInfo, slice_hdf5_filterbank
from xenia.radio.remote import RangeMetrics, open_counted_http_file

# Applied per file. The spec's example figure is 256 MiB per pair; each file
# is opened on its own, so the same number is the per-file ceiling.
CADENCE_TRANSFER_CAP_BYTES = 256 * 1024 * 1024
CADENCE_ROLES = ("A", "B", "A", "C", "A", "D")
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True, slots=True)
class CadenceFile:
    """One scan to slice, in cadence order."""

    url: str
    role: str
    expected_source_name: str
    catalog_md5: str | None = None
    catalog_size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class CadenceSlice:
    """One local slice plus the transfer that produced it."""

    scan_index: int
    role: str
    url: str
    expected_source_name: str
    path: Path
    info: Hdf5SliceInfo
    transfer: RangeMetrics
    catalog_md5: str | None
    catalog_size_bytes: int | None


def slice_cadence(
    files: tuple[CadenceFile, ...],
    *,
    output_dir: Path,
    frequency_low_mhz: float,
    frequency_high_mhz: float,
    max_transfer_bytes: int = CADENCE_TRANSFER_CAP_BYTES,
    allow_plain_http: bool = False,
) -> tuple[CadenceSlice, ...]:
    """Write six local filterbank slices and return their checksums and ranges.

    ``allow_plain_http`` does not enable public HTTP. The range reader refuses
    it either way, because decision D-018 was not accepted. Loopback HTTP remains
    available for tests. Local filesystem paths skip the network.
    """
    _validate_request(
        files,
        frequency_low_mhz=frequency_low_mhz,
        frequency_high_mhz=frequency_high_mhz,
        max_transfer_bytes=max_transfer_bytes,
        allow_plain_http=allow_plain_http,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    slices: list[CadenceSlice] = []
    for index, item in enumerate(files):
        destination = output_dir / f"scan-{index}-{item.role}.h5"
        info, transfer = _slice_one(
            item,
            destination=destination,
            frequency_low_mhz=frequency_low_mhz,
            frequency_high_mhz=frequency_high_mhz,
            max_transfer_bytes=max_transfer_bytes,
        )
        slices.append(
            CadenceSlice(
                scan_index=index,
                role=item.role,
                url=item.url,
                expected_source_name=item.expected_source_name,
                path=destination,
                info=info,
                transfer=transfer,
                catalog_md5=item.catalog_md5,
                catalog_size_bytes=item.catalog_size_bytes,
            )
        )
    return tuple(slices)


def _validate_request(
    files: tuple[CadenceFile, ...],
    *,
    frequency_low_mhz: float,
    frequency_high_mhz: float,
    max_transfer_bytes: int,
    allow_plain_http: bool,
) -> None:
    if len(files) != 6:
        raise ValueError("an ABACAD cadence has six files")
    roles = tuple(item.role for item in files)
    if roles != CADENCE_ROLES:
        raise ValueError("cadence roles must be A B A C A D, on source first")
    if any(not item.expected_source_name.strip() for item in files):
        raise ValueError("each cadence file needs an expected source name")
    if frequency_low_mhz >= frequency_high_mhz:
        raise ValueError("frequency window must increase")
    if max_transfer_bytes <= 0:
        raise ValueError("max_transfer_bytes must be positive")
    for item in files:
        _reject_public_http(item.url, allow_plain_http=allow_plain_http)


def _reject_public_http(url: str, *, allow_plain_http: bool) -> None:
    """Refuse a public HTTP URL before any socket is opened."""
    parsed = urlsplit(url)
    if parsed.scheme != "http":
        return
    if parsed.hostname in _LOOPBACK_HOSTS:
        return
    if not allow_plain_http:
        raise ValueError(
            "public HTTP is refused because allow_plain_http is false; D-018 was not accepted"
        )
    raise ValueError("the range reader does not permit public HTTP; D-018 was not accepted")


def _slice_one(
    item: CadenceFile,
    *,
    destination: Path,
    frequency_low_mhz: float,
    frequency_high_mhz: float,
    max_transfer_bytes: int,
) -> tuple[Hdf5SliceInfo, RangeMetrics]:
    parsed = urlsplit(item.url)
    if parsed.scheme in {"http", "https"}:
        with open_counted_http_file(
            item.url,
            block_size=1024 * 1024,
            max_transfer_bytes=max_transfer_bytes,
        ) as (remote, metrics):
            info = slice_hdf5_filterbank(
                remote,
                output_path=destination,
                frequency_low_mhz=frequency_low_mhz,
                frequency_high_mhz=frequency_high_mhz,
                expected_source_name=item.expected_source_name,
            )
        return info, metrics

    path = Path(item.url)
    if not path.is_file():
        raise FileNotFoundError(f"cadence file does not exist: {item.url}")
    source = _LocalFile(path)
    try:
        info = slice_hdf5_filterbank(
            source,
            output_path=destination,
            frequency_low_mhz=frequency_low_mhz,
            frequency_high_mhz=frequency_high_mhz,
            expected_source_name=item.expected_source_name,
        )
    finally:
        source.close()
    return info, RangeMetrics(
        source_url=path.resolve().as_posix(),
        source_size_bytes=path.stat().st_size,
        max_transfer_bytes=0,
    )


class _LocalFile:
    """Seekable view of a local file, with the size h5py slicing requires."""

    def __init__(self, path: Path) -> None:
        self._stream = path.open("rb")
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
