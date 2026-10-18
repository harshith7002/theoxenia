"""A public snapshot must be offline, traceable, and safe to browse."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from xenia.live.render import render_site

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_public_site", ROOT / "scripts/build_public_site.py"
)
assert SPEC is not None and SPEC.loader is not None
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key in {"href", "src"} and value:
                self.urls.append(value)


def test_public_snapshot_links_and_recovery(tmp_path: Path) -> None:
    now = datetime(2026, 10, 18, 12, tzinfo=UTC)
    first, second = tmp_path / "first", tmp_path / "second"
    for output in (first, second):
        state = BUILD.build_public_site(output, base_url="https://example.org/lab/", now=now)
        assert state.totals.hits == 273
        assert state.meta.is_mirror
        for page in output.rglob("*.html"):
            parser = Links()
            parser.feed(page.read_text())
            for url in parser.urls:
                parts = urlsplit(url)
                if parts.scheme or parts.netloc or not parts.path:
                    continue
                target = (page.parent / unquote(parts.path)).resolve()
                assert target.is_relative_to(output.resolve()), url
                assert target.is_file(), (page, url)
    assert (first / "index.html").read_bytes() == (second / "index.html").read_bytes()
    for path in (first / "downloads").iterdir():
        assert path.read_bytes() == (second / "downloads" / path.name).read_bytes()
    with pytest.raises(ValueError, match="new or empty"):
        BUILD.build_public_site(first, base_url="https://example.org/lab/")


def test_manifest_text_is_escaped_in_templates(demo_state, tmp_path: Path) -> None:
    hostile = '<img src=x onerror="alert(1)">'
    item = demo_state.gallery[0].model_copy(update={"target": hostile})
    state = demo_state.model_copy(update={"gallery": (item,)})
    state_path = tmp_path / "state.json"
    state_path.write_text(state.model_dump_json())
    render_site(
        state_path=state_path,
        runs_dir=ROOT / "tests/fixtures/live",
        output_dir=tmp_path / "site",
        repository_root=ROOT,
    )
    page = (tmp_path / "site/index.html").read_text()
    assert hostile not in page
    assert "&lt;img" in page
