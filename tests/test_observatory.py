"""Recovery, bounded failure handling, evidence checks and publication isolation."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from xenia.live.models import RunManifest
from xenia.live.observatory import (
    STATUS_PATH,
    completed_pairs,
    publish_cycle,
    read_status,
    run_cycle,
    validate_cadence,
)
from xenia.live.worker import PairOutcome

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "20261012T203545022355Z-exp-003-cadence"


def setup(root: Path, *, existing: bool = True) -> Path:
    (root / "configs").mkdir(parents=True)
    shutil.copy(ROOT / "configs/live.yaml", root / "configs/live.yaml")
    lines = (ROOT / "configs/queue.jsonl").read_text().splitlines()
    (root / "configs/queue.jsonl").write_text("\n".join(lines[:3]) + "\n")
    (root / "runs").mkdir()
    if existing:
        shutil.copytree(ROOT / "runs" / SOURCE, root / "runs" / SOURCE)
    return root


def materialize(root: Path, pair) -> PairOutcome:
    run_id = "new-measured-window"
    shutil.copytree(ROOT / "runs" / SOURCE, root / "runs" / run_id)
    path = root / "runs" / run_id / "manifest.json"
    text = path.read_text().replace(SOURCE, run_id)
    doc = json.loads(text)
    doc["mission_control"]["window_mhz"] = list(pair.window_mhz)
    doc["parameters"]["window_mhz"] = list(pair.window_mhz)
    path.write_text(json.dumps(doc))
    return PairOutcome(run_id, 0, "searched")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def repository(root: Path) -> Path:
    setup(root)
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    git(root, "add", ".")
    git(root, "commit", "-m", "source")
    remote = root.parent / "remote.git"
    git(root.parent, "init", "--bare", str(remote))
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-u", "origin", "main")
    return root


def test_resume_from_artifacts_not_host_specific_progress(tmp_path: Path) -> None:
    root = setup(tmp_path)
    assert read_status(root) is None
    calls = []

    def runner(pair):
        calls.append(pair.window_mhz)
        return materialize(root, pair)

    status = run_cycle(root, runner=runner)
    assert calls == [(1420.0, 1421.0)]
    assert status.state == "queue_complete"
    assert status.completed_windows == 2
    assert status.new_runs == ["new-measured-window"]
    (root / STATUS_PATH).unlink()  # Simulate loss of the convenience status file.
    recovered = run_cycle(root, runner=runner)
    assert recovered.completed_windows == 2
    assert recovered.new_runs == []
    assert len(calls) == 1
    assert read_status(root) == recovered
    assert len(completed_pairs(root)) == 2


def test_failures_are_bounded_and_remain_visible(tmp_path: Path) -> None:
    root = setup(tmp_path)
    calls = []

    def fail(pair):
        calls.append(pair)
        raise RuntimeError("upstream unavailable")

    for _ in range(4):
        status = run_cycle(root, runner=fail)
    assert len(calls) == 3
    assert status.state == "needs_attention"
    assert status.pending_windows == 0
    assert status.blocked_windows == 1
    assert next(iter(status.failures.values())).attempts == 3
    assert (root / "runs" / status.cycle_id / "cycle.json").exists()


def test_success_clears_failure_and_rejects_wrong_result(tmp_path: Path) -> None:
    root = setup(tmp_path)
    first = run_cycle(root, runner=lambda _: PairOutcome(SOURCE, 0, "wrong window"))
    assert "different window" in next(iter(first.failures.values())).error
    second = run_cycle(root, runner=lambda p: materialize(root, p))
    assert second.failures == {}
    assert second.state == "queue_complete"


def test_rejects_changed_evidence(tmp_path: Path) -> None:
    root = setup(tmp_path)
    (root / "runs" / SOURCE / "hits.parquet").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        completed_pairs(root)


def test_parquet_independently_checks_manifest_totals(tmp_path: Path) -> None:
    root = setup(tmp_path)
    manifest = RunManifest.model_validate_json(
        (root / "runs" / SOURCE / "manifest.json").read_text()
    )
    params = dict(manifest.parameters)
    params["verdict_counts"] = {**params["verdict_counts"], "IN_OFF": 150}
    params["hit_count"] = 274
    with pytest.raises(ValueError, match="hit table differs"):
        validate_cadence(root, manifest.model_copy(update={"parameters": params}))


def test_queue_guards(tmp_path: Path) -> None:
    root = setup(tmp_path)
    with pytest.raises(ValueError, match="max_pairs"):
        run_cycle(root, max_pairs=0)
    queue = root / "configs/queue.jsonl"
    lines = queue.read_text().splitlines()
    queue.write_text("\n".join([*lines, lines[1]]) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        run_cycle(root)
    queue.write_text("\n".join(lines).replace('"synthetic": false', '"synthetic": true'))
    with pytest.raises(ValueError, match="real-data"):
        run_cycle(root)


def test_publish_excludes_unrelated_files_and_preserves_source(tmp_path: Path) -> None:
    root = repository(tmp_path / "work")
    status = run_cycle(root, runner=lambda p: materialize(root, p))
    (root / "private.txt").write_text("unrelated")
    publish_cycle(root, status)
    assert "private.txt" not in git(root, "show", "--name-only", "--format=")
    assert "configs/live.yaml" not in git(root, "show", "--name-only", "--format=")
    assert git(root, "rev-parse", "HEAD") == git(root, "rev-parse", "origin/main")
    assert git(root, "branch", "--format=%(refname:short)") == "main"


def test_publish_rejects_unrelated_staged_or_modified_work(tmp_path: Path) -> None:
    root = repository(tmp_path / "work")
    status = run_cycle(root, runner=lambda p: materialize(root, p))
    config = root / "configs/live.yaml"
    config.write_text(config.read_text() + "\n# unrelated change\n")
    with pytest.raises(ValueError, match="modified tracked"):
        publish_cycle(root, status)
    git(root, "add", "configs/live.yaml")
    with pytest.raises(ValueError, match="staged changes"):
        publish_cycle(root, status)


def test_concurrent_remote_update_is_not_overwritten(tmp_path: Path) -> None:
    root = repository(tmp_path / "work")
    status = run_cycle(root, runner=lambda p: materialize(root, p))
    other = tmp_path / "other"
    git(tmp_path, "clone", "-b", "main", str(tmp_path / "remote.git"), str(other))
    git(other, "config", "user.name", "Other")
    git(other, "config", "user.email", "other@example.com")
    (other / "README").write_text("concurrent source edit")
    git(other, "add", "README")
    git(other, "commit", "-m", "concurrent change")
    git(other, "push")
    with pytest.raises(subprocess.CalledProcessError):
        publish_cycle(root, status)
    assert "observatory cycle" in git(root, "log", "-1", "--format=%s")
    git(root, "fetch", "origin")
    assert git(root, "log", "origin/main", "-1", "--format=%s") == "concurrent change"
