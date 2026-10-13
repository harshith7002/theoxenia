"""Known-answer tests for the EXP-020 CNEOS and GFZ baseline."""

from __future__ import annotations

import json
import ssl
import subprocess
import urllib.error
from pathlib import Path

import pytest
from pydantic import ValidationError

from xenia.cli import main
from xenia.fusion.baseline import (
    RECORDED_CNEOS_SHA256,
    RECORDED_GFZ_SHA256,
    Fetched,
    _curl_command,
    _fetch_curl,
    _fetch_urllib,
    _last_date_header,
    _tls_verify_failed,
    cneos_url,
    gfz_url,
    parse_fireball,
    parse_kp,
    run_baseline,
    urllib_then_curl,
)
from xenia.fusion.models import FusionBaseline
from xenia.live.models import RunManifest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "fusion"
START = "2004-11-14T00:00:00Z"
END = "2004-11-15T00:00:00Z"


def _window():
    from datetime import datetime

    return (
        datetime.fromisoformat("2004-11-14T00:00:00+00:00"),
        datetime.fromisoformat("2004-11-15T00:00:00+00:00"),
    )


def _copy_fixtures(repo: Path) -> None:
    destination = repo / "tests" / "fixtures" / "fusion"
    destination.mkdir(parents=True)
    for name in ("cneos-window.json", "gfz-kp-2004-11-14.json"):
        (destination / name).write_bytes((FIXTURES / name).read_bytes())


def _live_transport(url: str, timeout_s: float = 25) -> Fetched:
    if "fireball.api" in url:
        body = (FIXTURES / "cneos-window.json").read_bytes()
        return Fetched(
            status=200,
            body=body,
            via="urllib",
            date_header="Mon, 12 Oct 2026 22:22:15 GMT",
        )
    body = (FIXTURES / "gfz-kp-2004-11-14.json").read_bytes()
    return Fetched(
        status=200,
        body=body,
        via="urllib",
        date_header="Mon, 12 Oct 2026 22:10:03 GMT",
    )


def _fail_transport(url: str) -> Fetched:
    raise urllib.error.URLError(OSError("CERTIFICATE_VERIFY_FAILED"))


def test_recorded_bodies_match_the_measured_hashes() -> None:
    """The committed fixtures are the earlier measured responses, byte for byte."""
    import hashlib

    cneos = (FIXTURES / "cneos-window.json").read_bytes()
    gfz = (FIXTURES / "gfz-kp-2004-11-14.json").read_bytes()
    assert hashlib.sha256(cneos).hexdigest() == RECORDED_CNEOS_SHA256
    assert hashlib.sha256(gfz).hexdigest() == RECORDED_GFZ_SHA256
    assert len(cneos) == 82
    assert len(gfz) == 394


def test_parser_reports_the_measured_count_and_planetary_maximum() -> None:
    """Count stays a string token, and Kp max is computed from the nine samples."""
    raw, count, kind = parse_fireball((FIXTURES / "cneos-window.json").read_bytes())
    assert raw == "0"
    assert count == 0
    assert kind == "string"
    start, end = _window()
    maximum, values, times = parse_kp(
        (FIXTURES / "gfz-kp-2004-11-14.json").read_bytes(), start=start, end=end
    )
    assert values == (4.0, 2.667, 2.0, 1.333, 1.0, 1.333, 1.0, 0.333, 0.333)
    assert maximum == 4.0
    assert times[0] == "2004-11-14T00:00:00Z"
    assert times[-1] == "2004-11-15T00:00:00Z"
    from datetime import timedelta

    later_values = parse_kp(
        (FIXTURES / "gfz-kp-2004-11-14.json").read_bytes(),
        start=start + timedelta(hours=3),
        end=end,
    )[1]
    assert later_values[0] == 2.667
    assert 4.0 not in later_values
    other_raw, other_count, other_kind = parse_fireball(b'{"count": 2}')
    assert (other_raw, other_count, other_kind) == ("2", 2, "integer")


def test_requests_carry_the_time_window_and_not_the_radius() -> None:
    """Neither URL receives the coordinate or the 800 km radius."""
    start, end = _window()
    fireball = cneos_url(start, end)
    index = gfz_url(start, end)
    assert fireball == (
        "https://ssd-api.jpl.nasa.gov/fireball.api"
        "?date-min=2004-11-14T00:00:00&date-max=2004-11-15T00:00:00"
    )
    assert index == (
        "https://kp.gfz.de/app/json/?start=2004-11-14T00:00:00Z&end=2004-11-15T00:00:00Z&index=Kp"
    )
    for url in (fireball, index):
        assert "800" not in url
        assert "31.0" not in url
        assert "-118.5" not in url


