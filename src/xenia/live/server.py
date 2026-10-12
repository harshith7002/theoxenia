"""Static HTTP serving and health checks for the local M0 page."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from xenia.live.models import LiveState, WorkerStatus

HEARTBEAT_STALE_SECONDS = 10 * 60


def health_payload(state_path: Path, *, now: datetime | None = None) -> tuple[int, dict[str, Any]]:
    """Return the HTTP status and JSON body for `/healthz`.

    A healthy response requires a running non-demo worker whose heartbeat is no
    more than ten minutes old. Static pages remain available while health is 503.
    """
    current_time = now or datetime.now(UTC)
    try:
        state = LiveState.model_validate_json(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return 503, {"status": "unavailable", "reason": f"state unavailable: {exc}"}

    heartbeat = state.worker.last_heartbeat
    if heartbeat is None:
        return 503, {"status": "unavailable", "heartbeat_age_seconds": None}

    age = (current_time - heartbeat).total_seconds()
    age_seconds = max(0, int(age))
    healthy = (
        not state.meta.demo
        and state.worker.status is WorkerStatus.RUNNING
        and 0 <= age <= HEARTBEAT_STALE_SECONDS
    )
    body: dict[str, Any] = {
        "status": "ok" if healthy else "stale",
        "heartbeat_age_seconds": age_seconds,
        "worker_status": state.worker.status.value,
    }
    if state.meta.demo:
        body["reason"] = "demo state is not a live worker"
    elif age < 0:
        body["reason"] = "worker clock is ahead"
    elif age > HEARTBEAT_STALE_SECONDS:
        body["reason"] = "heartbeat is older than ten minutes"
    elif state.worker.status is not WorkerStatus.RUNNING:
        body["reason"] = "worker is not running"
    return (200 if healthy else 503), body


def create_server(
    directory: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> ThreadingHTTPServer:
    """Create, but do not start, a static server with the heartbeat route."""
    root = directory.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"site directory does not exist: {root}")
    state_path = root / "state.json"

    class MissionControlHandler(SimpleHTTPRequestHandler):
        """Handler that adds the worker freshness endpoint."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def do_GET(self) -> None:
            if urlsplit(self.path).path != "/healthz":
                super().do_GET()
                return
            status, body = health_payload(state_path)
            encoded = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer((host, port), MissionControlHandler)
    server.daemon_threads = True
    return server


def serve(
    directory: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    """Serve generated static files until interrupted."""
    server = create_server(directory, host=host, port=port)
    print(f"Theoxenia Mission Control serving {directory.resolve()} at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local server.")
    finally:
        server.server_close()
