"""SIGPROC filterbank parsing and bounded frequency-window slicing."""

from __future__ import annotations

import os
import struct
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

from xenia.radio.remote import SeekableByteReader

MAX_HEADER_BYTES = 1024 * 1024
COPY_CHUNK_BYTES = 64 * 1024
_SUPPORTED_NBITS = {8, 16, 32, 64}


@dataclass(frozen=True, slots=True)
class SigprocHeader:
    """Parsed filterbank header plus its exact original bytes and patch offsets."""

    fields: Mapping[str, object]
    raw: bytes
    data_offset: int
    nchans_value_offset: int
    fch1_value_offset: int


@dataclass(frozen=True, slots=True)
class FilterbankSliceInfo:
    """Metadata describing a newly written, frequency-sliced filterbank."""

    channel_start: int
    channel_count: int
    first_center_mhz: Decimal
    last_center_mhz: Decimal
    integrations: int
    nifs: int
    data_offset: int
    output_size_bytes: int
    source_size_bytes: int


def _read_next_header_keyword(source: SeekableByteReader):
    """Load blimpy's parser lazily so the base package stays lightweight."""
    try:
        from blimpy.io.sigproc import read_next_header_keyword
    except ImportError as exc:
        raise RuntimeError(
            "SIGPROC parsing requires blimpy; install the optional xenia[radio] extra"
        ) from exc
    return read_next_header_keyword(source)


def read_sigproc_header(source: SeekableByteReader) -> SigprocHeader:
    """Parse one SIGPROC header without reading any filterbank payload samples."""
    source.seek(0)
    keyword, _value, _value_offset = _read_next_header_keyword(source)
    if keyword != "HEADER_START":
        raise ValueError("SIGPROC file must begin with HEADER_START")

    fields: dict[str, object] = {keyword: 0}
    nchans_value_offset: int | None = None
    fch1_value_offset: int | None = None

    while True:
        if source.tell() > MAX_HEADER_BYTES:
            raise ValueError(f"SIGPROC header exceeds {MAX_HEADER_BYTES} bytes")
        try:
            keyword, value, value_offset = _read_next_header_keyword(source)
        except Exception as exc:
            raise ValueError(f"invalid or truncated SIGPROC header: {exc}") from exc

        if keyword == "HEADER_END":
            data_offset = source.tell()
            break

        fields[keyword] = value
        if keyword == "nchans":
            nchans_value_offset = value_offset
        elif keyword == "fch1":
            fch1_value_offset = value_offset

    if data_offset > MAX_HEADER_BYTES:
        raise ValueError(f"SIGPROC header exceeds {MAX_HEADER_BYTES} bytes")

    missing = {"nchans", "nifs", "nbits", "fch1", "foff"} - fields.keys()
    if missing:
        raise ValueError(f"SIGPROC header is missing required fields: {', '.join(sorted(missing))}")
    if nchans_value_offset is None or fch1_value_offset is None:
        raise ValueError("SIGPROC header is missing patch offsets for nchans or fch1")

    nchans = int(fields["nchans"])
    nifs = int(fields["nifs"])
    nbits = int(fields["nbits"])
    fch1 = Decimal(str(fields["fch1"]))
    foff = Decimal(str(fields["foff"]))
    if nchans <= 0 or nifs <= 0:
        raise ValueError("SIGPROC nchans and nifs must be positive")
    if nbits not in _SUPPORTED_NBITS:
        raise ValueError(f"unsupported SIGPROC nbits={nbits}; expected 8, 16, 32, or 64")
    if not fch1.is_finite() or not foff.is_finite() or foff == 0:
        raise ValueError("SIGPROC fch1 and non-zero foff must be finite")

    source.seek(0)
    raw = source.read(data_offset)
    if len(raw) != data_offset:
        raise ValueError("source ended while copying the SIGPROC header")
    source.seek(data_offset)
    return SigprocHeader(
        fields=fields,
        raw=raw,
        data_offset=data_offset,
        nchans_value_offset=nchans_value_offset,
        fch1_value_offset=fch1_value_offset,
    )