def test_live_transport_writes_a_non_demo_manifest(tmp_path: Path) -> None:
    """A successful fetch records the parsed numbers and leaves demo false."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _copy_fixtures(repo)
    start, end = _window()
    manifest, manifest_path = run_baseline(
        repo,
        ["xenia", "fusion", "baseline"],
        lat_deg=31.0,
        lon_deg=-118.5,
        start=start,
        end=end,
        radius_km=800,
        transport=_live_transport,
    )
    loaded = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assert loaded == manifest
    assert loaded.demo is False
    assert loaded.experiment_id == "EXP-020"
    assert loaded.pillar == "III · Fusion"
    assert loaded.outcome == "baseline_measured"
    assert loaded.parameters["fireball_count"] == 0
    assert loaded.parameters["fireball_count_raw"] == "0"
    assert loaded.parameters["kp_max"] == 4.0
    assert loaded.parameters["space_track_queried"] is False
    assert loaded.parameters["fireball_request_limited_to_radius"] is False
    baseline_path = manifest_path.parent / "baseline.json"
    baseline = FusionBaseline.model_validate_json(baseline_path.read_text(encoding="utf-8"))
    assert baseline.fireball_count == 0
    assert baseline.kp_max == 4.0
    assert baseline.fireball_request_limited_to_radius is False
    assert baseline.kp_is_planetary is True
    assert baseline.space_track_queried is False
    assert baseline.cneos_sha256 == RECORDED_CNEOS_SHA256
    assert baseline.gfz_sha256 == RECORDED_GFZ_SHA256
    assert "not a count inside the radius" in baseline.notes[0]
    assert "planetary index" in baseline.notes[1]
    assert "Space-Track was not queried" in baseline.notes[2]


def test_transport_failure_uses_the_recorded_response_and_says_so(tmp_path: Path) -> None:
    """An unreachable source reuses the measured body and does not invent a count."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _copy_fixtures(repo)
    start, end = _window()
    manifest, manifest_path = run_baseline(
        repo,
        ["xenia", "fusion", "baseline"],
        lat_deg=31.0,
        lon_deg=-118.5,
        start=start,
        end=end,
        radius_km=800,
        transport=_fail_transport,
    )
    assert manifest.demo is False
    assert manifest.outcome == "baseline_recorded"
    assert manifest.parameters["fireball_count"] == 0
    assert manifest.parameters["kp_max"] == 4.0
    baseline = json.loads((manifest_path.parent / "baseline.json").read_text(encoding="utf-8"))
    assert baseline["cneos_numbers_from"] == "recorded_response"
    assert baseline["gfz_numbers_from"] == "recorded_response"
    assert "This run did not replace them." in " ".join(baseline["notes"])


def test_wrong_recorded_hash_writes_no_baseline(tmp_path: Path) -> None:
    """A fixture that is not the measured response cannot supply a number."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _copy_fixtures(repo)
    (repo / "tests" / "fixtures" / "fusion" / "cneos-window.json").write_bytes(b'{"count":"9"}')
    start, end = _window()
    with pytest.raises(RuntimeError, match="sha256"):
        run_baseline(
            repo,
            ["xenia", "fusion", "baseline"],
            lat_deg=31.0,
            lon_deg=-118.5,
            start=start,
            end=end,
            radius_km=800,
            transport=_fail_transport,
        )
    assert list(repo.rglob("baseline.json")) == []


def test_unrecorded_window_does_not_reuse_the_2004_body(tmp_path: Path) -> None:
    """The 2004 fixtures are not a measurement for a different window."""
    from datetime import UTC, datetime

    repo = tmp_path / "repo"
    repo.mkdir()
    _copy_fixtures(repo)
    with pytest.raises(RuntimeError, match="no recorded body"):
        run_baseline(
            repo,
            ["xenia", "fusion", "baseline"],
            lat_deg=31.0,
            lon_deg=-118.5,
            start=datetime(2005, 1, 1, tzinfo=UTC),
            end=datetime(2005, 1, 2, tzinfo=UTC),
            radius_km=800,
            transport=_fail_transport,
        )
    assert list(repo.rglob("baseline.json")) == []


def test_tls_verification_failure_retries_with_curl_and_other_errors_do_not(monkeypatch) -> None:
    """Only a certificate failure may fall through to system curl."""

    def boom_tls(url: str, *, timeout_s: float) -> Fetched:
        raise urllib.error.URLError(OSError("[SSL: CERTIFICATE_VERIFY_FAILED]"))

    def boom_timeout(url: str, *, timeout_s: float) -> Fetched:
        raise urllib.error.URLError(TimeoutError("timed out"))

    def curl(url: str, *, timeout_s: float) -> Fetched:
        return Fetched(status=200, body=b"{}", via="curl", date_header=None)

    monkeypatch.setattr("xenia.fusion.baseline._fetch_urllib", boom_tls)
    monkeypatch.setattr("xenia.fusion.baseline._fetch_curl", curl)
    assert urllib_then_curl("https://example.test/path").via == "curl"

    monkeypatch.setattr("xenia.fusion.baseline._fetch_urllib", boom_timeout)
    with pytest.raises(urllib.error.URLError):
        urllib_then_curl("https://example.test/path")


def test_curl_command_does_not_disable_tls(tmp_path: Path) -> None:
    """The curl argv keeps the operating-system trust store."""
    command = _curl_command(
        "https://ssd-api.jpl.nasa.gov/fireball.api",
        timeout_s=25,
        body_path=tmp_path / "body",
        header_path=tmp_path / "headers",
    )
    assert command[0] == "/usr/bin/curl"
    assert "-k" not in command
    assert "--insecure" not in command
    assert "https://ssd-api.jpl.nasa.gov/fireball.api" in command


def test_cli_runs_the_baseline_against_a_stand_in_transport(tmp_path: Path, monkeypatch) -> None:
    """The documented command writes a manifest inside the working tree."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _copy_fixtures(repo)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("xenia.fusion.baseline.urllib_then_curl", _live_transport)
    code = main(
        [
            "fusion",
            "baseline",
            "--lat",
            "31.0",
            "--lon",
            "-118.5",
            "--start",
            START,
            "--end",
            END,
            "--radius-km",
            "800",
        ]
    )
    assert code == 0
    manifests = list((repo / "runs").rglob("manifest.json"))
    assert len(manifests) == 1
    loaded = RunManifest.model_validate_json(manifests[0].read_text(encoding="utf-8"))
    assert loaded.parameters["fireball_count"] == 0
    assert loaded.parameters["kp_max"] == 4.0
    assert loaded.demo is False


