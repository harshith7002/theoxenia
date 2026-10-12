"""Static page rendering and acceptance tests."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

from xenia.live.models import DetectionFloor, WorkerStatus
from xenia.live.render import render_site, worker_status

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEMO_RUNS = REPOSITORY_ROOT / "tests" / "fixtures" / "live"


class AssetInspector(HTMLParser):
    """Collect executable tags and external asset requests, not ordinary links."""

    def __init__(self) -> None:
        super().__init__()
        self.scripts = 0
        self.remote_assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script":
            self.scripts += 1
        attribute = "href" if tag == "link" else "src"
        if tag in {"img", "script", "link", "source"} and values.get(attribute):
            value = values[attribute] or ""
            if value.startswith(("http://", "https://", "//")):
                self.remote_assets.append(value)


def test_m0_page_is_static_accessible_and_provenance_linked(demo_state, tmp_path: Path) -> None:
    """The M0 page renders from state and remains usable without JavaScript."""
    state_path = tmp_path / "runs" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(demo_state.model_dump_json(indent=2), encoding="utf-8")
    output = tmp_path / "site"
    rendered = render_site(
        state_path=state_path,
        runs_dir=DEMO_RUNS,
        output_dir=output,
        repository_root=REPOSITORY_ROOT,
        now=demo_state.generated_at,
    )
    page = (output / "index.html").read_text(encoding="utf-8")
    parser = AssetInspector()
    parser.feed(page)

    assert (output / "state.json").is_file()
    assert (output / "sky.svg").is_file()
    assert (output / "floor.svg").is_file()
    assert (output / "runs" / "index.html").is_file()
    assert len(rendered) >= 10
    assert "Demo data — every number here is a placeholder." in page
    assert "M0 only: no live worker or telescope observations are included." in page
    assert "Worker paused, demo state" in page
    assert "Waiting for EXP-001" in page
    assert "Waiting for EXP-002" in page
    assert "Latest hits, and the checks applied." in page
    assert "0.5" in page
    assert "6000.123456" in page
    assert "runs/demo-cadence-002/manifest.json" in page
    assert 'loading="lazy"' in page
    assert 'role="img"' in (output / "sky.svg").read_text(encoding="utf-8")
    assert "aria-label=" in (output / "floor.svg").read_text(encoding="utf-8")
    assert 'name="viewport"' in page
    assert parser.scripts == 0
    assert parser.remote_assets == []
    assert not re.search(r"\b(alien|extraterrestrial|candidate|anomaly|mysterious)\b", page, re.I)
    assert "unexplained signal" not in page.lower()
    assert "Proof the detector works: Voyager 1" in page
    assert "Where we have looked" in page
    assert "How faint a signal we would catch" in page
    assert "Disclosure, Project Blue Book incident map: not started" in page
    assert "Near-Earth baselines, CNEOS and Kp: not started" in page
    assert "why they are not" not in page
    feed = json.loads((output / "feed.json").read_text(encoding="utf-8"))
    assert feed["version"] == "https://jsonfeed.org/version/1.1"
    assert feed["items"]
    assert all(item["id"] for item in feed["items"])
    assert 'href="cadences/demo-cadence-001/index.html"' in page
    assert 'href="hits/demo-hit-001.html"' in page
    assert 'href="sitemap.xml"' in page
    cadence_page = (output / "cadences" / "demo-cadence-001" / "index.html").read_text(
        encoding="utf-8"
    )
    hit_page = (output / "hits" / "demo-hit-001.html").read_text(encoding="utf-8")
    sitemap = (output / "sitemap.xml").read_text(encoding="utf-8")
    assert "Synthetic Target A" in cadence_page
    assert "12.5 deg right ascension" in cadence_page
    assert "not_in_off" in cadence_page
    assert "Checks recorded:" in cadence_page
    assert "synthetic fixture: cadence pair" in cadence_page
    assert "<script" not in cadence_page.lower()
    assert "demo-hit-001" in hit_page
    assert "Open the run manifest" in hit_page
    assert "cadences/demo-cadence-001/index.html" in sitemap
    assert "hits/demo-hit-001.html" in sitemap
    assert all(path.is_file() for path in rendered)


def test_all_metric_links_point_to_static_manifest_sections(demo_state, tmp_path: Path) -> None:
    """Every counter can be opened without a JavaScript filter."""
    state_path = tmp_path / "state.json"
    state_path.write_text(demo_state.model_dump_json(indent=2), encoding="utf-8")
    output = tmp_path / "site"
    render_site(
        state_path=state_path,
        runs_dir=DEMO_RUNS,
        output_dir=output,
        repository_root=REPOSITORY_ROOT,
        now=demo_state.generated_at,
    )
    page = (output / "index.html").read_text(encoding="utf-8")
    index = (output / "runs" / "index.html").read_text(encoding="utf-8")
    for anchor in ("cadences", "sky-hours", "hits", "survivors", "unexplained"):
        assert f'href="runs/index.html#{anchor}"' in page
        assert f'id="{anchor}"' in index


def test_floor_panel_links_manifest_and_actions_run_with_synthetic_disclosure(
    demo_state,
    tmp_path: Path,
) -> None:
    """The actual heatmap is labeled synthetic and links its run and optional CI record."""
    ci_url = "https://github.com/mpetyx/theoxenia/actions/runs/123456789"
    floor = DetectionFloor(
        run_id="demo-cadence-001",
        snr_grid=(5.0,),
        drift_grid=(0.0,),
        trials_per_cell=1,
        recovered_fraction=((1.0,),),
        summary="Synthetic test summary.",
        manifest_url="runs/demo-cadence-001/manifest.json",
        ci_run_url=ci_url,
    )
    meta = demo_state.meta.model_copy(
        update={
            "demo": False,
            "data_credit": "Synthetic setigen injection; no telescope observations.",
        }
    )
    state = demo_state.model_copy(update={"meta": meta, "detection_floor": floor})
    state_path = tmp_path / "state.json"
    state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    output = tmp_path / "site"

    render_site(
        state_path=state_path,
        runs_dir=DEMO_RUNS,
        output_dir=output,
        repository_root=REPOSITORY_ROOT,
        now=state.generated_at,
    )

    page = (output / "index.html").read_text(encoding="utf-8")
    svg = (output / "floor.svg").read_text(encoding="utf-8")
    assert "Synthetic setigen injections only" in page
    assert 'href="runs/demo-cadence-001/manifest.json"' in page
    assert f'href="{ci_url}"' in page
    assert "Open the CI run" in page
    assert "Synthetic setigen data · not telescope observations" in svg


def test_mirror_status_never_claims_to_be_live(demo_state) -> None:
    """A mirror labels itself with its update time instead of heartbeat freshness."""
    from xenia.live.render import worker_status

    meta = demo_state.meta.model_copy(
        update={"is_mirror": True, "mirror_updated_at": demo_state.generated_at}
    )
    mirror_state = demo_state.model_copy(update={"meta": meta})
    status = worker_status(mirror_state, now=demo_state.generated_at)
    assert status["label"] == "Mirror, updated 10:00 UTC"
    assert status["is_live"] is False


def test_status_pill_ages_from_live_to_quiet_to_stopped(demo_state) -> None:
    """Frozen clocks: under ten minutes, after ten minutes, and after six hours."""
    heartbeat = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
    worker = demo_state.worker.model_copy(
        update={"status": WorkerStatus.RUNNING, "last_heartbeat": heartbeat}
    )
    meta = demo_state.meta.model_copy(update={"demo": False})
    state = demo_state.model_copy(update={"worker": worker, "meta": meta})
    live = worker_status(state, now=heartbeat + timedelta(seconds=38))
    quiet = worker_status(state, now=heartbeat + timedelta(minutes=11))
    stopped = worker_status(state, now=heartbeat + timedelta(hours=7))
    assert live == {
        "label": "Live, heartbeat 38 s ago",
        "tone": "live",
        "is_live": True,
    }
    assert quiet["label"] == "Worker quiet since 10:00 UTC"
    assert quiet["is_live"] is False
    assert stopped["label"] == "Worker stopped, last run at 10:00 UTC"
    assert stopped["tone"] == "warning"
    assert stopped["is_live"] is False


def test_later_panels_light_only_when_a_non_demo_manifest_exists(
    demo_state, tmp_path: Path
) -> None:
    """EXP-010 lights its card. EXP-020 stays quiet when no manifest exists."""
    runs = tmp_path / "runs"
    shutil.copytree(DEMO_RUNS, runs)
    manifest = {
        "schema_version": "0.1",
        "run_id": "exp010-fixture",
        "pillar": "disclosure",
        "command": "xenia disclosure ocr data/case.pdf",
        "parameters": {"pages_processed": 3},
        "inputs": [{"uri": "synthetic://exp-010/case.pdf"}],
        "outputs": [],
        "git_sha": "fixture",
        "package_version": "0.1.0",
        "started_at": "2026-10-13T01:00:00Z",
        "finished_at": "2026-10-13T01:05:00Z",
        "outcome": "ocr_completed",
        "notes": ["Synthetic later-panel fixture."],
        "experiment_id": "EXP-010",
        "demo": False,
    }
    extra = runs / "exp010-fixture" / "manifest.json"
    extra.parent.mkdir()
    extra.write_text(json.dumps(manifest), encoding="utf-8")
    state_path = tmp_path / "state.json"
    state_path.write_text(demo_state.model_dump_json(indent=2), encoding="utf-8")
    output = tmp_path / "site"
    render_site(
        state_path=state_path,
        runs_dir=runs,
        output_dir=output,
        repository_root=REPOSITORY_ROOT,
        now=demo_state.generated_at,
    )
    page = (output / "index.html").read_text(encoding="utf-8")
    assert "Disclosure, Project Blue Book incident map: not started" not in page
    assert "Pages processed: 3." in page
    assert "outcome ocr_completed." in page
    assert 'href="runs/exp010-fixture/manifest.json"' in page
    assert "Near-Earth baselines, CNEOS and Kp: not started" in page
