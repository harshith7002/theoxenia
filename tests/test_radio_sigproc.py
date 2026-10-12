"""Offline tests for SIGPROC parsing and frequency-window slicing."""

from __future__ import annotations

import io
import struct
from pathlib import Path

import pytest
from blimpy.io.sigproc import header_keyword_types

from xenia.radio.sigproc import read_sigproc_header, slice_filterbank


class _MemoryReader:
    """Small seekable byte reader with the size attribute used by the slicer."""

    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)
        self.size = len(payload)

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._buffer.seek(offset, whence)

    def tell(self) -> int:
        return self._buffer.tell()

    def close(self) -> None:
        self._buffer.close()


def _write_text(output: bytearray, value: str) -> None:
    encoded = value.encode("ascii")
    output.extend(struct.pack("<I", len(encoded)))
    output.extend(encoded)


def _write_keyword(output: bytearray, name: str, value: int | float | str | None = None) -> None:
    _write_text(output, name)
    if name in {"HEADER_START", "HEADER_END"}:
        return
    kind = header_keyword_types[name]
    if kind == "<l":
        output.extend(struct.pack("<i", int(value)))
    elif kind in {"<d", "angle"}:
        output.extend(struct.pack("<d", float(value)))
    elif kind == "str":
        _write_text(output, str(value))
    else:
        raise AssertionError(f"unsupported test keyword type: {kind}")


def _make_filterbank(
    *,
    nchans: int = 10,
    nifs: int = 1,
    nbits: int = 8,
    fch1: float = 1400.0,
    foff: float = -0.5,
    add_trailing_bytes: int = 0,
) -> _MemoryReader:
    header = bytearray()
    _write_keyword(header, "HEADER_START")
    _write_keyword(header, "source_name", "synthetic")
    _write_keyword(header, "nchans", nchans)
    _write_keyword(header, "nifs", nifs)
    _write_keyword(header, "nbits", nbits)
    _write_keyword(header, "fch1", fch1)
    _write_keyword(header, "foff", foff)
    _write_keyword(header, "HEADER_END")

    if nbits == 8:
        payload = bytearray()
        for integration in range(2):
            for if_index in range(nifs):
                for channel in range(nchans):
                    payload.append((integration * 40 + if_index * 20 + channel) % 256)
    else:
        payload = bytearray(nifs * nchans * (nbits // 8) * 2)
    payload.extend(b"\x00" * add_trailing_bytes)
    return _MemoryReader(bytes(header) + bytes(payload))


def _read_output(path: Path) -> tuple[dict[str, object], bytes, int]:
    reader = _MemoryReader(path.read_bytes())
    header = read_sigproc_header(reader)
    return dict(header.fields), reader.read(), header.data_offset


def test_header_parser_retains_fields_offsets_and_raw_bytes() -> None:
    source = _make_filterbank()
    header = read_sigproc_header(source)

    assert header.fields["nchans"] == 10
    assert header.fields["nifs"] == 1
    assert header.fields["nbits"] == 8
    assert header.raw.startswith(struct.pack("<I", len("HEADER_START")))
    assert header.data_offset == len(header.raw)
    assert 0 <= header.nchans_value_offset < header.data_offset - 4
    assert 0 <= header.fch1_value_offset < header.data_offset - 8


def test_negative_foff_slices_only_selected_channels_and_patches_header(tmp_path: Path) -> None:
    source = _make_filterbank(nchans=10, nifs=1, fch1=1400.0, foff=-0.5)
    output = tmp_path / "negative.foff.fil"

    info = slice_filterbank(
        source,
        output_path=output,
        frequency_low_mhz="1398.5",
        frequency_high_mhz="1399.5",
    )

    fields, payload, data_offset = _read_output(output)
    assert info.channel_start == 1
    assert info.channel_count == 3
    assert info.first_center_mhz == 1399.5
    assert info.last_center_mhz == 1398.5
    assert fields["nchans"] == 3
    assert fields["fch1"] == pytest.approx(1399.5)
    assert fields["foff"] == pytest.approx(-0.5)
    assert data_offset == info.data_offset
    assert payload == bytes([1, 2, 3, 41, 42, 43])
    assert info.output_size_bytes == data_offset + len(payload)
    assert info.source_size_bytes > info.output_size_bytes


def test_positive_foff_slices_each_if_plane_in_time_order(tmp_path: Path) -> None:
    source = _make_filterbank(nchans=16, nifs=2, fch1=1200.0, foff=0.25)
    output = tmp_path / "positive.foff.fil"

    info = slice_filterbank(
        source,
        output_path=output,
        frequency_low_mhz=1200.5,
        frequency_high_mhz=1201.0,
    )

    fields, payload, _ = _read_output(output)
    assert info.channel_start == 2
    assert info.channel_count == 3
    assert info.integrations == 2
    assert info.nifs == 2
    assert fields["fch1"] == pytest.approx(1200.5)
    assert payload == bytes([2, 3, 4, 22, 23, 24, 42, 43, 44, 62, 63, 64])


def test_window_without_channel_centers_is_rejected_without_output(tmp_path: Path) -> None:
    source = _make_filterbank(nchans=4, fch1=1000.0, foff=1.0)
    output = tmp_path / "outside.fil"

    with pytest.raises(ValueError, match="no channel centers"):
        slice_filterbank(
            source,
            output_path=output,
            frequency_low_mhz=2000.0,
            frequency_high_mhz=3000.0,
        )
    assert not output.exists()


def test_reversed_frequency_interval_is_rejected(tmp_path: Path) -> None:
    source = _make_filterbank()
    with pytest.raises(ValueError, match="must not exceed"):
        slice_filterbank(
            source,
            output_path=tmp_path / "invalid.fil",
            frequency_low_mhz=1400.0,
            frequency_high_mhz=1399.0,
        )


def test_unsupported_sample_width_is_rejected() -> None:
    source = _make_filterbank(nbits=12)
    with pytest.raises(ValueError, match="unsupported SIGPROC nbits"):
        read_sigproc_header(source)


def test_non_integral_payload_length_is_rejected(tmp_path: Path) -> None:
    source = _make_filterbank(nchans=8, nifs=1, nbits=8, add_trailing_bytes=1)
    with pytest.raises(ValueError, match="whole number of integrations"):
        slice_filterbank(
            source,
            output_path=tmp_path / "truncated.fil",
            frequency_low_mhz=1399.0,
            frequency_high_mhz=1400.0,
        )
