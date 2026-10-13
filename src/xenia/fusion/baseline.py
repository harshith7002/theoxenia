"""EXP-020 public-record baseline: CNEOS fireballs and GFZ Kp for one window."""

from __future__ import annotations

import hashlib
import json
import ssl
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from xenia.fusion.models import FusionBaseline
from xenia.live.models import RunManifest
from xenia.provenance import create_run_manifest, input_ref, new_run_id, output_ref

CNEOS_ENDPOINT = "https://ssd-api.jpl.nasa.gov/fireball.api"
GFZ_ENDPOINT = "https://kp.gfz.de/app/json/"
RECORDED_CNEOS_SHA256 = "8c51803de9a1f0bec29fcb163212d69b7996fcfb2ab1b7b5a89df676d1e5fcce"
RECORDED_GFZ_SHA256 = "22b8fb82c275247b70696a1150fe17f6561590bbe299a107592de4ea5b057276"
RECORDED_START = datetime(2004, 11, 14, tzinfo=UTC)
RECORDED_END = datetime(2004, 11, 15, tzinfo=UTC)
RECORDED_CNEOS_NAME = "cneos-window.json"
RECORDED_GFZ_NAME = "gfz-kp-2004-11-14.json"
Via = Literal["urllib", "curl", "recorded_response"]
NumbersFrom = Literal["live", "recorded_response"]


@dataclass(frozen=True)
class Fetched:
    """One completed HTTPS response. The body is the bytes that were hashed."""

    status: int
    body: bytes
    via: Via
    date_header: str | None


@dataclass(frozen=True)
class Obtained:
    """A source body plus whether this process measured it or reused a recorded one."""

    body: bytes
    sha256: str
    via: Via
    numbers_from: NumbersFrom
    http_status: int | None
    date_header: str | None
    error: str | None


Transport = Callable[[str], Fetched]


def cneos_url(start: datetime, end: datetime) -> str:
    """Build the fireball request. The API receives the time window and no radius."""
    return f"{CNEOS_ENDPOINT}?date-min={_stamp_seconds(start)}&date-max={_stamp_seconds(end)}"


def gfz_url(start: datetime, end: datetime) -> str:
    """Build the GFZ Kp request for the same UTC window."""
    return f"{GFZ_ENDPOINT}?start={_stamp_seconds(start)}Z&end={_stamp_seconds(end)}Z&index=Kp"


def parse_fireball(body: bytes) -> tuple[str, int, str]:
    """Return the API count token, its integer value, and the JSON type.

    ``count`` is the number of records in the requested time window. This parser
    does not apply a geographic radius.
    """
    payload = json.loads(body)
    if not isinstance(payload, dict) or "count" not in payload:
        raise ValueError("fireball body has no count")
    count = payload["count"]
    if isinstance(count, bool) or not isinstance(count, str | int):
        raise ValueError("fireball count is not an integer or an integer string")
    if isinstance(count, str):
        if not count.isascii() or not count.isdigit():
            raise ValueError("fireball count string is not a base-10 integer")
        return count, int(count), "string"
    return str(count), count, "integer"


def parse_kp(
    body: bytes, *, start: datetime, end: datetime
) -> tuple[float, tuple[float, ...], tuple[str, ...]]:
    """Return the maximum definitive Kp inside the inclusive UTC window."""
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Kp body is not an object")
    values = payload.get("Kp")
    times = payload.get("datetime")
    statuses = payload.get("status")
    arrays_are_lists = (
        isinstance(values, list) and isinstance(times, list) and isinstance(statuses, list)
    )
    if not arrays_are_lists:
        raise ValueError("Kp body is missing Kp, datetime, or status")
    if not (len(values) == len(times) == len(statuses)) or not values:
        raise ValueError("Kp arrays differ in length")
    selected: list[tuple[float, str]] = []
    for value, stamp, status in zip(values, times, statuses, strict=True):
        if status != "def":
            raise ValueError(f"Kp status {status!r} is not definitive")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("Kp value is not a number")
        if not isinstance(stamp, str):
            raise ValueError("Kp datetime is not a string")
        moment = _parse_utc(stamp)
        if start <= moment <= end:
            selected.append((float(value), stamp))
    if not selected:
        raise ValueError("no definitive Kp samples fall inside the window")
    numbers = tuple(item[0] for item in selected)
    stamps = tuple(item[1] for item in selected)
    return max(numbers), numbers, stamps


