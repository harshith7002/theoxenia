"""Health-check semantics and HTTP integration for Mission Control."""

from __future__ import annotations

import http.client
import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from xenia.live.models import WorkerStatus
from xenia.live.server import create_server, health_payload

NOW = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


def _write_state(
    path: Path,
    demo_state,
    *,
    heartbeat_age_seconds: int,
    demo: bool = False,
    now: datetime = NOW,
) -> None:
    """Persist a valid running worker state with a chosen heartbeat age."""
    meta = demo_state.meta.model_copy(update={"demo": demo})
    worker = demo_state.worker.model_copy(
        update={
            "status": WorkerStatus.RUNNING,
            "host": "test-host",
            "last_heartbeat": now - timedelta(seconds=heartbeat_age_seconds),
        }
    )
    state = demo_state.model_copy(update={"meta": meta, "worker": worker})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def test_fresh_live_heartbeat_returns_200(demo_state, tmp_path: Path) -> None:
    """A non-demo running worker with a fresh heartbeat is healthy."""
    state_path = tmp_path / "site" / "state.json"
    _write_state(state_path, demo_state, heartbeat_age_seconds=599)
    status, body = health_payload(state_path, now=NOW)
    assert status == 200
    assert body["status"] == "ok"
    assert body["heartbeat_age_seconds"] == 599


def test_ten_minute_boundary_is_healthy_but_older_is_stale(demo_state, tmp_path: Path) -> None:
    """Only heartbeat ages greater than ten minutes return 503."""
    state_path = tmp_path / "site" / "state.json"
    _write_state(state_path, demo_state, heartbeat_age_seconds=600)
    assert health_payload(state_path, now=NOW)[0] == 200
    _write_state(state_path, demo_state, heartbeat_age_seconds=601)
    status, body = health_payload(state_path, now=NOW)
    assert status == 503
    assert body["status"] == "stale"


def test_demo_state_is_never_reported_healthy(demo_state, tmp_path: Path) -> None:
    """A fixture heartbeat cannot be mistaken for a live worker."""
    state_path = tmp_path / "site" / "state.json"
    _write_state(state_path, demo_state, heartbeat_age_seconds=1, demo=True)
    status, body = health_payload(state_path, now=NOW)
    assert status == 503
    assert body["reason"] == "demo state is not a live worker"


def test_missing_state_returns_503(tmp_path: Path) -> None:
    """The health route fails closed when state is unavailable."""
    status, body = health_payload(tmp_path / "missing.json", now=NOW)
    assert status == 503
    assert body["status"] == "unavailable"


def test_worker_clock_in_future_is_not_healthy(demo_state, tmp_path: Path) -> None:
    """A future heartbeat does not create a false healthy state."""
    state_path = tmp_path / "site" / "state.json"
    _write_state(state_path, demo_state, heartbeat_age_seconds=-1)
    status, body = health_payload(state_path, now=NOW)
    assert status == 503
    assert body["reason"] == "worker clock is ahead"


def test_http_server_serves_page_and_demo_health_route(demo_state, tmp_path: Path) -> None:
    """The local page is available even though its demo heartbeat is not healthy."""
    site = tmp_path / "site"
    _write_state(site / "state.json", demo_state, heartbeat_age_seconds=1, demo=True)
    (site / "index.html").write_text("<h1>Demo page</h1>\n", encoding="utf-8")
    server = create_server(site, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request("GET", "/")
        page_response = connection.getresponse()
        assert page_response.status == 200
        assert b"Demo page" in page_response.read()
        connection.request("GET", "/healthz")
        health_response = connection.getresponse()
        payload = json.loads(health_response.read())
        assert health_response.status == 503
        assert payload["reason"] == "demo state is not a live worker"
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
