"""Publication bundles fail closed when evidence is changed."""

import importlib.util
from pathlib import Path
from zipfile import ZipFile

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "package_report", Path(__file__).parents[1] / "scripts" / "package_report.py"
)
assert _SPEC and _SPEC.loader
PACKAGE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(PACKAGE)
ROOT = Path(__file__).parents[1]
SOURCE = "20261012T203545022355Z-exp-003-cadence"


def test_bundle_uses_complete_verified_original_outputs():
    files = PACKAGE.verified_evidence(ROOT, [SOURCE])
    assert f"runs/{SOURCE}/hits.parquet" in files
    assert f"runs/{SOURCE}/slice_summary.json" in files
    assert f"runs/{SOURCE}/manifest.json" in files


def test_bundle_refuses_changed_evidence(tmp_path):
    import shutil

    target = tmp_path / "runs" / SOURCE
    shutil.copytree(ROOT / "runs" / SOURCE, target)
    (target / "hits.parquet").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        PACKAGE.verified_evidence(tmp_path, [SOURCE])


def test_zip_has_fixed_metadata_and_sorted_content(tmp_path):
    a, b = tmp_path / "a.zip", tmp_path / "b.zip"
    PACKAGE.write_zip(a, {"z.txt": b"last", "a.txt": b"first"})
    PACKAGE.write_zip(b, {"a.txt": b"first", "z.txt": b"last"})
    assert a.read_bytes() == b.read_bytes()
    with ZipFile(a) as archive:
        assert archive.namelist() == ["a.txt", "z.txt"]
        assert archive.read("a.txt") == b"first"
