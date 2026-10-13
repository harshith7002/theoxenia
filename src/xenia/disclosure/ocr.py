"""OCR one PDF with PyMuPDF, OpenCV, and Tesseract."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from xenia.disclosure.models import IncidentTelemetry, PageTranscript
from xenia.live.models import RunManifest
from xenia.provenance import create_run_manifest, input_ref, new_run_id, output_ref

PROMPT = """Fill an IncidentTelemetry JSON object from the OCR page text only.
Use null for source_url, case_date, and location when the page text does not
state them. Do not add a conclusion, a verdict, or a field that is not in the
schema. pages_processed must equal the number of page objects.
"""


def character_error_rate(hypothesis: str, reference: str) -> tuple[int, float]:
    """Return Levenshtein distance and that distance divided by the reference length."""
    if reference == "":
        raise ValueError("reference text is empty")
    distance = _levenshtein(hypothesis, reference)
    return distance, distance / len(reference)


def prompt_text() -> str:
    """Return the extraction prompt and the IncidentTelemetry JSON Schema."""
    schema = json.dumps(IncidentTelemetry.model_json_schema(), indent=2, sort_keys=True)
    return f"{PROMPT}\n{schema}\n"


class HandLine(NamedTuple):
    """One rectangle on the 2x page render and the text read from that image."""

    page: int
    x0: int
    y0: int
    x1: int
    y1: int
    text: str


def load_hand_lines(path: Path) -> tuple[HandLine, ...]:
    """Load hand-read rectangles. The file is typed before OCR of those crops."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("hand lines must be a non-empty JSON list")
    lines: list[HandLine] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each hand line must be a JSON object")
        page = item.get("page")
        text = item.get("text")
        box = [item.get("x0"), item.get("y0"), item.get("x1"), item.get("y1")]
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError("hand line page must be an integer starting at 1")
        if not isinstance(text, str) or text == "":
            raise ValueError("hand line text is empty")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in box):
            raise ValueError("hand line box coordinates must be integers")
        x0, y0, x1, y1 = box
        if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
            raise ValueError("hand line box is empty or negative")
        lines.append(HandLine(page=page, x0=x0, y0=y0, x1=x1, y1=y1, text=text))
    return tuple(lines)


