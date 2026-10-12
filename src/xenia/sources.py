"""Probe the public data-source catalog and record only measured responses.

A transport failure can fall back to a synthetic known-answer fixture. Those
numbers are labeled ``numbers_from=fixture`` and never counted as a live fetch.
"""

from __future__ import annotations

import hashlib
import json
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pydantic import Field, field_validator

from xenia.live.models import StrictModel
from xenia.provenance import create_run_manifest, input_ref, new_run_id, output_ref

CAP_DEFAULT = 65536
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
HEADER_NAMES = (
    "content-type",
    "content-length",
    "content-range",
    "date",
    "server",
    "www-authenticate",
)


class SourceSpec(StrictModel):
    """One catalog row and the single request used to check it."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    name: str = Field(min_length=1)
    notion_url: str
    endpoint: str
    probe_url: str
    access: str = Field(min_length=1)
    pillar: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    formats: str = Field(min_length=1)
    method: Literal["GET", "HEAD"] = "GET"
    range_header: str | None = None
    accept: str | None = None
    allow_plain_http: bool = False
    credential_required: bool = False
    content_type_prefix: str | None = None
    synthetic_fixture: str | None = None

    @field_validator("endpoint", "probe_url", "notion_url")
    @classmethod
    def absolute_http_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError("URL must be absolute HTTP or HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URL must not embed credentials")
        return value


class SourceCatalog(StrictModel):
    """The checked-in mirror of the Data Sources database."""

    cap_bytes: int = Field(default=CAP_DEFAULT, gt=0, le=1_048_576)
    timeout_seconds: float = Field(default=25, gt=0, le=120)
    user_agent: str = Field(default="theoxenia-sources/1", min_length=1)
    sources: tuple[SourceSpec, ...]

    @field_validator("sources")
    @classmethod
    def ids_are_unique(cls, value: tuple[SourceSpec, ...]) -> tuple[SourceSpec, ...]:
        ids = [item.id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("source ids must be unique")
        return value


class SourceProbe(StrictModel):
    """One recorded response. Fixture numbers are not live measurements."""

    id: str
    name: str
    endpoint: str
    probe_url: str
    method: str
    http_status: int | None = None
    bytes_read: int = Field(ge=0)
    content_length: int | None = Field(default=None, ge=0)
    content_type: str | None = None
    content_range: str | None = None
    date_header: str | None = None
    sha256_of_bytes_read: str | None = None
    truncated: bool
    elapsed_s: float | None = Field(default=None, ge=0)
    error: str | None = None
    synthetic: bool
    numbers_from: Literal["live", "fixture"]
    verdict: Literal["verified", "blocked", "synthetic"]
    note: str = Field(min_length=1)

    @field_validator("sha256_of_bytes_read")
    @classmethod
    def checksum_is_sha256(cls, value: str | None) -> str | None:
        if value is not None and len(value) != 64:
            raise ValueError("sha256 must contain 64 hexadecimal characters")
        if value is not None and any(char not in "0123456789abcdef" for char in value):
            raise ValueError("sha256 must be lowercase hexadecimal")
        return value


class SourcesCheck(StrictModel):
    """The file written beside the run manifest."""

    schema_version: Literal["0.1"] = "0.1"
    checked_at: datetime
    catalog_sha256: str
    cap_bytes: int
    results: tuple[SourceProbe, ...]

    @field_validator("checked_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")
        return value


@dataclass(frozen=True, slots=True)
class _LiveRead:
    """Bytes and headers from one attempt. Status is None when nothing came back."""

    http_status: int | None
    final_url: str | None
    body: bytes
    truncated: bool
    headers: dict[str, str]
    elapsed_s: float
    error: str | None


def load_catalog(path: Path) -> SourceCatalog:
    """Read configs/sources.yaml. PyYAML comes from the dev dependency group."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dev group is installed in CI
        raise RuntimeError("reading sources.yaml requires PyYAML") from exc
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must be a mapping")
    return SourceCatalog.model_validate(document)


def classify_live(
    live: _LiveRead,
    *,
    credential_required: bool,
    content_type_prefix: str | None,
) -> Literal["verified", "blocked"]:
    """Decide from a live read. An empty 2xx response is not verification."""
    if live.error is not None or live.http_status is None:
        return "blocked"
    if credential_required:
        return "blocked"
    if not 200 <= live.http_status < 300:
        return "blocked"
    content_length = _content_length(live.headers)
    if live.body == b"" and (content_length is None or content_length <= 0):
        return "blocked"
    if content_type_prefix is not None:
        content_type = live.headers.get("content-type", "")
        if not content_type.startswith(content_type_prefix):
            return "blocked"
    return "verified"


