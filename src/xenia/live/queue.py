"""Build a breadth-first queue of (cadence, window) pairs.

A window is emitted only when a measured file band contains it. A catalog
centre frequency is not a band. The synthetic queue is a separate path and
says so on every line.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from xenia.live.config import LiveConfig
from xenia.radio.floor_config import (
    FRAME_FCH1_MHZ,
    FREQUENCY_CHANNELS,
    FREQUENCY_RESOLUTION_HZ,
)

FINE_SUFFIX = ".gpuspec.0000.h5"
ROLES = ("A", "B", "A", "C", "A", "D")
_MAX_LISTING_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class QueuePair:
    """One searchable pair. ``files`` is empty for a synthetic cadence."""

    cadence_id: str
    target: str
    ra_deg: float
    dec_deg: float
    receiver: str
    window_mhz: tuple[float, float]
    priority: int
    synthetic: bool
    files: tuple[str, ...]
    roles: tuple[str, ...]
    sources: tuple[str, ...]
    catalog_md5: tuple[str, ...]
    catalog_size_bytes: tuple[int, ...]
    band_coverage: str


def synthetic_frame_band_mhz() -> tuple[float, float]:
    """Return the generated EXP-004 band, high edge included.

    The generator writes ``fch1`` at 6000 MHz and steps down by one channel.
    """
    span_mhz = (FREQUENCY_CHANNELS - 1) * FREQUENCY_RESOLUTION_HZ / 1e6
    return (FRAME_FCH1_MHZ - span_mhz, FRAME_FCH1_MHZ)


def fetch_listing(url: str, *, timeout_seconds: float = 60.0) -> bytes:
    """Download a catalog listing. Public HTTP is the publisher's catalog, not a filterbank."""
    if not url.startswith(("https://", "http://")):
        raise ValueError("listing URL must be http or https")
    request = Request(url, headers={"User-Agent": "theoxenia-queue/1"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        payload = response.read(_MAX_LISTING_BYTES + 1)
    if len(payload) > _MAX_LISTING_BYTES:
        raise ValueError(f"listing exceeded {_MAX_LISTING_BYTES} bytes and was not parsed")
    return payload


def build_listing_queue(
    listing: bytes,
    *,
    config: LiveConfig,
    listing_url: str,
    receiver: str,
    limit: int,
    cadence_id: str | None = None,
) -> str:
    """Turn one catalog JSON document into JSONL. The header records the listing hash."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    rows = _rows(listing)
    groups = _group_rows(rows, cadence_id=cadence_id)
    measured = {band.cadence_id: band for band in config.measured_file_bands}
    starts = config.window_starts(receiver)
    pairs: list[QueuePair] = []
    queued_ids: set[str] = set()
    skipped_outside = 0
    for group_id in sorted(groups):
        selected = _fine_abacad(groups[group_id])
        if selected is None:
            continue
        full_id = group_id if group_id.startswith("bl-opendata-") else f"bl-opendata-{group_id}"
        band = measured.get(full_id)
        if band is None:
            continue
        queued_ids.add(full_id)
        for index, start in enumerate(starts):
            window = (start, start + config.window_mhz)
            if window[0] < band.low_mhz or window[1] > band.high_mhz:
                skipped_outside += 1
                continue
            first = selected[0]
            pairs.append(
                QueuePair(
                    cadence_id=full_id,
                    target=str(first["target"]),
                    ra_deg=float(first["ra"]),
                    dec_deg=float(first["decl"]),
                    receiver=receiver,
                    window_mhz=window,
                    priority=index,
                    synthetic=False,
                    files=tuple(str(row["url"]) for row in selected),
                    roles=ROLES,
                    sources=tuple(str(row["target"]) for row in selected),
                    catalog_md5=tuple(str(row["md5sum"]) for row in selected),
                    catalog_size_bytes=tuple(int(row["size"]) for row in selected),
                    band_coverage="measured",
                )
            )
    pairs.sort(key=lambda item: (item.priority, item.cadence_id, item.window_mhz))
    kept = pairs[:limit]
    header = {
        "kind": "listing",
        "listing_url": listing_url,
        "listing_sha256": hashlib.sha256(listing).hexdigest(),
        "campaign": config.campaign,
        "synthetic": False,
        "receiver": receiver,
        "cadences_in_listing": len(groups),
        "cadences_queued": len(queued_ids),
        "windows_skipped_outside_measured_band": skipped_outside,
        "pairs_omitted_by_limit": max(0, len(pairs) - len(kept)),
    }
    return _jsonl(header, kept)


def build_synthetic_queue(
    *,
    config: LiveConfig,
    seeds: tuple[int, ...],
    limit: int,
) -> str:
    """Queue EXP-004 cadences. Every line is marked synthetic."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not seeds or any(seed < 0 for seed in seeds):
        raise ValueError("synthetic seeds must be non-negative")
    low, high = synthetic_frame_band_mhz()
    identity = "synthetic://exp-004/seeds/" + ",".join(str(seed) for seed in seeds)
    pairs = [
        QueuePair(
            cadence_id=f"exp-004-{seed}-full",
            target="XENIA-SYNTHETIC",
            ra_deg=0.0,
            dec_deg=0.0,
            receiver="C",
            window_mhz=(low, high),
            priority=index,
            synthetic=True,
            files=(),
            roles=ROLES,
            sources=("XENIA-SYNTHETIC",) * 6,
            catalog_md5=(),
            catalog_size_bytes=(),
            band_coverage="synthetic-generator",
        )
        for index, seed in enumerate(seeds)
    ]
    header = {
        "kind": "listing",
        "listing_url": identity,
        "listing_sha256": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "campaign": config.campaign,
        "synthetic": True,
        "receiver": "C",
        "cadences_in_listing": len(seeds),
        "cadences_queued": min(limit, len(pairs)),
        "windows_skipped_outside_measured_band": 0,
        "pairs_omitted_by_limit": max(0, len(pairs) - limit),
        "note": (
            "Synthetic EXP-004 frames. The window is the generated band, "
            "not a Breakthrough Listen file."
        ),
    }
    return _jsonl(header, pairs[:limit])


def read_queue(path: Path) -> tuple[dict[str, object], tuple[QueuePair, ...]]:
    """Read a queue file written by ``build_listing_queue`` or ``build_synthetic_queue``."""
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"{path} is empty")
    header = json.loads(lines[0])
    if not isinstance(header, dict) or header.get("kind") != "listing":
        raise ValueError(f"{path} does not start with a listing header")
    pairs: list[QueuePair] = []
    for line in lines[1:]:
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path} has a pair line that is not an object")
        window = row["window_mhz"]
        pairs.append(
            QueuePair(
                cadence_id=str(row["cadence_id"]),
                target=str(row["target"]),
                ra_deg=float(row["ra_deg"]),
                dec_deg=float(row["dec_deg"]),
                receiver=str(row["receiver"]),
                window_mhz=(float(window[0]), float(window[1])),
                priority=int(row["priority"]),
                synthetic=bool(row["synthetic"]),
                files=tuple(str(item) for item in row["files"]),
                roles=tuple(str(item) for item in row["roles"]),
                sources=tuple(str(item) for item in row["sources"]),
                catalog_md5=tuple(str(item) for item in row["catalog_md5"]),
                catalog_size_bytes=tuple(int(item) for item in row["catalog_size_bytes"]),
                band_coverage=str(row["band_coverage"]),
            )
        )
    return header, tuple(pairs)