def test_parsers_reject_bodies_that_are_not_measurements() -> None:
    """A malformed payload raises before any count or Kp value is returned."""
    start, end = _window()
    with pytest.raises(ValueError, match="no count"):
        parse_fireball(b"[]")
    with pytest.raises(ValueError, match="not an integer"):
        parse_fireball(b'{"count": true}')
    with pytest.raises(ValueError, match="base-10"):
        parse_fireball(b'{"count": "0.5"}')
    with pytest.raises(ValueError, match="not an object"):
        parse_kp(b"[]", start=start, end=end)
    with pytest.raises(ValueError, match="missing"):
        parse_kp(b'{"Kp": null}', start=start, end=end)
    with pytest.raises(ValueError, match="differ in length"):
        parse_kp(
            b'{"Kp": [1.0], "datetime": ["2004-11-14T00:00:00Z"], "status": []}',
            start=start,
            end=end,
        )
    with pytest.raises(ValueError, match="not definitive"):
        parse_kp(
            b'{"Kp": [1.0], "datetime": ["2004-11-14T00:00:00Z"], "status": ["pre"]}',
            start=start,
            end=end,
        )
    with pytest.raises(ValueError, match="not a number"):
        parse_kp(
            b'{"Kp": [true], "datetime": ["2004-11-14T00:00:00Z"], "status": ["def"]}',
            start=start,
            end=end,
        )
    with pytest.raises(ValueError, match="not a string"):
        parse_kp(b'{"Kp": [1.0], "datetime": [1], "status": ["def"]}', start=start, end=end)
    later = start.replace(year=2006)
    with pytest.raises(ValueError, match="no definitive"):
        parse_kp(
            (FIXTURES / "gfz-kp-2004-11-14.json").read_bytes(),
            start=later,
            end=later.replace(day=15),
        )


