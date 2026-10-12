"""Static page rendering and acceptance tests."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from xenia.live.models import DetectionFloor
from xenia.live.render import render_site
from xenia.text_policy import find_banned_words

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
    assert find_banned_words(page) == ()
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
