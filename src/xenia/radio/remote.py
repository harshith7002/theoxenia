"""Bounded, measured HTTP byte-range access for public radio data."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

MAX_RANGE_BLOCK_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_TRANSFER_BYTES = 512 * 1024 * 1024


class RemoteReadError(RuntimeError):
    """Raised when a remote source cannot be read with bounded byte ranges."""


class SeekableByteReader(Protocol):
    """Small file protocol required by h5py and the SIGPROC slicer."""

    size: int

    def read(self, size: int = -1) -> bytes: ...

    def readinto(self, buffer: bytearray) -> int: ...

    def seek(self, offset: int, whence: int = 0) -> int: ...

    def tell(self) -> int: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ByteRange:
    """One successful range response, using a half-open byte interval."""

    start: int
    end_exclusive: int
    bytes_received: int


@dataclass(slots=True)
class RangeMetrics:
    """Actual network range responses recorded for one remote file handle."""

    source_url: str
    source_size_bytes: int
    max_transfer_bytes: int
    ranges: list[ByteRange] = field(default_factory=list)

    @property
    def bytes_transferred(self) -> int:
        """Return payload bytes received from the server, excluding cache hits."""
        return sum(item.bytes_received for item in self.ranges)

    def as_dict(self) -> dict[str, object]:
        """Return JSON-compatible range and byte-count evidence."""
        return {
            "source_url": self.source_url,
            "source_size_bytes": self.source_size_bytes,
            "max_transfer_bytes": self.max_transfer_bytes,
            "ranges": [
                {
                    "start": item.start,
                    "end_exclusive": item.end_exclusive,
                    "bytes_received": item.bytes_received,
                }
                for item in self.ranges
            ],
            "bytes_transferred": self.bytes_transferred,
        }


def _validate_url(url: str) -> None:
    """Allow HTTPS sources and loopback HTTP only for deterministic local tests."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("source URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URL must not contain embedded credentials")
    if parsed.scheme == "http" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("insecure HTTP is permitted only for loopback addresses")


@contextmanager
def open_counted_http_file(
    url: str,
    *,
    block_size: int = 1024 * 1024,
    max_transfer_bytes: int = DEFAULT_MAX_TRANSFER_BYTES,
) -> Iterator[tuple[SeekableByteReader, RangeMetrics]]:
    """Open a seekable HTTP file while measuring and capping network range reads.

    ``fsspec`` performs the HTTP Range requests and caches blocks. The cache's fetcher
    is wrapped so the returned ``RangeMetrics`` records only successful network
    responses, not reads served from the local block cache. Each fetch interval is
    half-open: ``[start, end_exclusive)``.

    The cap prevents an accidental full-file download. No fallback to streaming the
    full source is attempted if a server does not support byte ranges.
    """
    _validate_url(url)
    if not 0 < block_size <= MAX_RANGE_BLOCK_BYTES:
        raise ValueError(f"block_size must be in 1..{MAX_RANGE_BLOCK_BYTES} bytes")
    if max_transfer_bytes <= 0:
        raise ValueError("max_transfer_bytes must be positive")

    try:
        from fsspec.implementations.http import HTTPFileSystem
    except ImportError as exc:  # pragma: no cover - covered in environments without extra
        raise RemoteReadError("HTTP range access requires the optional xenia[radio] extra") from exc

    filesystem = HTTPFileSystem(
        block_size=block_size,
        cache_type="bytes",
        skip_instance_cache=True,
    )
    remote_file = None
    try:
        try:
            info = filesystem.info(url)
            source_size = int(info["size"])
            if source_size <= 0:
                raise RemoteReadError("remote source has no positive Content-Length")
            remote_file = filesystem.open(
                url,
                mode="rb",
                block_size=block_size,
                cache_type="bytes",
                size=source_size,
            )
        except RemoteReadError:
            raise
        except Exception as exc:
            raise RemoteReadError(f"could not open ranged source {url}: {exc}") from exc

        cache = getattr(remote_file, "cache", None)
        original_fetcher = getattr(cache, "fetcher", None)
        if cache is None or not callable(original_fetcher):
            raise RemoteReadError("unsupported fsspec HTTP cache; expected a bytes-cache fetcher")

        metrics = RangeMetrics(
            source_url=url,
            source_size_bytes=source_size,
            max_transfer_bytes=max_transfer_bytes,
        )

        def record_fetch(start: int, end_exclusive: int | None) -> bytes:
            if end_exclusive is None:
                end_exclusive = source_size
            if start < 0 or end_exclusive < start:
                raise RemoteReadError("HTTP range has invalid byte offsets")
            request_size = end_exclusive - start
            if request_size > MAX_RANGE_BLOCK_BYTES:
                raise RemoteReadError(
                    f"HTTP range of {request_size} bytes exceeds "
                    f"the {MAX_RANGE_BLOCK_BYTES}-byte cap"
                )
            try:
                payload = original_fetcher(start, end_exclusive)
            except Exception as exc:
                raise RemoteReadError(
                    f"HTTP range [{start}, {end_exclusive}) failed: {exc}"
                ) from exc
            if not isinstance(payload, bytes):
                raise RemoteReadError("HTTP range fetcher returned a non-bytes payload")
            maximum_available = max(0, min(end_exclusive, source_size) - start)
            if len(payload) > min(request_size, maximum_available):
                raise RemoteReadError("HTTP server returned more bytes than the requested range")
            metrics.ranges.append(ByteRange(start, end_exclusive, len(payload)))
            if metrics.bytes_transferred > max_transfer_bytes:
                raise RemoteReadError(
                    f"source transfer exceeded the {max_transfer_bytes}-byte safety limit"
                )
            return payload

        cache.fetcher = record_fetch
        yield remote_file, metrics
    finally:
        if remote_file is not None:
            with suppress(Exception):
                remote_file.close()
            session = getattr(remote_file, "session", None)
            loop = getattr(remote_file, "loop", None)
            if session is not None:
                with suppress(Exception):
                    HTTPFileSystem.close_session(loop, session)
