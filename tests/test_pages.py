"""Detail-page path rules and the generated experiments index."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xenia.cli import main
from xenia.live.pages import CHECK_NAMES, render_experiments_index, sky_href
from xenia.live.state import load_manifests
from xenia.live.verdict import _checks


def test_check_names_match_the_verdict_function() -> None:
    """The page lists the same five checks the verdict function records."""
    records = _checks(
        drift_hz_s=0.2,
        off_count=0,
        passed_filter=True,
        known_name=None,
        session_match=None,
        session_hits=(),
    )
    assert tuple(item.name for item in records) == CHECK_NAMES


def test_sky_href_rejects_a_slash() -> None:
    """A cadence id cannot escape the cadences directory."""
    with pytest.raises(ValueError, match="safe path segment"):
        sky_href("bad/id")


def test_experiments_index_is_deterministic_and_check_fails_when_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command writes the index, then --check rejects a hand edit."""
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "runs" / "exp010-fixture"
    run_dir.mkdir(parents=True)
    manifest = {
        "schema_version": "0.1",
        "run_id": "exp010-fixture",
        "pillar": "disclosure",
        "command": "xenia disclosure ocr data/case.pdf",
        "parameters": {},
        "inputs": [{"uri": "synthetic://exp-010/case.pdf"}],
        "outputs": [],
        "git_sha": "fixture",
        "package_version": "0.1.0",
        "started_at": "2026-10-13T01:00:00Z",
        "finished_at": "2026-10-13T01:05:00Z",
        "outcome": "ocr_completed",
        "notes": ["Synthetic index fixture."],
        "experiment_id": "EXP-010",
        "demo": False,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "docs" / "experiments.md"
    output.parent.mkdir()
    text = render_experiments_index(load_manifests(tmp_path / "runs"))
    assert "exp010-fixture" in text
    assert "xenia disclosure ocr data/case.pdf" in text
    assert "ocr_completed" in text
    assert main(["docs", "experiments", "--runs", "runs", "--output", "docs/experiments.md"]) == 0
    assert output.read_text(encoding="utf-8") == text
    output.write_text(text + "\nextra\n", encoding="utf-8")
    assert (
        main(
            [
                "docs",
                "experiments",
                "--check",
                "--runs",
                "runs",
                "--output",
                "docs/experiments.md",
            ]
        )
        == 1
    )
