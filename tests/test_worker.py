"""Worker loop tests. The cadence search is replaced with a fake runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from xenia.live.config import load_live_config
from xenia.live.models import RunManifest
from xenia.live.queue import QueuePair, read_queue
from xenia.live.worker import GitPublisher, PairOutcome, run_worker

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _config():
    return load_live_config(REPOSITORY_ROOT / "configs" / "live.yaml")


def _pair(**overrides: object) -> QueuePair:
    values = {
        "cadence_id": "exp-004-20261012-full",
        "target": "XENIA-SYNTHETIC",
        "ra_deg": 0.0,
        "dec_deg": 0.0,
        "receiver": "C",
        "window_mhz": (5999.0, 6000.0),
        "priority": 0,
        "synthetic": True,
        "files": (),
        "roles": ("A", "B", "A", "C", "A", "D"),
        "sources": ("XENIA-SYNTHETIC",) * 6,
        "catalog_md5": (),
        "catalog_size_bytes": (),
        "band_coverage": "synthetic-generator",
    }
    values.update(overrides)
    return QueuePair(**values)


def _write_queue(path: Path, pairs: list[QueuePair]) -> None:
    header = {
        "kind": "listing",
        "listing_url": "synthetic://test",
        "listing_sha256": "0" * 64,
        "synthetic": True,
    }
    lines = [json.dumps(header)]
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
                }
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_once_runs_a_pair_writes_a_heartbeat_and_deletes_tmp(tmp_path: Path) -> None:
    queue = tmp_path / "queue.jsonl"
    _write_queue(queue, [_pair()])
    calls: list[str] = []

    def runner(pair: QueuePair) -> PairOutcome:
        calls.append(pair.cadence_id)
        marker = tmp_path / "data" / "tmp" / "slice.h5"
        marker.parent.mkdir(parents=True)
        marker.write_bytes(b"not-committed")
        return PairOutcome(run_id="synthetic-1", on_only=0, detail="searched")

    summary = run_worker(
        tmp_path,
        _config(),
        queue,
        once=True,
        pair_runner=runner,
        publisher=None,
        refresh=None,
        host="test-host",
    )
    assert summary.pairs_completed == 1
    assert calls == ["exp-004-20261012-full"]
    assert not (tmp_path / "data" / "tmp").exists()
    manifest_path = tmp_path / "runs" / "worker-test-host" / "manifest.json"
    manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assert manifest.demo is False
    assert manifest.mission_control is not None
    assert manifest.mission_control.kind == "worker"
    assert manifest.mission_control.status.value == "running"
    assert manifest.mission_control.current is None


def test_retries_then_marks_the_pair_failed(tmp_path: Path) -> None:
    queue = tmp_path / "queue.jsonl"
    _write_queue(queue, [_pair()])
    calls = {"n": 0}

    def runner(pair: QueuePair) -> PairOutcome:
        calls["n"] += 1
        raise RuntimeError(f"down {pair.cadence_id}")

    summary = run_worker(
        tmp_path,
        _config(),
        queue,
        once=True,
        pair_runner=runner,
        publisher=None,
        host="test-host",
    )
    assert calls["n"] == 3
    assert summary.pairs_failed == 1
    progress = json.loads(
        (tmp_path / "runs" / "worker-test-host" / "progress.json").read_text(encoding="utf-8")
    )
    assert progress["failed"]
    second = run_worker(
        tmp_path,
        _config(),
        queue,
        once=True,
        pair_runner=runner,
        publisher=None,
        host="test-host",
    )
    assert second.pairs_failed == 0
    assert calls["n"] == 3


def test_survivor_asks_for_a_commit_and_main_is_refused(tmp_path: Path) -> None:
    queue = tmp_path / "queue.jsonl"
    _write_queue(queue, [_pair()])
    seen: list[tuple[str, str]] = []

    class Recorder:
        def prepare(self, root: Path, branch: str) -> str | None:
            seen.append(("prepare", branch))
            return f"branch {branch} does not exist; not creating it"

        def commit_runs(self, root: Path, branch: str, message: str) -> str | None:
            seen.append((branch, message))
            return None

    summary = run_worker(
        tmp_path,
        _config(),
        queue,
        once=True,
        pair_runner=lambda _pair: PairOutcome(run_id="s", on_only=1, detail="searched"),
        publisher=Recorder(),
        host="test-host",
    )
    assert summary.pairs_completed == 1
    assert any(message.startswith("worker: survivor") for _branch, message in seen)


def test_publisher_does_not_create_live_or_commit_to_main(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "init")
    publisher = GitPublisher()
    missing = publisher.commit_runs(repo, "live", "should not create")
    assert missing is not None
    assert "does not exist" in missing
    branches = _git(repo, "branch")
    assert "live" not in branches
    refused = publisher.commit_runs(repo, "main", "should not commit")
    assert refused is not None
    assert "main" in refused
    assert _git(repo, "log", "--oneline").endswith("init")

    _git(repo, "checkout", "-b", "live")
    (repo / "runs").mkdir()
    (repo / "runs" / "note.txt").write_text("pair\n", encoding="utf-8")
    committed = publisher.commit_runs(repo, "live", "record a pair")
    assert committed is None
    assert "record a pair" in _git(repo, "log", "--oneline")
    assert "record a pair" not in _git(repo, "log", "main", "--oneline")


def test_idle_forever_heartbeats_without_sleeping_the_whole_interval(tmp_path: Path) -> None:
    queue = tmp_path / "queue.jsonl"
    _write_queue(queue, [])
    sleeps: list[float] = []
    beats: list[int] = []
    summary = run_worker(
        tmp_path,
        _config(),
        queue,
        once=False,
        pair_runner=lambda _pair: PairOutcome(run_id="x", on_only=0, detail="searched"),
        publisher=None,
        host="test-host",
        refresh=lambda: beats.append(1),
        sleep=sleeps.append,
        should_stop=lambda: len(sleeps) >= 1,
    )
    assert summary.pairs_completed == 0
    assert sleeps == [60.0]
    assert len(beats) == 2
    manifest = RunManifest.model_validate_json(
        (tmp_path / "runs" / "worker-test-host" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest.mission_control.current is None


def test_read_queue_round_trip() -> None:
    _header, pairs = read_queue(REPOSITORY_ROOT / "configs" / "queue.synthetic.jsonl")
    assert len(pairs) == 1
    assert pairs[0].synthetic is True
    assert pairs[0].cadence_id == "exp-004-20261012-full"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