def urllib_then_curl(url: str, *, timeout_s: float = 25) -> Fetched:
    """GET one HTTPS URL. A TLS verification failure retries with system curl.

    Certificate checks stay on. This function does not pass ``verify=False`` or
    curl ``-k``.
    """
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-HTTPS URL: {url}")
    try:
        return _fetch_urllib(url, timeout_s=timeout_s)
    except urllib.error.URLError as exc:
        if not _tls_verify_failed(exc):
            raise
        return _fetch_curl(url, timeout_s=timeout_s)


def run_baseline(
    repository_root: Path,
    command: Sequence[str],
    *,
    lat_deg: float,
    lon_deg: float,
    start: datetime,
    end: datetime,
    radius_km: float,
    timeout_s: float = 25,
    transport: Transport | None = None,
) -> tuple[RunManifest, Path]:
    """Fetch both sources, write ``baseline.json``, and record a run manifest."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    started_at = datetime.now(UTC)
    root = repository_root.resolve()
    window_start = start.astimezone(UTC)
    window_end = end.astimezone(UTC)
    allow_recorded = window_start == RECORDED_START and window_end == RECORDED_END
    fetcher = transport or (lambda url: urllib_then_curl(url, timeout_s=timeout_s))
    cneos = _obtain(
        cneos_url(window_start, window_end),
        fixture=root / "tests" / "fixtures" / "fusion" / RECORDED_CNEOS_NAME,
        expected_sha256=RECORDED_CNEOS_SHA256,
        fetcher=fetcher,
        allow_recorded=allow_recorded,
    )
    gfz = _obtain(
        gfz_url(window_start, window_end),
        fixture=root / "tests" / "fixtures" / "fusion" / RECORDED_GFZ_NAME,
        expected_sha256=RECORDED_GFZ_SHA256,
        fetcher=fetcher,
        allow_recorded=allow_recorded,
    )
    count_raw, count, count_type = parse_fireball(cneos.body)
    kp_max, kp_values, kp_times = parse_kp(gfz.body, start=window_start, end=window_end)
    notes = _notes(cneos, gfz, radius_km=radius_km)
    baseline = FusionBaseline(
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        radius_km=radius_km,
        start=window_start,
        end=window_end,
        fireball_count_raw=count_raw,
        fireball_count=count,
        fireball_count_json_type=count_type,
        kp_max=kp_max,
        kp_values=kp_values,
        kp_times=kp_times,
        cneos_url=cneos_url(window_start, window_end),
        cneos_sha256=cneos.sha256,
        cneos_bytes=len(cneos.body),
        cneos_http_status=cneos.http_status,
        cneos_via=cneos.via,
        cneos_numbers_from=cneos.numbers_from,
        gfz_url=gfz_url(window_start, window_end),
        gfz_sha256=gfz.sha256,
        gfz_bytes=len(gfz.body),
        gfz_http_status=gfz.http_status,
        gfz_via=gfz.via,
        gfz_numbers_from=gfz.numbers_from,
        notes=notes,
    )
    run_id = new_run_id(started_at, "exp-020-baseline")
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    cneos_path = run_dir / "cneos.json"
    gfz_path = run_dir / "gfz.json"
    baseline_path = run_dir / "baseline.json"
    cneos_path.write_bytes(cneos.body)
    gfz_path.write_bytes(gfz.body)
    baseline_path.write_text(
        json.dumps(baseline.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    finished_at = datetime.now(UTC)
    both_live = cneos.numbers_from == "live" and gfz.numbers_from == "live"
    manifest, manifest_path = create_run_manifest(
        run_id=run_id,
        command=command,
        parameters={
            "lat_deg": lat_deg,
            "lon_deg": lon_deg,
            "radius_km": radius_km,
            "start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fireball_count": count,
            "fireball_count_raw": count_raw,
            "kp_max": kp_max,
            "space_track_queried": False,
            "fireball_request_limited_to_radius": False,
        },
        inputs=(
            input_ref(cneos_path, repository_root=root),
            input_ref(gfz_path, repository_root=root),
        ),
        outputs=(output_ref(baseline_path, repository_root=root),),
        started_at=started_at,
        finished_at=finished_at,
        outcome="baseline_measured" if both_live else "baseline_recorded",
        notes=notes,
        repository_root=root,
        demo=False,
        pillar="III · Fusion",
        experiment_id="EXP-020",
        manifest_path=run_dir / "manifest.json",
    )
    return manifest, manifest_path


def _obtain(
    url: str,
    *,
    fixture: Path,
    expected_sha256: str,
    fetcher: Transport,
    allow_recorded: bool,
) -> Obtained:
    try:
        fetched = fetcher(url)
        if fetched.status != 200:
            raise RuntimeError(f"HTTP {fetched.status} for {url}")
        digest = hashlib.sha256(fetched.body).hexdigest()
        return Obtained(
            body=fetched.body,
            sha256=digest,
            via=fetched.via,
            numbers_from="live",
            http_status=fetched.status,
            date_header=fetched.date_header,
            error=None,
        )
    except (OSError, urllib.error.URLError, subprocess.SubprocessError, RuntimeError) as exc:
        if not allow_recorded:
            raise RuntimeError(
                f"live fetch failed and this window has no recorded body: {url}"
            ) from exc
        if not fixture.is_file():
            raise RuntimeError(f"recorded body is missing: {fixture}") from exc
        raw = fixture.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_sha256:
            raise RuntimeError("recorded body sha256 does not match the measured response") from exc
        return Obtained(
            body=raw,
            sha256=digest,
            via="recorded_response",
            numbers_from="recorded_response",
            http_status=None,
            date_header=None,
            error=str(exc),
        )


def _notes(cneos: Obtained, gfz: Obtained, *, radius_km: float) -> tuple[str, ...]:
    return (
        (
            f"CNEOS request is the UTC window only. The {radius_km:g} km radius was not sent. "
            "count is the API record count for that window, not a count inside the radius."
        ),
        "Kp is the GFZ planetary index. It is not a value at the coordinate.",
        "Space-Track was not queried. No account was created. Satellite passes were not computed.",
        _source_note("CNEOS", cneos),
        _source_note("GFZ", gfz),
    )


def _source_note(name: str, obtained: Obtained) -> str:
    if obtained.numbers_from == "live":
        date = obtained.date_header or "absent"
        return (
            f"{name} numbers_from live via {obtained.via}. "
            f"HTTP {obtained.http_status}. Date header {date}. "
            f"{len(obtained.body)} bytes. SHA-256 {obtained.sha256}."
        )
    failure = obtained.error or "live fetch failed"
    return (
        f"{name} numbers_from recorded_response. The live attempt failed ({failure}). "
        "The bytes are the earlier measured response, checked by SHA-256 "
        f"{obtained.sha256}, {len(obtained.body)} bytes. This run did not replace them."
    )


def _fetch_urllib(url: str, *, timeout_s: float) -> Fetched:
    request = urllib.request.Request(url, headers={"User-Agent": "theoxenia-fusion/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        body = response.read()
        date = response.headers.get("Date")
        return Fetched(status=response.status, body=body, via="urllib", date_header=date)


def _fetch_curl(url: str, *, timeout_s: float) -> Fetched:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temporary:
        body_path = Path(temporary) / "body"
        header_path = Path(temporary) / "headers"
        command = _curl_command(
            url, timeout_s=timeout_s, body_path=body_path, header_path=header_path
        )
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=timeout_s + 5,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"curl exited {completed.returncode}: {detail}")
        status_text = completed.stdout.decode("utf-8", errors="replace").strip()
        if not status_text.isdigit():
            raise RuntimeError(f"curl did not report an HTTP status: {status_text!r}")
        header_text = header_path.read_text(encoding="utf-8", errors="replace")
        return Fetched(
            status=int(status_text),
            body=body_path.read_bytes(),
            via="curl",
            date_header=_last_date_header(header_text),
        )


def _curl_command(url: str, *, timeout_s: float, body_path: Path, header_path: Path) -> list[str]:
    command = [
        "/usr/bin/curl",
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        str(timeout_s),
        "--dump-header",
        str(header_path),
        "--output",
        str(body_path),
        "--write-out",
        "%{http_code}",
        url,
    ]
    return command


def _last_date_header(header_text: str) -> str | None:
    blocks = [block for block in header_text.split("\r\n\r\n") if block.strip()]
    if not blocks:
        blocks = [block for block in header_text.split("\n\n") if block.strip()]
    if not blocks:
        return None
    for line in blocks[-1].splitlines():
        if line.lower().startswith("date:"):
            return line.split(":", 1)[1].strip() or None
    return None


def _tls_verify_failed(exc: BaseException) -> bool:
    reason = exc.__cause__ or getattr(exc, "reason", None)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    return "CERTIFICATE_VERIFY_FAILED" in str(exc)


def _stamp_seconds(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp must be timezone-aware: {value}")
    return parsed.astimezone(UTC)
