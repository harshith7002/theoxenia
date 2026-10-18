"""Public evidence parity, provenance failure modes and usable offline dossiers."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import polars as pl
import pytest
from test_public_release import BUILD

from xenia.live.investigations import STORIES, explorer_evidence, verified_output
from xenia.live.state import load_manifests
from xenia.text_policy import find_banned_words

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
ARCHIVE = str(STORIES[1]["run_id"])


def test_explorer_matches_every_source_row_and_measured_scan() -> None:
    manifests = load_manifests(RUNS)
    original = next(m for m in manifests if m.run_id == ARCHIVE)
    result = explorer_evidence(manifests, RUNS, original)
    assert result is not None
    data, preparation = result
    assert data["rows"] == pl.read_parquet(RUNS / ARCHIVE / "hits.parquet").to_dicts()
    assert len(data["rows"]) == 273
    assert len(data["scans"]) == 6
    assert [s["role"] for s in data["scans"]] == ["A", "B", "A", "C", "A", "D"]
    for index, scan in enumerate(data["scans"]):
        assert scan["slice_sha256"] == original.inputs[index].sha256
        assert scan["matches_original_slice_bytes"] is True
        assert scan["finite_positive_fraction"] == 1
        assert len(scan["relative_db"]) == scan["integrations"] == 16
        assert {len(row) for row in scan["relative_db"]} == {1024}
        assert scan["frequency_low_mhz"] == pytest.approx(1380, abs=0.000003)
        assert scan["frequency_high_mhz"] == pytest.approx(1381, abs=0.000003)
    assert preparation.parameters["detector_rerun"] is False


def test_reject_changed_artifact_and_wrong_parent(tmp_path: Path) -> None:
    manifests = load_manifests(RUNS)
    source = next(m for m in manifests if m.run_id == ARCHIVE)
    data, prepared = explorer_evidence(manifests, RUNS, source)  # type: ignore[misc]
    for m in (source, prepared):
        shutil.copytree(RUNS / m.run_id, tmp_path / m.run_id)
    path = tmp_path / prepared.run_id / "explorer.json"
    original_bytes = path.read_bytes()
    path.write_bytes(original_bytes + b" ")
    with pytest.raises(ValueError, match="checksum"):
        explorer_evidence(manifests, tmp_path, source)
    path.write_bytes(original_bytes)
    corrupted_source = source.model_copy(
        update={
            "parameters": {
                **source.parameters,
                "hit_count": 274,
            }
        }
    )
    with pytest.raises(ValueError, match="incomplete"):
        explorer_evidence(manifests, tmp_path, corrupted_source)
    with pytest.raises(ValueError, match="missing checksummed"):
        verified_output(source, "../../unrelated", tmp_path)
    data["source_run_id"] = "different-parent"
    path.write_text(json.dumps(data))
    changed_output = prepared.outputs[0].model_copy(
        update={
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
    changed = prepared.model_copy(update={"outputs": (changed_output, *prepared.outputs[1:])})
    with pytest.raises(ValueError, match="provenance"):
        explorer_evidence([source, changed], tmp_path, source)
    data["source_run_id"] = source.run_id
    data["rows"][0]["verdict"] = "IN_OFF"
    path.write_text(json.dumps(data))
    changed_output = changed_output.model_copy(
        update={
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
    changed = changed.model_copy(update={"outputs": (changed_output, *prepared.outputs[1:])})
    with pytest.raises(ValueError, match="classifications"):
        explorer_evidence([source, changed], tmp_path, source)


def test_dossiers_downloads_and_no_script_fallback(tmp_path: Path) -> None:
    BUILD.build_public_site(tmp_path, base_url="https://example.org/theoxenia/")
    explorer = (tmp_path / "explorer.html").read_text()
    assert explorer.count('class="row-select"') == 273
    assert explorer.count('class="measured-waterfall"') == 6
    assert "roughly 1 kHz display bins" in explorer
    assert "Later ON scans returned empty detector tables" in explorer
    with (tmp_path / "downloads/archive-hits.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 273
    assert sum(r["verdict"] == "IN_OFF" for r in rows) == 149
    assert sum(r["verdict"] == "SINGLE_POINTING" for r in rows) == 124
    for story in STORIES:
        run = story["run_id"]
        dossier = (tmp_path / f"dossiers/{run}.html").read_text()
        assert "not submitted or independently accepted" in dossier
        with zipfile.ZipFile(tmp_path / f"downloads/{run}.zip") as bundle:
            assert (
                bundle.read(f"runs/{run}/manifest.json")
                == (RUNS / run / "manifest.json").read_bytes()
            )
            assert "README.txt" in bundle.namelist()
            manifest = json.loads(bundle.read(f"runs/{run}/manifest.json"))
            for artifact in manifest["outputs"]:
                if artifact["sha256"]:
                    assert (
                        hashlib.sha256(bundle.read(artifact["path"])).hexdigest()
                        == artifact["sha256"]
                    )
        story_page = (tmp_path / f"investigations/{story['slug']}.html").read_text()
        assert 'id="step-4"' in story_page
        assert find_banned_words(story_page) == ()
    assert (tmp_path / "investigations/recovery.html").read_text().count(
        'class="recovery-cell"'
    ) == 72
    sitemap = (tmp_path / "sitemap.xml").read_text()
    assert "https://example.org/theoxenia/explorer.html" in sitemap
    assert "https://example.org/theoxenia/investigations/voyager.html" in sitemap


def test_no_observational_story_is_invented_for_fixtures() -> None:
    from xenia.live.investigations import available_stories

    assert available_stories(load_manifests(ROOT / "tests/fixtures/live")) == []