def run_sources_check(
    repository_root: Path,
    command: list[str],
    *,
    config_path: Path,
    out_path: Path,
    started_at: datetime | None = None,
) -> tuple[SourcesCheck, Path]:
    """Probe every catalog row, write sources_check.json, and write a manifest."""
    root = repository_root.resolve()
    started = started_at or datetime.now(UTC)
    catalog = load_catalog(config_path)
    results: list[SourceProbe] = []
    fixture_inputs: list[Path] = []
    for spec in catalog.sources:
        _reject_plain_http(spec)
        live = _fetch(
            spec,
            cap_bytes=catalog.cap_bytes,
            timeout_seconds=catalog.timeout_seconds,
            user_agent=catalog.user_agent,
        )
        verdict = classify_live(
            live,
            credential_required=spec.credential_required,
            content_type_prefix=spec.content_type_prefix,
        )
        if verdict == "blocked" and live.http_status is None and spec.synthetic_fixture:
            fixture_path = _inside(root, Path(spec.synthetic_fixture))
            results.append(_from_fixture(spec, live, fixture_path))
            fixture_inputs.append(fixture_path)
            continue
        results.append(_from_live(spec, live, verdict))

    checked_at = datetime.now(UTC)
    document = SourcesCheck(
        checked_at=checked_at,
        catalog_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(),
        cap_bytes=catalog.cap_bytes,
        results=tuple(results),
    )
    destination = _inside(root, out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    synthetic_ids = [item.id for item in results if item.synthetic]
    blocked_ids = [item.id for item in results if item.verdict == "blocked"]
    verified_count = sum(item.verdict == "verified" for item in results)
    notes = [
        f"verified={verified_count} blocked={len(blocked_ids)} synthetic={len(synthetic_ids)}",
    ]
    if synthetic_ids:
        notes.append(
            "Synthetic fixture numbers are not live measurements: " + ", ".join(synthetic_ids)
        )
    if blocked_ids:
        notes.append("Blocked: " + ", ".join(blocked_ids))
    demo = bool(synthetic_ids)
    outcome = "sources_checked_with_synthetic" if demo else "sources_checked"
    run_id = new_run_id(started, "sources-check")
    inputs = [input_ref(config_path.resolve(), repository_root=root)]
    inputs.extend(input_ref(path, repository_root=root) for path in fixture_inputs)
    _, manifest_path = create_run_manifest(
        run_id=run_id,
        command=command,
        parameters={
            "config": config_path.resolve().relative_to(root).as_posix(),
            "out": destination.relative_to(root).as_posix(),
            "verified_count": verified_count,
            "blocked_count": len(blocked_ids),
            "synthetic_count": len(synthetic_ids),
            "cap_bytes": catalog.cap_bytes,
        },
        inputs=tuple(inputs),
        outputs=(output_ref(destination, repository_root=root),),
        started_at=started,
        finished_at=checked_at,
        outcome=outcome,
        notes=tuple(notes),
        repository_root=root,
        demo=demo,
        pillar="infra",
        experiment_id=None,
        manifest_path=root / "runs" / run_id / "manifest.json",
    )
    return document, manifest_path


def _from_live(
    spec: SourceSpec,
    live: _LiveRead,
    verdict: Literal["verified", "blocked"],
) -> SourceProbe:
    content_length = _content_length(live.headers)
    digest = hashlib.sha256(live.body).hexdigest() if live.http_status is not None else None
    status_text = "none" if live.http_status is None else str(live.http_status)
    note = (
        f"Live {spec.method} {status_text}, bytes_read={len(live.body)}, "
        f"truncated={str(live.truncated).lower()}."
    )
    if live.error:
        note = f"{note} {live.error}"
    if spec.credential_required and live.http_status is not None:
        note = f"{note} Data product needs an account or a paid agreement."
    return SourceProbe(
        id=spec.id,
        name=spec.name,
        endpoint=spec.endpoint,
        probe_url=live.final_url or spec.probe_url,
        method=spec.method,
        http_status=live.http_status,
        bytes_read=len(live.body),
        content_length=content_length,
        content_type=live.headers.get("content-type"),
        content_range=live.headers.get("content-range"),
        date_header=live.headers.get("date"),
        sha256_of_bytes_read=digest,
        truncated=live.truncated,
        elapsed_s=round(live.elapsed_s, 6),
        error=live.error,
        synthetic=False,
        numbers_from="live",
        verdict=verdict,
        note=note,
    )


def _from_fixture(spec: SourceSpec, live: _LiveRead, fixture_path: Path) -> SourceProbe:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "body_text" not in payload or "http_status" not in payload:
        raise ValueError(f"{fixture_path} must contain http_status and body_text")
    body = str(payload["body_text"]).encode("utf-8")
    status = int(payload["http_status"])
    content_type = payload.get("content_type")
    content_type_text = None if content_type is None else str(content_type)
    return SourceProbe(
        id=spec.id,
        name=spec.name,
        endpoint=spec.endpoint,
        probe_url=f"synthetic://{spec.id}",
        method=spec.method,
        http_status=status,
        bytes_read=len(body),
        content_length=len(body),
        content_type=content_type_text,
        content_range=None,
        date_header=None,
        sha256_of_bytes_read=hashlib.sha256(body).hexdigest(),
        truncated=False,
        elapsed_s=round(live.elapsed_s, 6),
        error=live.error,
        synthetic=True,
        numbers_from="fixture",
        verdict="synthetic",
        note=(
            f"Live probe failed ({live.error}). "
            f"http_status, bytes_read, and sha256 are the synthetic fixture "
            f"{fixture_path.name}, not a live measurement. elapsed_s is the failed attempt."
        ),
    )


def _fetch(
    spec: SourceSpec,
    *,
    cap_bytes: int,
    timeout_seconds: float,
    user_agent: str,
) -> _LiveRead:
    headers = {"User-Agent": user_agent, "Accept": spec.accept or "*/*"}
    if spec.range_header:
        headers["Range"] = spec.range_header
    request = Request(spec.probe_url, headers=headers, method=spec.method)
    context = ssl.create_default_context()
    started = datetime.now(UTC)
    try:
        with urlopen(request, timeout=timeout_seconds, context=context) as response:  # noqa: S310
            raw = response.read(cap_bytes + 1)
            if not isinstance(raw, bytes):
                raise ValueError("HTTP body was not bytes")
            body, truncated = raw[:cap_bytes], len(raw) > cap_bytes
            elapsed = (datetime.now(UTC) - started).total_seconds()
            return _LiveRead(
                http_status=int(response.status),
                final_url=response.geturl(),
                body=body,
                truncated=truncated,
                headers=_kept_headers(response.headers),
                elapsed_s=elapsed,
                error=None,
            )
    except HTTPError as exc:
        raw = exc.read(cap_bytes + 1) if exc.fp is not None else b""
        truncated = len(raw) > cap_bytes
        elapsed = (datetime.now(UTC) - started).total_seconds()
        return _LiveRead(
            http_status=int(exc.code),
            final_url=exc.geturl() if hasattr(exc, "geturl") else spec.probe_url,
            body=raw[:cap_bytes],
            truncated=truncated,
            headers=_kept_headers(exc.headers),
            elapsed_s=elapsed,
            error=f"HTTPError {exc.code}",
        )
    except (URLError, TimeoutError, OSError) as exc:
        elapsed = (datetime.now(UTC) - started).total_seconds()
        return _LiveRead(
            http_status=None,
            final_url=None,
            body=b"",
            truncated=False,
            headers={},
            elapsed_s=elapsed,
            error=f"{type(exc).__name__}: {exc}",
        )


def _kept_headers(headers: object) -> dict[str, str]:
    items = getattr(headers, "items", None)
    if not callable(items):
        return {}
    found = {str(key).lower(): str(value) for key, value in items()}
    return {name: found[name] for name in HEADER_NAMES if name in found}


def _content_length(headers: dict[str, str]) -> int | None:
    raw = headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _reject_plain_http(spec: SourceSpec) -> None:
    for url in (spec.endpoint, spec.probe_url):
        parsed = urlsplit(url)
        if parsed.scheme != "http":
            continue
        if parsed.hostname in LOOPBACK or spec.allow_plain_http:
            continue
        raise ValueError(f"{spec.id} uses plain HTTP without allow_plain_http")


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path must stay inside repository: {path}") from exc
    return resolved
