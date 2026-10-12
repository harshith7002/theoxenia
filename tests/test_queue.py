"""Queue construction stays breadth-first and does not invent file bands."""

from __future__ import annotations

import json
from pathlib import Path

from xenia.live.config import load_live_config
from xenia.live.queue import build_listing_queue, build_synthetic_queue, synthetic_frame_band_mhz

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LISTING = REPOSITORY_ROOT / "tests" / "fixtures" / "opendata_cadence_63460.json"


def test_measured_cadence_queues_only_windows_inside_the_header_band() -> None:
    config = load_live_config(REPOSITORY_ROOT / "configs" / "live.yaml")
    listing = LISTING.read_bytes()
    text = build_listing_queue(
        listing,
        config=config,
        listing_url="fixture://opendata_cadence_63460.json",
        receiver="L",
        limit=200,
        cadence_id="63460",
    )
    lines = [json.loads(line) for line in text.splitlines()]
    header, *pairs = lines

    assert header["synthetic"] is False
    assert header["cadences_queued"] == 1
    assert header["listing_sha256"]
    assert [pair["window_mhz"][0] for pair in pairs] == list(config.window_starts("L"))
    assert all(pair["priority"] == index for index, pair in enumerate(pairs))
    assert pairs[0]["files"][0].endswith("Hip544_0039.gpuspec.0000.h5")
    assert pairs[0]["sources"] == ["HIP544", "HIP1024", "HIP544", "HIP114", "HIP544", "HIP1344"]
    assert pairs[0]["roles"] == ["A", "B", "A", "C", "A", "D"]
    assert pairs[0]["band_coverage"] == "measured"
    assert pairs[0]["catalog_md5"][0] == "b66f9ddb87204955651b45d0c80296c1"
    assert all(not pair["synthetic"] for pair in pairs)


def test_unmeasured_cadence_is_not_queued(tmp_path: Path) -> None:
    config = load_live_config(REPOSITORY_ROOT / "configs" / "live.yaml")
    listing = json.loads(LISTING.read_text(encoding="utf-8"))
    for row in listing["data"]:
        row["cadence_url"] = "999"
    path = tmp_path / "listing.json"
    payload = json.dumps(listing).encode("utf-8")
    path.write_bytes(payload)

    text = build_listing_queue(
        payload,
        config=config,
        listing_url="fixture://unmeasured",
        receiver="L",
        limit=200,
    )
    lines = [json.loads(line) for line in text.splitlines()]
    assert lines[0]["cadences_queued"] == 0
    assert len(lines) == 1


def test_synthetic_queue_names_the_generated_band() -> None:
    config = load_live_config(REPOSITORY_ROOT / "configs" / "live.yaml")
    low, high = synthetic_frame_band_mhz()
    text = build_synthetic_queue(config=config, seeds=(20261012, 7), limit=200)
    lines = [json.loads(line) for line in text.splitlines()]
    header, first, second = lines

    assert header["synthetic"] is True
    assert header["listing_url"] == "synthetic://exp-004/seeds/20261012,7"
    assert first["cadence_id"] == "exp-004-20261012-full"
    assert first["window_mhz"] == [low, high]
    assert first["synthetic"] is True
    assert first["files"] == []
    assert second["priority"] == 1
    assert low < 5999.99 < high