def run_ocr(
    repository_root: Path,
    command: Sequence[str],
    pdf_path: Path,
    *,
    source_url: str | None = None,
    references: dict[int, str] | None = None,
    hand_lines_path: Path | None = None,
    tesseract_bin: str = "tesseract",
) -> tuple[RunManifest, Path]:
    """Render, grayscale, and OCR every page. Reference text is optional."""
    hand_lines = () if hand_lines_path is None else load_hand_lines(hand_lines_path)
    started_at = datetime.now(UTC)
    root = repository_root.resolve()
    source = pdf_path.resolve()
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"pdf must stay inside repository: {pdf_path}") from exc
    if source.suffix.lower() != ".pdf":
        raise ValueError("ocr input must be a PDF")
    raw = source.read_bytes()
    cv2, pymupdf = _load_stack()
    version = _tesseract_version(tesseract_bin)
    document = pymupdf.open(source)
    try:
        page_count = document.page_count
        if page_count < 1:
            raise ValueError("pdf has no pages")
        transcripts: list[PageTranscript] = []
        scored: list[dict[str, object]] = []
        for index in range(page_count):
            pixmap = document[index].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            png = pixmap.tobytes("png")
            text = _ocr_png(cv2, png, tesseract_bin)
            for line in hand_lines:
                if line.page != index + 1:
                    continue
                hypothesis = _ocr_png(
                    cv2,
                    _crop_png(cv2, png, line.x0, line.y0, line.x1, line.y1),
                    tesseract_bin,
                )
                distance, rate = character_error_rate(hypothesis, line.text)
                scored.append(
                    {
                        "page_index": line.page,
                        "x0": line.x0,
                        "y0": line.y0,
                        "x1": line.x1,
                        "y1": line.y1,
                        "reference_text": line.text,
                        "hypothesis_text": hypothesis,
                        "levenshtein": distance,
                        "character_error_rate": rate,
                    }
                )
            reference = None if references is None else references.get(index + 1)
            distance: int | None = None
            rate: float | None = None
            if reference is not None:
                distance, rate = character_error_rate(text, reference)
            transcripts.append(
                PageTranscript(
                    page_index=index + 1,
                    text=text,
                    reference_text=reference,
                    character_error_rate=rate,
                    levenshtein=distance,
                )
            )
    finally:
        document.close()
    if len(scored) != len(hand_lines):
        raise ValueError("a hand line page is outside this PDF")
    line_pages = {line.page for line in hand_lines}
    checked = sum(
        page.character_error_rate is not None or page.page_index in line_pages
        for page in transcripts
    )
    notes_list = [
        "PDF bytes are not committed. The manifest records the SHA-256 of the file that was read.",
        "OpenCV converted each rendered page to grayscale before Tesseract.",
        "case_date and location are null. They were not copied out of the OCR text.",
        f"Hand-checked pages: {checked}. A missing reference is not a character error rate.",
    ]
    if hand_lines:
        notes_list.append(
            "Each hand line is one rectangle on the 2x render. The rate divides the "
            "Levenshtein distance by the reference length for that rectangle only."
        )
    notes = tuple(notes_list)
    payload = IncidentTelemetry(
        source_url=source_url,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_bytes=len(raw),
        page_count=page_count,
        pages_processed=page_count,
        tesseract_version=version,
        pages=tuple(transcripts),
        notes=notes,
    )
    run_id = new_run_id(started_at, "exp-010-ocr")
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ocr_path = run_dir / "ocr.json"
    ocr_path.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    rates = [
        page.character_error_rate for page in transcripts if page.character_error_rate is not None
    ]
    outputs = [output_ref(ocr_path, repository_root=root)]
    if scored:
        hand_path = run_dir / "hand_lines.json"
        hand_path.write_text(
            json.dumps(scored, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        outputs.append(output_ref(hand_path, repository_root=root))
    inputs = [input_ref(source, repository_root=root)]
    if hand_lines_path is not None:
        inputs.append(input_ref(hand_lines_path, repository_root=root))
    parameters: dict[str, object] = {
        "pdf": source.relative_to(root).as_posix(),
        "source_url": source_url,
        "pages_processed": page_count,
        "hand_checked_pages": checked,
        "character_error_rates": rates,
        "tesseract_version": version,
    }
    if scored:
        parameters["hand_lines"] = scored
    finished_at = datetime.now(UTC)
    manifest, manifest_path = create_run_manifest(
        run_id=run_id,
        command=command,
        parameters=parameters,
        inputs=tuple(inputs),
        outputs=tuple(outputs),
        started_at=started_at,
        finished_at=finished_at,
        outcome="ocr_completed",
        notes=notes,
        repository_root=root,
        demo=False,
        pillar="II · Disclosure",
        experiment_id="EXP-010",
        manifest_path=run_dir / "manifest.json",
    )
    return manifest, manifest_path


def _crop_png(cv2: Any, png: bytes, x0: int, y0: int, x1: int, y1: int) -> bytes:
    """Cut one rectangle from the rendered page. The slice matches the hand-read crop."""
    import numpy as np

    encoded = np.frombuffer(png, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("OpenCV could not read the rendered page")
    height, width = image.shape[:2]
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError(
            f"hand line box is outside the rendered page: {x0},{y0},{x1},{y1} page {width}x{height}"
        )
    ok, crop = cv2.imencode(".png", image[y0:y1, x0:x1])
    if not ok:
        raise RuntimeError("OpenCV could not encode a hand-line crop")
    return crop.tobytes()


def count_ocr_pages(
    repository_root: Path,
    command: Sequence[str],
    manifest_paths: Sequence[Path],
) -> tuple[RunManifest, Path]:
    """Sum pages_processed from finished EXP-010 OCR manifests. No new OCR."""
    started_at = datetime.now(UTC)
    root = repository_root.resolve()
    if not manifest_paths:
        raise ValueError("count needs at least one OCR manifest")
    rows: list[dict[str, object]] = []
    total = 0
    inputs = []
    for path in manifest_paths:
        resolved = path.resolve()
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"manifest is not an object: {path}")
        if payload.get("experiment_id") != "EXP-010" or payload.get("outcome") != "ocr_completed":
            raise ValueError(f"not an EXP-010 OCR manifest: {path}")
        if payload.get("demo") is not False:
            raise ValueError(f"OCR manifest is not a measured run: {path}")
        parameters = payload.get("parameters")
        if not isinstance(parameters, dict):
            raise ValueError(f"OCR manifest has no parameters: {path}")
        pages = parameters.get("pages_processed")
        if not isinstance(pages, int) or isinstance(pages, bool) or pages < 1:
            raise ValueError(f"pages_processed is not a positive int: {path}")
        total += pages
        rows.append(
            {
                "run_id": payload.get("run_id"),
                "pdf": parameters.get("pdf"),
                "pages_processed": pages,
            }
        )
        inputs.append(input_ref(resolved, repository_root=root))
    run_id = new_run_id(started_at, "exp-010-count")
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    count_path = run_dir / "count.json"
    count_path.write_text(
        json.dumps({"pages_processed": total, "runs": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    notes = (
        "pages_processed is the sum of the listed OCR runs. It is not the page count of one PDF.",
        "No page was OCR'd again for this manifest.",
    )
    finished_at = datetime.now(UTC)
    return create_run_manifest(
        run_id=run_id,
        command=command,
        parameters={"pages_processed": total, "runs": rows},
        inputs=tuple(inputs),
        outputs=(output_ref(count_path, repository_root=root),),
        started_at=started_at,
        finished_at=finished_at,
        outcome="ocr_pages_counted",
        notes=notes,
        repository_root=root,
        demo=False,
        pillar="II · Disclosure",
        experiment_id="EXP-010",
        manifest_path=run_dir / "manifest.json",
    )


def _ocr_png(cv2: Any, png: bytes, tesseract_bin: str) -> str:
    import numpy as np

    encoded = np.frombuffer(png, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("OpenCV could not read the rendered page")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ok, gray_png = cv2.imencode(".png", gray)
    if not ok:
        raise RuntimeError("OpenCV could not encode the grayscale page")
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temporary:
        image_path = Path(temporary) / "page.png"
        image_path.write_bytes(gray_png.tobytes())
        completed = subprocess.run(
            [tesseract_bin, str(image_path), "stdout", "--psm", "6"],
            check=False,
            capture_output=True,
            timeout=180,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"tesseract exited {completed.returncode}: {detail}")
    return completed.stdout.decode("utf-8", errors="replace")


def _tesseract_version(tesseract_bin: str) -> str:
    completed = subprocess.run(
        [tesseract_bin, "--version"],
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"tesseract --version exited {completed.returncode}: {detail}")
    text = completed.stdout.decode("utf-8", errors="replace").strip()
    first = text.splitlines()[0].strip() if text else ""
    if not first:
        raise RuntimeError("tesseract --version returned no version line")
    return first


def _load_stack() -> tuple[object, object]:
    try:
        import cv2
        import pymupdf
    except ImportError as exc:
        raise RuntimeError(
            "pymupdf and opencv are required. Install the disclosure extra."
        ) from exc
    return cv2, pymupdf


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            replace = previous[j - 1] + (left_char != right_char)
            current.append(min(insert, delete, replace))
        previous = current
    return previous[-1]
