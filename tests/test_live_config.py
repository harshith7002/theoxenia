"""configs/live.yaml matches the worker contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from xenia.live.config import load_live_config

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_live_yaml_matches_the_spec_and_the_measured_cap() -> None:
    config = load_live_config(REPOSITORY_ROOT / "configs" / "live.yaml")

    assert config.campaign == "bl-opendata-gbt-hdf5"
    assert config.queue_file == "configs/queue.jsonl"
    assert config.window_mhz == 1.0
    assert config.window_starts("L")[0] == 1380.0
    assert config.window_starts("C") == (4000.0, 5000.0, 6000.0, 7000.0, 7800.0)
    assert config.max_drift_hz_s == 4.0
    assert config.minimum_snr == 10.0
    assert config.filter_threshold == 3
    assert config.thumb_px == (320, 140)
    assert config.colormap == "theoxenia_night"
    assert config.commit_branch == "main"
    assert config.commit_every_minutes == 30
    assert config.commit_on_survivor is True
    assert config.heartbeat_seconds == 60
    assert config.idle_sleep_minutes == 15
    assert config.max_retries == 2
    assert config.transfer_cap_bytes == 256 * 1024 * 1024
    assert config.allow_plain_http is False
    band = config.measured_file_bands[0]
    assert band.cadence_id == "bl-opendata-63460"
    assert band.low_mhz < 1380.0 < 1381.0 < band.high_mhz


def test_live_config_rejects_an_unknown_key(tmp_path: Path) -> None:
    source = (REPOSITORY_ROOT / "configs" / "live.yaml").read_text(encoding="utf-8")
    path = tmp_path / "live.yaml"
    path.write_text(source + "extra: 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown keys"):
        load_live_config(path)
