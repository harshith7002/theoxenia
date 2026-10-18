"""Local Mission Control loop.

The loop slices, searches, and labels one queued pair at a time. It writes a
heartbeat manifest and can commit that work to the branch named in the
config. It does not create that branch, and it does not commit to ``main``.
``UNEXPLAINED`` is not a status this module can set.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

from xenia.live.config import LiveConfig
from xenia.live.models import (
    CadencePayload,
    CurrentSearch,
    NextSearch,
    RunManifest,
    Verdict,
    WorkerPayload,
    WorkerStatus,
)
from xenia.live.queue import QueuePair, read_queue
from xenia.provenance import create_run_manifest

Sleep = Callable[[float], None]
Clock = Callable[[], datetime]
Stop = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class PairOutcome:
    """What one pair run reported back to the loop."""

    run_id: str
    on_only: int
    detail: str


@dataclass(frozen=True, slots=True)
class LoopSummary:
    """Counts from one invocation. Rates are computed by the caller from the wall clock."""

    pairs_completed: int
    pairs_failed: int
    warnings: tuple[str, ...]


class GitPublisher:
    """Commit run artifacts onto an existing branch.

    This does not create ``live``, and it does not commit to ``main``.
    """

    def prepare(self, root: Path, branch: str) -> str | None:
        """Fast-forward the named branch when HEAD is already there."""
        refused = _refuse_branch(root, branch)
        if refused is not None:
            return refused
        result = subprocess.run(
            ["git", "pull", "--ff-only", "origin", branch],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            tail = detail[-1] if detail else f"exit {result.returncode}"
            return f"git pull --ff-only origin {branch} failed: {tail[:180]}"
        return None

    def commit_runs(self, root: Path, branch: str, message: str) -> str | None:
        """Commit ``runs/`` when HEAD is already the configured branch.

        Push only when ``THEOXENIA_PUSH`` is ``1``.
        """
        refused = _refuse_branch(root, branch)
        if refused is not None:
            return refused
        add = subprocess.run(
            ["git", "add", "--", "runs"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if add.returncode != 0:
            return f"git add runs failed: {(add.stderr or '').strip()[:180]}"
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=root,
            check=False,
        )
        if staged.returncode == 0:
            return None
        commit = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if commit.returncode != 0:
            return f"git commit failed: {(commit.stderr or '').strip()[:180]}"
        if os.environ.get("THEOXENIA_PUSH") != "1":
            return None
        push = subprocess.run(
            ["git", "push", "origin", branch],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if push.returncode != 0:
            return f"git push origin {branch} failed: {(push.stderr or '').strip()[:180]}"
        return None


def execute_pair(root: Path, pair: QueuePair, *, config: LiveConfig) -> PairOutcome:
    """Run one queued pair through the existing cadence commands."""
    if pair.synthetic:
        from xenia.live.cadence import run_synthetic_cadence

        seed = _synthetic_seed(pair.cadence_id)
        known = root / "configs" / "fixtures" / "exp004_known_sources.yaml"
        command = [
            "xenia",
            "live",
            "cadence",
            "--synthetic",
            "--seed",
            str(seed),
            "--mode",
            "full",
            "--experiment-id",
            "EXP-030",
        ]
        manifest, _path = run_synthetic_cadence(
            root,
            command,
            seed=seed,
            experiment_id="EXP-030",
            mode="full",
            known_sources_path=known,
        )
    else:
        from xenia.live.archive_cadence import run_archive_cadence

        known = root / "configs" / "known_sources.yaml"
        command = [
            "xenia",
            "live",
            "cadence",
            "--experiment-id",
            "EXP-003",
            "--cadence-id",
            pair.cadence_id,
        ]
        manifest, _path = run_archive_cadence(
            root,
            command,
            files=pair.files,
            sources=pair.sources,
            roles=pair.roles,
            window_mhz=pair.window_mhz,
            target=pair.target,
            ra_deg=pair.ra_deg,
            dec_deg=pair.dec_deg,
            experiment_id="EXP-003",
            cadence_id=pair.cadence_id,
            known_sources_path=known,
            catalog_md5=pair.catalog_md5 or None,
            catalog_size_bytes=pair.catalog_size_bytes or None,
            max_transfer_bytes=config.transfer_cap_bytes,
            allow_plain_http=config.allow_plain_http,
        )
    return PairOutcome(
        run_id=manifest.run_id,
        on_only=_on_only(manifest),
        detail=manifest.outcome,
    )


def run_worker(
    root: Path,
    config: LiveConfig,
    queue_path: Path,
    *,
    once: bool,
    max_pairs: int | None = None,
    pair_runner: Callable[[QueuePair], PairOutcome] | None = None,
    publisher: GitPublisher | None = None,
    refresh: Callable[[], None] | None = None,
    host: str | None = None,
    sleep: Sleep = time.sleep,
    clock: Clock | None = None,
    should_stop: Stop | None = None,
) -> LoopSummary:
    """Process the queue once, or until ``should_stop`` says to leave the forever loop."""
    repository = root.resolve()
    now = clock or (lambda: datetime.now(UTC))
    runner = pair_runner or (lambda pair: execute_pair(repository, pair, config=config))
    stop = should_stop or (lambda: False)
    started = now()
    worker_host = (host or os.environ.get("THEOXENIA_HOST") or socket.gethostname()).strip()
    if not worker_host:
        worker_host = "localhost"
    run_id = f"worker-{_slug(worker_host)}"
    manifest_path = repository / "runs" / run_id / "manifest.json"
    progress_path = repository / "runs" / run_id / "progress.json"
    completed = 0
    failed = 0
    warnings: list[str] = []
    last_commit_at: datetime | None = None
    cap = 1 if once and max_pairs is None else max_pairs

    def beat(current: CurrentSearch | None, nxt: NextSearch | None) -> None:
        _write_heartbeat(
            repository,
            manifest_path,
            run_id=run_id,
            host=worker_host,
            started_at=started,
            now=now(),
            current=current,
            nxt=nxt,
            warnings=warnings,
            queue_path=queue_path,
            branch=config.commit_branch,
        )
        _refresh(refresh, warnings)

    while True:
        if publisher is not None:
            prepared = publisher.prepare(repository, config.commit_branch)
            if prepared:
                _remember(warnings, prepared)
        _header, pairs = read_queue(queue_path)
        progress = _load_progress(progress_path)
        pending = [
            pair
            for pair in pairs
            if _pair_key(pair) not in progress["completed"]
            and _pair_key(pair) not in progress["failed"]
        ]
        if not pending:
            beat(None, None)
            if once or stop():
                break
            _idle(config, sleep, now, stop, beat=lambda: beat(None, None))
            if stop():
                break
            continue

        pair = pending[0]
        following = pending[1] if len(pending) > 1 else None
        beat(_current(pair, now()), _next(following))
        outcome: PairOutcome | None = None
        error = ""
        for _attempt in range(config.max_retries + 1):
            try:
                outcome = runner(pair)
                error = ""
                break
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            finally:
                _clear_tmp(repository)
        key = _pair_key(pair)
        if outcome is None:
            progress["failed"].append(key)
            progress["reasons"][key] = error[:300]
            failed += 1
            _remember(
                warnings,
                f"{pair.cadence_id} failed after {config.max_retries} retries: {error[:180]}",
            )
        else:
            progress["completed"].append(key)
            completed += 1
            if outcome.on_only and config.commit_on_survivor and publisher is not None:
                committed = publisher.commit_runs(
                    repository,
                    config.commit_branch,
                    f"worker: survivor in {outcome.run_id}",
                )
                last_commit_at = now()
                if committed:
                    _remember(warnings, committed)
        _save_progress(progress_path, progress)
        due = last_commit_at is None or now() - last_commit_at >= timedelta(
            minutes=config.commit_every_minutes
        )
        if due and publisher is not None and outcome is not None:
            committed = publisher.commit_runs(
                repository,
                config.commit_branch,
                "worker: record queued pairs",
            )
            last_commit_at = now()
            if committed:
                _remember(warnings, committed)
        beat(None, _next(following))
        if cap is not None and completed + failed >= cap:
            break
        if stop():
            break
    return LoopSummary(
        pairs_completed=completed,
        pairs_failed=failed,
        warnings=tuple(warnings),
    )


def _idle(
    config: LiveConfig, sleep: Sleep, clock: Clock, stop: Stop, *, beat: Callable[[], None]
) -> None:
    """Sleep the idle interval, rewriting the heartbeat so it stays under ten minutes."""
    deadline = clock() + timedelta(minutes=config.idle_sleep_minutes)
    while clock() < deadline:
        if stop():
            return
        remaining = (deadline - clock()).total_seconds()
        sleep(max(0.0, min(float(config.heartbeat_seconds), remaining)))
        beat()


def _write_heartbeat(
    root: Path,
    manifest_path: Path,
    *,
    run_id: str,
    host: str,
    started_at: datetime,
    now: datetime,
    current: CurrentSearch | None,
    nxt: NextSearch | None,
    warnings: list[str],
    queue_path: Path,
    branch: str,
) -> None:
    payload = WorkerPayload(
        kind="worker",
        status=WorkerStatus.RUNNING,
        last_heartbeat=now,
        host=host,
        current=current,
        next=nxt,
    )
    notes = ["Worker heartbeat. demo is false. The loop does not write UNEXPLAINED."]
    if warnings:
        notes.append(warnings[-1])
    finished = now if now >= started_at else started_at
    create_run_manifest(
        run_id=run_id,
        command=["xenia", "live", "run"],
        parameters={
            "host": host,
            "queue": queue_path.as_posix(),
            "commit_branch": branch,
            "push": os.environ.get("THEOXENIA_PUSH") == "1",
        },
        inputs=(),
        outputs=(),
        started_at=started_at,
        finished_at=finished,
        outcome="running",
        notes=notes,
        repository_root=root,
        demo=False,
        pillar="live",
        experiment_id="EXP-030",
        mission_control=payload,
        manifest_path=manifest_path,
    )


def _current(pair: QueuePair, started_at: datetime) -> CurrentSearch:
    return CurrentSearch(
        cadence_id=pair.cadence_id,
        target=pair.target,
        ra_deg=pair.ra_deg,
        dec_deg=pair.dec_deg,
        receiver=pair.receiver,
        window_mhz=pair.window_mhz,
        scan_index=1,
        scan_count=6,
        started_at=started_at,
    )


def _next(pair: QueuePair | None) -> NextSearch | None:
    if pair is None:
        return None
    return NextSearch(cadence_id=pair.cadence_id, target=pair.target, eta=None)


def _on_only(manifest: RunManifest) -> int:
    payload = manifest.mission_control
    if not isinstance(payload, CadencePayload):
        return 0
    return sum(hit.verdict is Verdict.ON_ONLY for hit in payload.hits)


def _synthetic_seed(cadence_id: str) -> int:
    parts = cadence_id.split("-")
    if len(parts) < 3 or parts[0] != "exp" or parts[1] != "004":
        raise ValueError(f"synthetic cadence id {cadence_id} has no seed")
    return int(parts[2])


def _pair_key(pair: QueuePair) -> str:
    start, stop = pair.window_mhz
    return f"{pair.cadence_id}:{start:.6f}:{stop:.6f}"


class Progress(TypedDict):
    completed: list[str]
    failed: list[str]
    reasons: dict[str, str]


def _load_progress(path: Path) -> Progress:
    if not path.is_file():
        return {"completed": [], "failed": [], "reasons": {}}
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} is not an object")
    completed = document.get("completed", [])
    failed = document.get("failed", [])
    reasons = document.get("reasons", {})
    if not isinstance(completed, list) or not all(isinstance(v, str) for v in completed):
        raise ValueError("completed progress must be a list of pair keys")
    if not isinstance(failed, list) or not all(isinstance(v, str) for v in failed):
        raise ValueError("failed progress must be a list of pair keys")
    if not isinstance(reasons, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in reasons.items()
    ):
        raise ValueError("progress reasons must map pair keys to text")
    return {"completed": completed, "failed": failed, "reasons": reasons}


def _save_progress(path: Path, progress: Progress) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(progress, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _clear_tmp(root: Path) -> None:
    tmp = root / "data" / "tmp"
    if tmp.exists():
        shutil.rmtree(tmp)


def _refresh(refresh: Callable[[], None] | None, warnings: list[str]) -> None:
    """Rebuild the page after a heartbeat. A render error is a warning, not a failed pair."""
    if refresh is None:
        return
    try:
        refresh()
    except Exception as exc:
        _remember(warnings, f"page refresh failed: {type(exc).__name__}: {exc}"[:180])


def _remember(warnings: list[str], text: str) -> None:
    if text and (not warnings or warnings[-1] != text):
        warnings.append(text)


def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in value)
    cleaned = cleaned.strip(".-") or "host"
    return cleaned[:40]


def _head_branch(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    return None if name == "HEAD" else name


def _branch_exists(root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _refuse_branch(root: Path, branch: str) -> str | None:
    if branch == "main":
        return "refusing to commit or pull main"
    if not _branch_exists(root, branch):
        return f"branch {branch} does not exist; not creating it"
    head = _head_branch(root)
    if head != branch:
        return f"HEAD is {head}; not switching to {branch}"
    return None
