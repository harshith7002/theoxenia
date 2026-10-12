"""State aggregation and run-manifest loading tests."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from xenia.live.models import FloorPayload, HeroPayload, Verdict
from xenia.live.state import ManifestLoadError, build_state, floor_summary, load_manifests


def test_demo_totals_are_aggregated_from_fixture_manifests(demo_state) -> None:
    """Known-answer demo totals come from the synthetic fixture records."""
    assert demo_state.meta.demo is True
    assert demo_state.totals.cadences_searched == 2
    assert demo_state.totals.windows_searched == 2
    assert demo_state.totals.mhz_hours_on_target == 0.5
    assert demo_state.totals.hits == 3
    assert demo_state.totals.known_source == 1
    assert demo_state.totals.in_off == 1
    assert demo_state.totals.survivors == 1
    assert demo_state.totals.unexplained == 0
    assert demo_state.totals.targets_distinct == 3
    assert demo_state.totals.failed == 1
    assert (
        demo_state.meta.data_credit
        == "Synthetic M0 fixtures; no telescope observations are included."
    )


def test_failed_experiment_does_not_remove_demo_badge(demo_manifests, fixed_time) -> None:
    """An operational failure is not enough to claim that the live page has real data."""
    failed = demo_manifests[0].model_copy(
        update={"demo": False, "mission_control": None, "outcome": "failed"}
    )

    state = build_state([failed], generated_at=fixed_time, git_sha="failure-sha")

    assert state.meta.demo is True
    assert (
        state.meta.data_credit == "Synthetic M0 fixtures; no telescope observations are included."
    )


def test_real_manifest_backed_hero_removes_demo_badge(demo_manifests, fixed_time) -> None:
    """Only a real, typed experiment payload turns the page into an observation view."""
    source = demo_manifests[0]
    real_hero = source.model_copy(
        update={
            "demo": False,
            "mission_control": HeroPayload(
                kind="hero",
                experiment="EXP-001",
                run_id=source.run_id,
                image_url=f"runs/{source.run_id}/hero.png",
                freq_mhz=8419.297028,
                drift_hz_s=-0.373093,
                snr=245.708,
            ),
        }
    )

    state = build_state([real_hero], generated_at=fixed_time, git_sha="real-sha")

    assert state.meta.demo is False
    assert state.meta.data_credit == "Breakthrough Listen open data, Green Bank Telescope."
    assert state.hero is not None
    assert state.hero.freq_mhz == pytest.approx(8419.297028)


def test_gallery_prioritizes_recent_survivors_and_links_manifests(demo_state) -> None:
    """Recent survivor cards appear first and keep relative provenance links."""
    assert demo_state.gallery[0].verdict is Verdict.ON_ONLY
    assert demo_state.gallery[0].badge_text == "Survivor, 1 of 5 checks done"
    assert demo_state.gallery[0].manifest_url == "runs/demo-cadence-002/manifest.json"
    assert all(item.manifest_url.startswith("runs/") for item in demo_state.gallery)
    assert all(point.manifest_url.startswith("runs/") for point in demo_state.pointings)


def test_same_inputs_and_clock_produce_identical_state(demo_manifests, fixed_time) -> None:
    """Aggregation is stable when timestamp and code metadata are held constant."""
    first = build_state(demo_manifests, generated_at=fixed_time, git_sha="abc123")
    second = build_state(demo_manifests, generated_at=fixed_time, git_sha="abc123")
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_only_generated_at_changes_when_clock_changes(demo_manifests, fixed_time) -> None:
    """State content is reproducible apart from its explicit build timestamp."""
    first = build_state(demo_manifests, generated_at=fixed_time, git_sha="abc123")
    second = build_state(
        demo_manifests,
        generated_at=datetime(2026, 10, 12, 10, 1, tzinfo=UTC),
        git_sha="abc123",
    )
    left = first.model_dump(mode="json")
    right = second.model_dump(mode="json")
    left.pop("generated_at")
    right.pop("generated_at")
    assert left == right


def test_invalid_manifest_fails_loudly(tmp_path: Path) -> None:
    """Malformed manifests are errors, not silently omitted records."""
    manifest = tmp_path / "broken" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ManifestLoadError, match="invalid manifest"):
        load_manifests(tmp_path)


def test_duplicate_run_ids_fail_loudly(tmp_path: Path, demo_manifests) -> None:
    """Two records cannot silently shadow one another under the same run ID."""
    source = Path(__file__).parent / "fixtures" / "live" / "demo-worker-001" / "manifest.json"
    for folder in ("a", "b"):
        destination = tmp_path / folder / "manifest.json"
        destination.parent.mkdir()
        shutil.copyfile(source, destination)
    with pytest.raises(ManifestLoadError, match="duplicate run_id"):
        load_manifests(tmp_path)


def test_missing_manifest_directory_is_not_treated_as_an_empty_success(tmp_path: Path) -> None:
    """A misspelled input root produces a clear filesystem error."""
    with pytest.raises(FileNotFoundError, match="does not exist"):
        load_manifests(tmp_path / "missing")


def test_floor_summary_is_computed_from_the_recovery_grid() -> None:
    """The lowest fully recovered SNR in the configured drift range is derived."""
    payload = FloorPayload(
        kind="detection_floor",
        experiment="EXP-002",
        snr_grid=(6.0, 12.0),
        drift_grid=(-1.0, 1.0, 4.0),
        trials_per_cell=5,
        recovered_fraction=((1.0, 1.0, 0.8), (1.0, 1.0, 1.0)),
    )
    assert floor_summary(payload) == "Recovers SNR ≥ 6 at drift within ±3 Hz/s."


def test_floor_summary_describes_centerline_only_recovery() -> None:
    """A null drift floor still exposes the measured zero-drift threshold."""
    payload = FloorPayload(
        kind="detection_floor",
        experiment="EXP-002",
        snr_grid=(5.0, 8.0, 40.0),
        drift_grid=(-2.0, 0.0, 2.0, 4.0),
        trials_per_cell=5,
        recovered_fraction=((0.0, 0.4, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0)),
    )
    assert floor_summary(payload) == (
        "At 0 Hz/s, full recovery begins at SNR ≥ 8; all tested nonzero-drift cells recovered 0%. "
        "No tested SNR reached full recovery across ±3 Hz/s."
    )


def test_floor_summary_reports_best_nonzero_recovery_without_claiming_a_floor() -> None:
    """Partial off-center recovery is described without implying full sensitivity."""
    payload = FloorPayload(
        kind="detection_floor",
        experiment="EXP-002",
        snr_grid=(8.0,),
        drift_grid=(-1.0, 0.0, 1.0),
        trials_per_cell=5,
        recovered_fraction=((0.2, 1.0, 0.4),),
    )
    assert floor_summary(payload) == (
        "At 0 Hz/s, full recovery begins at SNR ≥ 8; best nonzero-drift recovery was 40%. "
        "No tested SNR reached full recovery across ±3 Hz/s."
    )


def test_floor_summary_explains_when_no_drift_cells_qualify() -> None:
    """The summary does not invent a threshold outside the supplied grid."""
    payload = FloorPayload(
        kind="detection_floor",
        experiment="EXP-002",
        snr_grid=(6.0,),
        drift_grid=(4.0, 8.0),
        trials_per_cell=5,
        recovered_fraction=((1.0, 1.0),),
    )
    assert "No drift cells" in floor_summary(payload)


def test_floor_ci_run_link_survives_state_aggregation_without_observation_credit(
    demo_manifests,
    fixed_time,
) -> None:
    """The page carries CI provenance while keeping synthetic calibration distinct."""
    source = demo_manifests[0]
    floor_manifest = source.model_copy(
        update={
            "demo": False,
            "experiment_id": "EXP-002",
            "mission_control": FloorPayload(
                kind="detection_floor",
                experiment="EXP-002",
                snr_grid=(5.0,),
                drift_grid=(0.0,),
                trials_per_cell=1,
                recovered_fraction=((0.0,),),
                ci_run_url="https://github.com/mpetyx/theoxenia/actions/runs/123456789",
            ),
        }
    )

    state = build_state([floor_manifest], generated_at=fixed_time, git_sha="floor-sha")

    assert state.detection_floor is not None
    assert state.detection_floor.ci_run_url == (
        "https://github.com/mpetyx/theoxenia/actions/runs/123456789"
    )
    assert "synthetic signal injections" in state.meta.data_credit
    assert "Breakthrough Listen" not in state.meta.data_credit


def test_fixture_files_are_small_json_or_svg(demo_manifests) -> None:
    """The committed M0 set contains no raw telescope/scan files."""
    root = Path(__file__).parent / "fixtures" / "live"
    assert all(
        path.suffix in {".json", ".svg", ".md"} for path in root.rglob("*") if path.is_file()
    )
    assert sum(len(manifest.model_dump_json()) for manifest in demo_manifests) > 0
