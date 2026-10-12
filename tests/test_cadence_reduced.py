"""Reduced EXP-004 cadence: four known answers, then the rendered tile text."""

from __future__ import annotations

import shutil
from pathlib import Path

from xenia.live.cadence import run_synthetic_cadence
from xenia.live.models import Verdict
from xenia.live.render import render_site
from xenia.live.state import build_state, load_manifests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_reduced_synthetic_cadence_matches_four_verdicts(tmp_path: Path) -> None:
    """One seed, 8192 channels. The page must say the cadence is synthetic."""
    root = tmp_path / "repo"
    shutil.copytree(REPOSITORY_ROOT / "site" / "templates", root / "site" / "templates")
    shutil.copyfile(REPOSITORY_ROOT / "site" / "styles.css", root / "site" / "styles.css")
    manifest, manifest_path = run_synthetic_cadence(
        root,
        ["xenia", "live", "cadence", "--synthetic", "--mode", "reduced", "--seed", "20261012"],
        seed=20261012,
        experiment_id="EXP-004",
        mode="reduced",
        known_sources_path=REPOSITORY_ROOT / "configs" / "known_sources.yaml",
    )
    assert manifest.demo is False
    assert manifest.outcome == "searched_with_survivors"
    assert manifest.mission_control is not None
    assert manifest.mission_control.kind == "cadence"
    hits = manifest.mission_control.hits
    assert len(hits) == 4
    assert {hit.verdict for hit in hits} == {
        Verdict.ON_ONLY,
        Verdict.IN_OFF,
        Verdict.SINGLE_POINTING,
        Verdict.KNOWN_SOURCE,
    }
    assert all("synthetic" in hit.explanation.lower() for hit in hits)
    assert all(str(item.uri).startswith("synthetic://") for item in manifest.inputs)
    recovery = (manifest_path.parent / "recovery.json").read_text(encoding="utf-8")
    assert '"all_matched": true' in recovery or '"all_matched":true' in recovery

    state = build_state(load_manifests(root / "runs"), git_sha="test")
    state_path = root / "runs" / "state.json"
    state_path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    render_site(
        state_path=state_path,
        runs_dir=root / "runs",
        output_dir=root / "site",
        repository_root=root,
    )
    page = (root / "site" / "index.html").read_text(encoding="utf-8")
    assert page.count('class="hit-card"') == 4
    assert "Synthetic ABACAD cadence, not a telescope observation." in page
    assert "Synthetic ABACAD" in page