def _rows(listing: bytes) -> list[dict[str, object]]:
    try:
        document = json.loads(listing)
    except json.JSONDecodeError as exc:
        raise ValueError("listing is not JSON") from exc
    if not isinstance(document, dict) or document.get("result") != "success":
        raise ValueError("listing result was not success")
    rows = document.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError("listing data is empty")
    parsed: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("listing row is not an object")
        parsed.append(row)
    return parsed


def _group_rows(
    rows: list[dict[str, object]], *, cadence_id: str | None
) -> dict[str, list[dict[str, object]]]:
    if all(not row.get("cadence_url") for row in rows):
        if not cadence_id:
            raise ValueError("listing rows have no cadence_url; pass cadence_id")
        return {cadence_id: rows}
    groups: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        key = str(row.get("cadence_url") or "")
        if not key:
            raise ValueError("listing mixes rows with and without cadence_url")
        groups.setdefault(key, []).append(row)
    return groups


def _fine_abacad(rows: list[dict[str, object]]) -> tuple[dict[str, object], ...] | None:
    fine = [row for row in rows if str(row.get("url", "")).endswith(FINE_SUFFIX)]
    fine.sort(key=lambda row: (float(row["mjd"]), int(row["id"])))
    if len(fine) != 6:
        return None
    targets = [str(row["target"]) for row in fine]
    on_source = targets[0]
    if not (targets[0] == targets[2] == targets[4]):
        return None
    offs = (targets[1], targets[3], targets[5])
    if on_source in offs or len(set(offs)) != 3:
        return None
    return tuple(fine)


def _jsonl(header: dict[str, object], pairs: list[QueuePair]) -> str:
    lines = [json.dumps(header, ensure_ascii=False, sort_keys=True)]
    for pair in pairs:
        lines.append(
            json.dumps(
                {
                    "band_coverage": pair.band_coverage,
                    "cadence_id": pair.cadence_id,
                    "catalog_md5": list(pair.catalog_md5),
                    "catalog_size_bytes": list(pair.catalog_size_bytes),
                    "dec_deg": pair.dec_deg,
                    "files": list(pair.files),
                    "priority": pair.priority,
                    "ra_deg": pair.ra_deg,
                    "receiver": pair.receiver,
                    "roles": list(pair.roles),
                    "sources": list(pair.sources),
                    "synthetic": pair.synthetic,
                    "target": pair.target,
                    "window_mhz": list(pair.window_mhz),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return "\n".join(lines) + "\n"
