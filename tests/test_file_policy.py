"""Repository file-policy tests."""

from __future__ import annotations

from pathlib import Path

from xenia.file_policy import MAX_FILE_BYTES, problems


def test_file_under_limit_is_allowed(tmp_path: Path) -> None:
    """Small text assets and manifests remain commit-friendly."""
    file_path = tmp_path / "manifest.json"
    file_path.write_text("{}\n", encoding="utf-8")
    assert problems([str(file_path)]) == []


def test_large_file_is_rejected(tmp_path: Path) -> None:
    """Any staged file above two MiB is blocked regardless of extension."""
    file_path = tmp_path / "preview.bin"
    file_path.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    assert any("exceeds the 2 MiB" in item for item in problems([str(file_path)]))


def test_raw_science_formats_are_rejected(tmp_path: Path) -> None:
    """Raw telescope scan formats are blocked even when small."""
    file_path = tmp_path / "scan.fil"
    file_path.write_bytes(b"small placeholder")
    assert any("raw telescope/scan" in item for item in problems([str(file_path)]))


def test_data_directory_is_rejected(tmp_path: Path) -> None:
    """The ignored local data/ directory must not enter a commit."""
    file_path = tmp_path / "data" / "note.txt"
    file_path.parent.mkdir()
    file_path.write_text("local only", encoding="utf-8")
    assert any("data/ files are not committed" in item for item in problems([str(file_path)]))
