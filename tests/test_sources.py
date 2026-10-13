"""Known-answer tests for the data-source probe. The network is not used."""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from xenia.cli import main
from xenia.sources import SourceCatalog, _LiveRead, classify_live, load_catalog, run_sources_check

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "sources" / "unreachable.json"


def _live(
    *,
    status: int | None,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    error: str | None = None,
) -> _LiveRead:
    return _LiveRead(
        http_status=status,
        final_url="https://example.test/item",
        body=body,
        truncated=False,
        headers=headers or {},
        elapsed_s=0.01,
        error=error,
    )


def test_catalog_on_disk_has_nineteen_sources() -> None:
    """The checked-in mirror matches the Data Sources database row count."""
    catalog = load_catalog(REPOSITORY_ROOT / "configs" / "sources.yaml")
    assert len(catalog.sources) == 19
    assert catalog.sources[0].id == "mast-jwst"
    assert catalog.cap_bytes == 65536


def test_plain_http_without_the_flag_is_rejected(tmp_path: Path) -> None:
    """Plain HTTP stays off unless the row opts in or the host is loopback."""
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
cap_bytes: 128
timeout_seconds: 2
user_agent: theoxenia-sources-test/1
sources:
  - id: remote-http
    name: Remote
    notion_url: https://example.test/row
    endpoint: http://example.test/data
    probe_url: http://example.test/data
    access: "Open · no key"
    pillar: "I · Sensor"
    domain: Radio SETI
    formats: JSON
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="plain HTTP"):
        run_sources_check(
            tmp_path,
            ["xenia", "sources", "check"],
            config_path=path,
            out_path=tmp_path / "out.json",
        )


def test_classify_live_requires_bytes_and_optional_content_type() -> None:
    """2xx with a body verifies; empty, typed-wrong, and credential rows do not."""
    ok = _live(
        status=200,
        body=b"{}",
        headers={"content-type": "application/json", "content-length": "2"},
    )
    assert (
        classify_live(ok, credential_required=False, content_type_prefix="application/json")
        == "verified"
    )
    assert classify_live(ok, credential_required=True, content_type_prefix=None) == "blocked"
    empty = _live(status=200, headers={"content-length": "0"})
    assert classify_live(empty, credential_required=False, content_type_prefix=None) == "blocked"
    html = _live(status=200, body=b"<html>", headers={"content-type": "text/html"})
    html_verdict = classify_live(
        html, credential_required=False, content_type_prefix="application/json"
    )
    assert html_verdict == "blocked"
    missing = _live(status=None, error="URLError: timed out")
    assert classify_live(missing, credential_required=False, content_type_prefix=None) == "blocked"


def test_local_server_is_a_live_measurement(tmp_path: Path) -> None:
    """A loopback response records the status, byte count, and hash we served."""
    body = b'{"ok":true}\n'

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            payload = body
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Date", "Mon, 12 Oct 2026 22:10:00 GMT")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        path = _write_catalog(
            tmp_path,
            probe=f"http://127.0.0.1:{port}/item",
            fixture=False,
        )
        document, manifest_path = run_sources_check(
            tmp_path,
            ["xenia", "sources", "check"],
            config_path=path,
            out_path=tmp_path / "runs" / "manual" / "sources_check.json",
        )
    finally:
        server.shutdown()
    result = document.results[0]
    assert result.verdict == "verified"
    assert result.numbers_from == "live"
    assert result.synthetic is False
    assert result.http_status == 200
    assert result.bytes_read == len(body)
    assert result.sha256_of_bytes_read == hashlib.sha256(body).hexdigest()
    assert result.date_header == "Mon, 12 Oct 2026 22:10:00 GMT"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["demo"] is False
    assert manifest["outcome"] == "sources_checked"
    assert manifest["parameters"]["verified_count"] == 1


def test_unreachable_host_uses_the_synthetic_fixture(tmp_path: Path) -> None:
    """A refused connection records the fixture body and says it is not live."""
    fixture = tmp_path / "fixture.json"
    fixture.write_bytes(FIXTURE.read_bytes())
    path = _write_catalog(tmp_path, probe="http://127.0.0.1:9/missing", fixture=True)
    # Port 9 is discarded; nothing should accept it. Point the catalog at the copied fixture.
    text = path.read_text(encoding="utf-8").replace(
        "tests/fixtures/sources/unreachable.json",
        "fixture.json",
    )
    path.write_text(text, encoding="utf-8")
    document, manifest_path = run_sources_check(
        tmp_path,
        ["xenia", "sources", "check", "--out", "sources_check.json"],
        config_path=path,
        out_path=tmp_path / "sources_check.json",
    )
    result = document.results[0]
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected = str(payload["body_text"]).encode("utf-8")
    assert result.verdict == "synthetic"
    assert result.numbers_from == "fixture"
    assert result.probe_url == "synthetic://loop"
    assert result.http_status == 200
    assert result.bytes_read == len(expected)
    assert result.sha256_of_bytes_read == hashlib.sha256(expected).hexdigest()
    assert result.error is not None
    assert "not a live measurement" in result.note
    assert result.elapsed_s is not None and result.elapsed_s >= 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["demo"] is True
    assert manifest["outcome"] == "sources_checked_with_synthetic"
    assert "loop" in manifest["notes"][1]


def test_cli_writes_the_check_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The console command stays inside the working tree."""
    body = b"hello"
    server, port = _serve(body)
    try:
        _write_catalog(tmp_path, probe=f"http://127.0.0.1:{port}/item", fixture=False)
        monkeypatch.chdir(tmp_path)
        code = main(
            [
                "sources",
                "check",
                "--config",
                "sources.yaml",
                "--out",
                "runs/cli/sources_check.json",
            ]
        )
    finally:
        server.shutdown()
    assert code == 0
    check_path = tmp_path / "runs" / "cli" / "sources_check.json"
    written = json.loads(check_path.read_text(encoding="utf-8"))
    assert written["results"][0]["bytes_read"] == len(body)
    assert written["schema_version"] == "0.1"


def test_duplicate_ids_are_rejected() -> None:
    """Two rows cannot share an id."""
    with pytest.raises(ValueError, match="unique"):
        SourceCatalog.model_validate(
            {
                "sources": [
                    _row("same"),
                    _row("same"),
                ]
            }
        )


def _row(source_id: str) -> dict[str, object]:
    return {
        "id": source_id,
        "name": "Example",
        "notion_url": "https://example.test/row",
        "endpoint": "https://example.test/data",
        "probe_url": "https://example.test/data",
        "access": "Open · no key",
        "pillar": "I · Sensor",
        "domain": "Radio SETI",
        "formats": "JSON",
    }


def _write_catalog(tmp_path: Path, *, probe: str, fixture: bool) -> Path:
    fixture_line = (
        "    synthetic_fixture: tests/fixtures/sources/unreachable.json\n" if fixture else ""
    )
    path = tmp_path / "sources.yaml"
    path.write_text(
        f"""
cap_bytes: 128
timeout_seconds: 2
user_agent: theoxenia-sources-test/1
sources:
  - id: loop
    name: Loopback
    notion_url: https://example.test/row
    endpoint: {probe}
    probe_url: {probe}
    access: "Open · no key"
    pillar: "I · Sensor"
    domain: Radio SETI
    formats: JSON
    content_type_prefix: application/json
{fixture_line}""",
        encoding="utf-8",
    )
    return path


def _serve(body: bytes) -> tuple[ThreadingHTTPServer, int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    address = server.server_address
    assert isinstance(address, tuple)
    return server, int(address[1])
