"""Known-answer tests for character error rate and the OCR command."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from xenia.cli import main
from xenia.disclosure.ocr import character_error_rate, count_ocr_pages, load_hand_lines, prompt_text

ROOT = Path(__file__).resolve().parents[1]


def test_character_error_rate_matches_hand_counted_edits() -> None:
    """One substitution in a three-character reference is one third."""
    distance, rate = character_error_rate("abx", "abc")
    assert distance == 1
    assert rate == pytest.approx(1 / 3)
    assert character_error_rate("abc", "abc") == (0, 0.0)
    assert character_error_rate("", "ab") == (2, 1.0)
    with pytest.raises(ValueError, match="empty"):
        character_error_rate("abc", "")


def test_load_hand_lines_rejects_an_empty_reference(tmp_path: Path) -> None:
    """A rectangle with no typed text is not a character error rate."""
    path = tmp_path / "lines.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        load_hand_lines(path)
    path.write_text(
        '[{"page": 1, "x0": 0, "y0": 0, "x1": 2, "y1": 2, "text": ""}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="empty"):
        load_hand_lines(path)


def test_count_ocr_pages_sums_the_recorded_counts(tmp_path: Path) -> None:
    """The total is the sum of pages_processed values already written in manifests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    paths = []
    for index, pages in enumerate((15, 25), start=1):
        run = repo / "runs" / f"run-{index}"
        run.mkdir(parents=True)
        manifest = run / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "experiment_id": "EXP-010",
                    "outcome": "ocr_completed",
                    "demo": False,
                    "run_id": f"run-{index}",
                    "parameters": {
                        "pdf": f"data/file-{index}.pdf",
                        "pages_processed": pages,
                    },
                }
            ),
            encoding="utf-8",
        )
        paths.append(manifest)
    manifest, _path = count_ocr_pages(repo, ["xenia", "disclosure", "count"], paths)
    assert manifest.parameters["pages_processed"] == 40
    assert manifest.outcome == "ocr_pages_counted"
    assert manifest.demo is False


def test_prompt_names_the_schema_and_forbids_a_conclusion() -> None:
    """The prompt is local text. It does not call a model."""
    text = prompt_text()
    assert "IncidentTelemetry" in text
    assert "Do not add a conclusion" in text
    assert "pages_processed" in text


def test_known_answer_pdf_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A generated page comes back through the same OCR path as a scan."""
    pytest.importorskip("pymupdf")
    pytest.importorskip("cv2")
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract is not installed")
    import pymupdf

    repo = tmp_path / "repo"
    repo.mkdir()
    pdf_path = repo / "known-answer.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 120), "THEOXENIA KNOWN ANSWER 20261013", fontsize=18)
    document.save(pdf_path)
    document.close()
    monkeypatch.chdir(repo)
    code = main(["disclosure", "ocr", "known-answer.pdf"])
    assert code == 0
    manifests = list((repo / "runs").rglob("manifest.json"))
    assert len(manifests) == 1
    ocr_files = list((repo / "runs").rglob("ocr.json"))
    text = ocr_files[0].read_text(encoding="utf-8")
    assert "THEOXENIA KNOWN ANSWER 20261013" in text


def test_validate_accepts_a_minimal_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """validate checks the model and does not read a PDF."""
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = repo / "ocr.json"
    payload.write_text(
        """
        {
          "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "source_bytes": 1,
          "page_count": 1,
          "pages_processed": 1,
          "tesseract_version": "tesseract 5.5.3",
          "pages": [{"page_index": 1, "text": "abc"}]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.chdir(repo)
    assert main(["disclosure", "validate", "ocr.json"]) == 0
    code = main(["disclosure", "prompt"])
    assert code == 0