def _decimal(value: Decimal | str | float) -> Decimal:
    """Convert a user/header frequency without introducing binary-float math."""
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("frequency values must be finite")
    return result


def _channel_interval(
    *, fch1: Decimal, foff: Decimal, nchans: int, low: Decimal, high: Decimal
) -> tuple[int, int]:
    """Return the half-open index interval whose centers fall inside [low, high]."""
    if low > high:
        raise ValueError("frequency_low_mhz must not exceed frequency_high_mhz")
    step = abs(foff)
    if foff > 0:
        first_index = ((low - fch1) / step).to_integral_value(rounding=ROUND_CEILING)
        stop_index = ((high - fch1) / step).to_integral_value(rounding=ROUND_FLOOR) + 1
    else:
        first_index = ((fch1 - high) / step).to_integral_value(rounding=ROUND_CEILING)
        stop_index = ((fch1 - low) / step).to_integral_value(rounding=ROUND_FLOOR) + 1

    start = max(0, min(nchans, int(first_index)))
    stop = max(0, min(nchans, int(stop_index)))
    if start >= stop:
        raise ValueError("requested frequency window contains no channel centers")
    return start, stop


def slice_filterbank(
    source: SeekableByteReader,
    *,
    output_path: Path,
    frequency_low_mhz: Decimal | str | float,
    frequency_high_mhz: Decimal | str | float,
) -> FilterbankSliceInfo:
    """Write only samples whose channel centers lie within an inclusive MHz window.

    The source is seeked by row and IF; the complete filterbank is never read into
    memory or written to disk. The output header is copied exactly except for its
    channel count and first-channel center frequency.
    """
    header = read_sigproc_header(source)
    fields = header.fields
    nchans = int(fields["nchans"])
    nifs = int(fields["nifs"])
    nbits = int(fields["nbits"])
    fch1 = _decimal(fields["fch1"])
    foff = _decimal(fields["foff"])
    low = _decimal(frequency_low_mhz)
    high = _decimal(frequency_high_mhz)

    channel_start, channel_stop = _channel_interval(
        fch1=fch1,
        foff=foff,
        nchans=nchans,
        low=low,
        high=high,
    )
    channel_count = channel_stop - channel_start
    first_center = fch1 + channel_start * foff
    last_center = fch1 + (channel_stop - 1) * foff

    source_size = int(source.size)
    bytes_per_sample = nbits // 8
    bytes_per_integration = nifs * nchans * bytes_per_sample
    payload_bytes = source_size - header.data_offset
    if payload_bytes <= 0 or payload_bytes % bytes_per_integration:
        raise ValueError("SIGPROC payload is not a positive whole number of integrations")
    integrations = payload_bytes // bytes_per_integration

    output_header = bytearray(header.raw)
    struct.pack_into("<i", output_header, header.nchans_value_offset, channel_count)
    struct.pack_into("<d", output_header, header.fch1_value_offset, float(first_center))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.", suffix=".partial", dir=output_path.parent
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as output:
            output.write(output_header)
            selected_bytes = channel_count * bytes_per_sample
            for integration in range(integrations):
                for if_index in range(nifs):
                    plane_offset = (
                        header.data_offset
                        + ((integration * nifs + if_index) * nchans + channel_start)
                        * bytes_per_sample
                    )
                    source.seek(plane_offset)
                    remaining = selected_bytes
                    while remaining:
                        chunk = source.read(min(COPY_CHUNK_BYTES, remaining))
                        if not chunk:
                            raise ValueError(
                                "unexpected EOF while reading selected channel samples"
                            )
                        if len(chunk) > remaining:
                            raise ValueError("source reader returned more bytes than requested")
                        output.write(chunk)
                        remaining -= len(chunk)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return FilterbankSliceInfo(
        channel_start=channel_start,
        channel_count=channel_count,
        first_center_mhz=first_center,
        last_center_mhz=last_center,
        integrations=integrations,
        nifs=nifs,
        data_offset=header.data_offset,
        output_size_bytes=output_path.stat().st_size,
        source_size_bytes=source_size,
    )
