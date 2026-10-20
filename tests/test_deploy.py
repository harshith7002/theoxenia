"""Deploy script guard and the recovery-page comparison."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUN_SH = REPOSITORY_ROOT / "deploy" / "run.sh"
_SPEC = importlib.util.spec_from_file_location(
    "recovery_check",
    REPOSITORY_ROOT / "scripts" / "recovery_check.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_RECOVERY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RECOVERY)
pages_match = _RECOVERY.pages_match

_PAGE = """<!DOCTYPE html>
<html><body>
<div class="status-pill status-pill--live" aria-label="Worker status: {label}">
  <span class="status-dot status-dot--live" aria-hidden="true"></span>
  <span>{label}</span>
</div>
<section class="ticker-panel" aria-label="Search ticker">
  <p>{ticker}</p>
  <span>State built {built}</span>
</section>
<p class="gallery">{body}</p>
</body></html>
"""


def _page(*, label: str, ticker: str, built: str, body: str) -> str:
    return _PAGE.format(label=label, ticker=ticker, built=built, body=body)


def test_clock_text_does_not_fail_recovery(tmp_path: Path) -> None:
    """Heartbeat, ticker, and the build clock may differ. The gallery may not."""
    left = tmp_path / "a" / "index.html"
    right = tmp_path / "b" / "index.html"
    left.parent.mkdir()
    right.parent.mkdir()
    left.write_text(
        _page(
            label="Live, heartbeat 4 s ago",
            ticker="Now searching HIP544, L, 1380 to 1381 MHz, scan 1 of 6.",
            built="21:24 UTC",
            body="IN_OFF",
        ),
        encoding="utf-8",
    )
    right.write_text(
        _page(
            label="Live, heartbeat 40 s ago",
            ticker="Idle, no cadence queued.",
            built="21:30 UTC",
            body="IN_OFF",
        ),
        encoding="utf-8",
    )
    assert pages_match(left.read_text(encoding="utf-8"), right.read_text(encoding="utf-8"))
    changed = right.read_text(encoding="utf-8").replace("IN_OFF", "ON_ONLY")
    assert pages_match(left.read_text(encoding="utf-8"), changed) is False


def test_run_sh_does_not_create_live(tmp_path: Path) -> None:
    """A checkout with no live branch stays put and does not clone or create one."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    result = subprocess.run(
        ["bash", str(RUN_SH)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env={"THEOXENIA_DEPLOY_STOP": "before-sync", "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert "not creating any branch" in result.stderr
    assert "stopping before sync" in result.stderr
    branches = subprocess.run(
        ["git", "branch"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "live" not in branches.stdout
