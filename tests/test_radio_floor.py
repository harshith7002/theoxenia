"""Offline tests for the EXP-002 seeded setigen injection/recovery runner."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import setigen as stg
from astropy import units as u
from blimpy import Waterfall

from xenia.live.models import RecoveryGridArtifact, RunManifest
from xenia.radio import floor
from xenia.radio.detector import DetectorResult, DopplerHit


def _hit(
    *,
    top_hit: int,
    frequency_mhz: float,
    drift_hz_s: float,
    snr: float = 20.0,
) -> DopplerHit:
    return DopplerHit(
        top_hit=top_hit,
        drift_hz_s=drift_hz_s,
        snr=snr,
        uncorrected_frequency_mhz=frequency_mhz,
        corrected_frequency_mhz=frequency_mhz,
        frequency_start_mhz=frequency_mhz - 0.0001,
        frequency_end_mhz=frequency_mhz + 0.0001,
    )


def test_grid_values_are_the_specified_full_and_reduced_shapes() -> None:
    """The PR smoke grid is a subset with one trial; nightly runs cover the full grid."""
    full_snr, full_drift, full_trials = floor.grid_values("full")
    reduced_snr, reduced_drift, reduced_trials = floor.grid_values("reduced")
    assert (len(full_snr), len(full_drift), full_trials) == (8, 9, 5)
    assert (len(reduced_snr), len(reduced_drift), reduced_trials) == (3, 3, 1)
    assert max(abs(value) for value in full_drift) == floor.MAX_ABS_DRIFT_HZ_S
    minimum_smearing_samples = (
        2 * floor.MAX_ABS_DRIFT_HZ_S * floor.TIME_RESOLUTION_SECONDS / floor.FREQUENCY_RESOLUTION_HZ
    )
    assert minimum_smearing_samples <= floor.SMEARING_SUBSAMPLES
    with pytest.raises(ValueError, match="unsupported"):
        floor.grid_values("other")  # type: ignore[arg-type]


def test_sweep_csv_is_deterministic_and_records_null_and_recovered_seeds(
    tmp_path: Path,
    reduced_recovery_grid: RecoveryGridArtifact,
) -> None:
    """CSV rows follow grid order and encode recovered seed lists unambiguously."""
    data = reduced_recovery_grid.model_dump(mode="json")
    first_measurement = data["measurements"][0]
    hit = _hit(
        top_hit=1,
        frequency_mhz=first_measurement["frequency_mhz"],
        drift_hz_s=first_measurement["drift_hz_s"],
    )
    first_measurement.update(
        {
            "recovered": True,
            "matched_hit": hit.as_dict(),
            "frequency_error_hz": 0.0,
            "drift_error_hz_s": 0.0,
        }
    )
    data["searches"][0]["detected_hits"] = [hit.as_dict()]
    data["recovered_count"][0][0] = 1
    data["recovered_fraction"][0][0] = 1.0
    grid = RecoveryGridArtifact.model_validate(data)

    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    floor._write_sweep_csv(first_path, grid)
    floor._write_sweep_csv(second_path, grid)

    csv_bytes = first_path.read_bytes()
    assert csv_bytes == second_path.read_bytes()
    assert b"\r" not in csv_bytes
    with first_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 9
    assert list(rows[0]) == [
        "snr",
        "drift_hz_s",
        "trials",
        "recovered_count",
        "recovered_fraction",
        "recovered_seeds",
    ]
    assert (rows[0]["snr"], rows[0]["drift_hz_s"]) == ("5.0", "-4.0")
    assert rows[0]["recovered_count"] == "1"
    assert rows[0]["recovered_fraction"] == "1.0"
    assert json.loads(rows[0]["recovered_seeds"]) == [grid.seed]
    assert (rows[1]["snr"], rows[1]["drift_hz_s"]) == ("5.0", "0.0")
    assert rows[1]["recovered_count"] == "0"
    assert rows[1]["recovered_fraction"] == "0.0"
    assert json.loads(rows[1]["recovered_seeds"]) == []


def test_setigen_frame_is_deterministic_and_filterbank_metadata_is_neutral(
    tmp_path: Path,
) -> None:
    """Same seed gives identical noise/signals and the temporary file names no telescope."""
    kwargs = {
        "snr_grid": (15.0,),
        "drift_grid": (1.0,),
        "trial_index": 1,
        "seed": 20261012,
        "frequency_channels": 4096,
    }
    first_frame, first_plans = floor._build_trial_frame(**kwargs)
    second_frame, second_plans = floor._build_trial_frame(**kwargs)
    assert np.array_equal(first_frame.data, second_frame.data)
    assert first_plans == second_plans
    assert first_plans[0].channel_index == floor.FREQUENCY_MARGIN_CHANNELS

    noise_only = stg.Frame(
        fchans=kwargs["frequency_channels"],
        tchans=floor.TIME_CHANNELS,
        df=floor.FREQUENCY_RESOLUTION_HZ * u.Hz,
        dt=floor.TIME_RESOLUTION_SECONDS * u.s,
        fch1=floor.FRAME_FCH1_MHZ * u.MHz,
        ascending=False,
        seed=kwargs["seed"],
        mjd=floor.FRAME_MJD,
        source_name="XENIA-SYNTHETIC",
    )
    noise_only.add_noise(x_mean=floor.NOISE_MEAN, noise_type="chi2")
    injected_power = first_frame.data - noise_only.data
    plan = first_plans[0]
    for time_index, integration_start in enumerate(first_frame.ts):
        integration_midpoint = integration_start + floor.TIME_RESOLUTION_SECONDS / 2
        frequency_hz = plan.start_frequency_mhz * 1e6 + plan.drift_hz_s * integration_midpoint
        channel_index = first_frame.get_index(frequency_hz)
        assert np.max(injected_power[time_index, channel_index - 2 : channel_index + 3]) > 0.1

    filterbank = tmp_path / "trial.fil"
    floor._save_neutral_filterbank(first_frame, filterbank)
    waterfall = Waterfall(str(filterbank), max_load=1)
    assert waterfall.header["source_name"] == "XENIA-SYNTHETIC"
    assert waterfall.header["rawdatafile"] == "Synthetic setigen injection; not telescope data"
    assert waterfall.header["telescope_id"] == 0
    assert waterfall.header["machine_id"] == 0
    assert waterfall.header["src_raj"] == 0.0
    assert waterfall.header["src_dej"] == 0.0


def test_recovery_matching_is_one_to_one_and_preserves_nulls() -> None:
    """A hit can recover at most one injection; below-threshold hits are not promoted."""
    shared_plan = floor._InjectionPlan(
        snr=10.0,
        drift_hz_s=0.0,
        trial_index=1,
        seed=44,
        channel_index=512,
        frequency_mhz=6000.0,
        start_frequency_mhz=6000.0,
    )
    duplicate_plan = floor._InjectionPlan(
        snr=20.0,
        drift_hz_s=0.0,
        trial_index=1,
        seed=44,
        channel_index=2112,
        frequency_mhz=6000.0,
        start_frequency_mhz=6000.0,
    )
    unobservable_plan = floor._InjectionPlan(
        snr=5.0,
        drift_hz_s=4.0,
        trial_index=1,
        seed=44,
        channel_index=3712,
        frequency_mhz=6000.02,
        start_frequency_mhz=6000.019,
    )
    hits = (
        _hit(top_hit=1, frequency_mhz=6000.0, drift_hz_s=0.0, snr=10.0),
        _hit(top_hit=2, frequency_mhz=6000.02, drift_hz_s=4.0, snr=4.9),
    )

    measurements = floor._match_trial(
        (shared_plan, duplicate_plan, unobservable_plan),
        hits,
    )

    assert [item.recovered for item in measurements] == [True, False, False]
    assert measurements[0].matched_hit is not None
    assert measurements[0].matched_hit.top_hit == 1
    assert measurements[0].frequency_error_hz == pytest.approx(0.0)
    assert measurements[1].matched_hit is None
    assert measurements[2].matched_hit is None


def test_ci_url_is_emitted_only_for_a_well_formed_actions_context(monkeypatch) -> None:
    """Local runs remain unlinked; Actions runs are safe, absolute HTTPS URLs."""
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert floor._ci_run_url_from_environment() is None

    monkeypatch.setenv("GITHUB_RUN_ID", "987654321")
    monkeypatch.setenv("GITHUB_REPOSITORY", "mpetyx/theoxenia")
    assert floor._ci_run_url_from_environment() == (
        "https://github.com/mpetyx/theoxenia/actions/runs/987654321"
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "../unsafe")
    with pytest.raises(ValueError, match="owner/repository"):
        floor._ci_run_url_from_environment()
    monkeypatch.setenv("GITHUB_REPOSITORY", "mpetyx/theoxenia")
    monkeypatch.setenv("GITHUB_SERVER_URL", "http://example.test")
    with pytest.raises(ValueError, match="HTTPS origin"):
        floor._ci_run_url_from_environment()


def test_floor_command_records_a_complete_null_grid_and_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero recoveries remain a valid, fully reproducible result rather than a missing run."""
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    versions = {
        "python": "3.15.0",
        "setigen": "2.7.0",
        "astropy": "8.0.1",
        "numpy": "2.5.0",
        "turbo-seti": "2.3.2",
        "blimpy": "2.1.4",
        "h5py": "3.16.0",
    }
    monkeypatch.setattr(floor, "_runtime_versions", lambda: versions)

    def fake_build_trial_frame(
        *,
        snr_grid,
        drift_grid,
        trial_index,
        seed,
        frequency_channels=floor.FREQUENCY_CHANNELS,
    ):
        plans = tuple(
            floor._InjectionPlan(
                snr=snr,
                drift_hz_s=drift,
                trial_index=trial_index,
                seed=seed,
                channel_index=512 + index * 1600,
                frequency_mhz=5900.0 + index * 0.01,
                start_frequency_mhz=5900.0 + index * 0.01,
            )
            for index, (snr, drift) in enumerate(floor._grid_cells(snr_grid, drift_grid))
        )
        return object(), plans

    def fake_save_filterbank(frame, path: Path) -> None:
        path.write_bytes(b"synthetic temporary FILTERBANK")

    def fake_detector(*args, **kwargs) -> DetectorResult:
        return DetectorResult(
            hits=(),
            artifacts=(),
            turbo_seti_version="2.3.2",
            blimpy_version="2.1.4",
        )

    monkeypatch.setattr(floor, "_build_trial_frame", fake_build_trial_frame)
    monkeypatch.setattr(floor, "_save_neutral_filterbank", fake_save_filterbank)
    monkeypatch.setattr(floor, "run_turboseti", fake_detector)

    manifest, manifest_path = floor.run_floor(
        tmp_path,
        ["xenia", "live", "floor", "--mode", "reduced", "--seed", "77"],
        mode="reduced",
        seed=77,
    )

    assert manifest_path.is_file()
    assert manifest.experiment_id == "EXP-002"
    assert manifest.pillar == "I · Sensor"
    assert manifest.outcome == "recovery_grid_completed"
    assert manifest.demo is False
    assert manifest.mission_control is not None
    assert manifest.mission_control.recovered_fraction == (
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    )
    grid_output = next(
        output for output in manifest.outputs if output.path.endswith("recovery_grid.json")
    )
    assert grid_output.sha256 is not None
    assert grid_output.size_bytes > 0
    grid_path = next(tmp_path.glob("runs/*/recovery_grid.json"))
    sweep_path = grid_path.with_name("sweep.csv")
    sweep_output = next(output for output in manifest.outputs if output.path.endswith("/sweep.csv"))
    assert sweep_output.sha256 == hashlib.sha256(sweep_path.read_bytes()).hexdigest()
    assert sweep_output.size_bytes == sweep_path.stat().st_size
    with sweep_path.open(encoding="utf-8", newline="") as stream:
        sweep_rows = list(csv.DictReader(stream))
    assert len(sweep_rows) == 9
    assert all(row["recovered_count"] == "0" for row in sweep_rows)
    assert all(json.loads(row["recovered_seeds"]) == [] for row in sweep_rows)
    grid = RecoveryGridArtifact.model_validate_json(grid_path.read_text(encoding="utf-8"))
    assert len(grid.measurements) == 9
    assert len(grid.searches) == 1
    assert grid.recovered_count == ((0, 0, 0), (0, 0, 0), (0, 0, 0))
    assert not list(tmp_path.rglob("*.fil"))
    assert not list(tmp_path.rglob("*.dat"))
    assert RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def test_floor_generator_failure_keeps_a_failed_manifest_and_partial_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generator bugs are explicit failed runs, with no fabricated grid."""
    monkeypatch.setattr(floor, "_runtime_versions", lambda: {"python": "3.15.0"})

    def fail_build(**kwargs):
        raise RuntimeError("synthetic generator failure")

    monkeypatch.setattr(floor, "_build_trial_frame", fail_build)
    with pytest.raises(RuntimeError, match="synthetic generator failure"):
        floor.run_floor(
            tmp_path,
            ["xenia", "live", "floor", "--mode", "reduced"],
            mode="reduced",
            seed=10,
        )

    manifest_path = next(tmp_path.glob("runs/*/manifest.json"))
    manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assert manifest.experiment_id == "EXP-002"
    assert manifest.outcome == "failed"
    assert manifest.mission_control is None
    assert any(item.path.endswith("failure.json") for item in manifest.outputs)
    failure = json.loads((manifest_path.parent / "failure.json").read_text(encoding="utf-8"))
    assert failure["error_type"] == "RuntimeError"
    assert failure["error_message"] == "synthetic generator failure"
    assert failure["failed_trial_index"] == 1
    assert failure["completed_searches"] == []
    assert failure["completed_measurements"] == []
    assert not (manifest_path.parent / "recovery_grid.json").exists()