def test_http_error_and_missing_fixture_do_not_invent_a_number(tmp_path: Path) -> None:
    """A non-200 response falls back only when the measured file is present."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _copy_fixtures(repo)
    (repo / "tests" / "fixtures" / "fusion" / "gfz-kp-2004-11-14.json").unlink()
    start, end = _window()

    def http_500(url: str) -> Fetched:
        return Fetched(status=500, body=b"nope", via="urllib", date_header=None)

    with pytest.raises(RuntimeError, match="missing"):
        run_baseline(
            repo,
            ["xenia", "fusion", "baseline"],
            lat_deg=31.0,
            lon_deg=-118.5,
            start=start,
            end=end,
            radius_km=800,
            transport=http_500,
        )
    assert list(repo.rglob("baseline.json")) == []


def test_urllib_and_curl_readers_keep_status_body_and_date(monkeypatch, tmp_path: Path) -> None:
    """Both transports return the bytes they actually received."""

    class _Response:
        status = 200
        headers = {"Date": "Mon, 12 Oct 2026 22:22:15 GMT"}

        def read(self) -> bytes:
            return b'{"count":"0"}'

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    monkeypatch.setattr(
        "xenia.fusion.baseline.urllib.request.urlopen",
        lambda *args, **kwargs: _Response(),
    )
    fetched = _fetch_urllib("https://ssd-api.jpl.nasa.gov/fireball.api", timeout_s=1)
    assert fetched.via == "urllib"
    assert fetched.body == b'{"count":"0"}'
    assert fetched.date_header == "Mon, 12 Oct 2026 22:22:15 GMT"

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        output = Path(command[command.index("--output") + 1])
        headers = Path(command[command.index("--dump-header") + 1])
        output.write_bytes(b'{"count":"0"}')
        headers.write_text(
            "HTTP/1.1 200 OK\r\nDate: Mon, 12 Oct 2026 22:22:15 GMT\r\n\r\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout=b"200", stderr=b"")

    monkeypatch.setattr("xenia.fusion.baseline.subprocess.run", fake_run)
    curled = _fetch_curl("https://ssd-api.jpl.nasa.gov/fireball.api", timeout_s=1)
    assert curled.via == "curl"
    assert curled.status == 200
    assert curled.date_header == "Mon, 12 Oct 2026 22:22:15 GMT"

    def failed_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 22, stdout=b"", stderr=b"tls")

    monkeypatch.setattr("xenia.fusion.baseline.subprocess.run", failed_run)
    with pytest.raises(RuntimeError, match="curl exited 22"):
        _fetch_curl("https://ssd-api.jpl.nasa.gov/fireball.api", timeout_s=1)

    def blank_status(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        output = Path(command[command.index("--output") + 1])
        headers = Path(command[command.index("--dump-header") + 1])
        output.write_bytes(b"")
        headers.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=b"nope", stderr=b"")

    monkeypatch.setattr("xenia.fusion.baseline.subprocess.run", blank_status)
    with pytest.raises(RuntimeError, match="HTTP status"):
        _fetch_curl("https://ssd-api.jpl.nasa.gov/fireball.api", timeout_s=1)


def test_header_and_tls_helpers_cover_the_recorded_failure_shapes() -> None:
    """Date parsing and the certificate check match the failure seen on this host."""
    assert _last_date_header("") is None
    assert _last_date_header("\n\n") is None
    assert _last_date_header("HTTP/1.1 200 OK\n\nDate: \n") is None
    assert (
        _last_date_header("HTTP/1.1 302\n\nHTTP/1.1 200\nDate: Mon, 12 Oct 2026 22:22:15 GMT\n")
        == "Mon, 12 Oct 2026 22:22:15 GMT"
    )
    reason = ssl.SSLCertVerificationError(1, "certificate verify failed")
    assert _tls_verify_failed(urllib.error.URLError(reason)) is True
    with pytest.raises(ValueError, match="non-HTTPS"):
        urllib_then_curl("http://example.test")


def test_baseline_model_rejects_disagreement() -> None:
    """The schema refuses a maximum or a count that the samples do not support."""
    start, end = _window()
    payload = {
        "lat_deg": 31.0,
        "lon_deg": -118.5,
        "radius_km": 800,
        "start": start,
        "end": end,
        "fireball_count_raw": "0",
        "fireball_count": 0,
        "fireball_count_json_type": "string",
        "kp_max": 4.0,
        "kp_values": [4.0],
        "kp_times": ["2004-11-14T00:00:00Z"],
        "cneos_url": "https://ssd-api.jpl.nasa.gov/fireball.api",
        "cneos_sha256": RECORDED_CNEOS_SHA256,
        "cneos_bytes": 82,
        "cneos_via": "urllib",
        "cneos_numbers_from": "live",
        "gfz_url": "https://kp.gfz.de/app/json/",
        "gfz_sha256": RECORDED_GFZ_SHA256,
        "gfz_bytes": 394,
        "gfz_via": "urllib",
        "gfz_numbers_from": "live",
    }
    FusionBaseline.model_validate(payload)
    with pytest.raises(ValidationError, match="kp_max"):
        FusionBaseline.model_validate(payload | {"kp_max": 9.0})
    with pytest.raises(ValidationError, match="fireball_count"):
        FusionBaseline.model_validate(payload | {"fireball_count": 3})
    with pytest.raises(ValidationError, match="recorded body"):
        FusionBaseline.model_validate(
            payload | {"cneos_numbers_from": "live", "cneos_via": "recorded_response"}
        )
    with pytest.raises(ValidationError, match="recorded Kp"):
        FusionBaseline.model_validate(
            payload | {"gfz_numbers_from": "recorded_response", "gfz_via": "urllib"}
        )
