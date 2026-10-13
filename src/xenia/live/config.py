"""Load configs/live.yaml. The shape is spec section 8.5 plus two local fields."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RECEIVER_KEYS = {"L": "L-band", "C": "C-band", "L-band": "L-band", "C-band": "C-band"}


@dataclass(frozen=True, slots=True)
class MeasuredBand:
    """A file band read from real headers, not inferred from a centre frequency."""

    cadence_id: str
    low_mhz: float
    high_mhz: float
    checked: str


@dataclass(frozen=True, slots=True)
class LiveConfig:
    """Worker settings. ``transfer_cap_bytes`` is the per-file ceiling."""

    campaign: str
    queue_file: str
    window_mhz: float
    windows: dict[str, tuple[float, ...]]
    max_drift_hz_s: float
    minimum_snr: float
    filter_threshold: int
    thumb_px: tuple[int, int]
    full_px: tuple[int, int]
    colormap: str
    commit_branch: str
    commit_every_minutes: int
    commit_on_survivor: bool
    heartbeat_seconds: int
    idle_sleep_minutes: int
    max_retries: int
    transfer_cap_bytes: int
    allow_plain_http: bool
    measured_file_bands: tuple[MeasuredBand, ...]

    def window_starts(self, receiver: str) -> tuple[float, ...]:
        """Return the configured window starts for L or C."""
        key = RECEIVER_KEYS.get(receiver)
        if key is None:
            raise ValueError("receiver must be L or C")
        starts = self.windows.get(key)
        if not starts:
            raise ValueError(f"{key} has no window starts")
        return starts


def load_live_config(path: Path) -> LiveConfig:
    """Read the worker config. Unknown top-level keys are rejected."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - radio extra installation failure
        raise RuntimeError("reading live.yaml requires PyYAML from the radio extra") from exc

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must be a mapping")
    allowed = {
        "campaign",
        "queue_file",
        "window_mhz",
        "windows",
        "turboseti",
        "plots",
        "commit",
        "heartbeat_seconds",
        "idle_sleep_minutes",
        "max_retries",
        "transfer_cap_bytes",
        "allow_plain_http",
        "measured_file_bands",
    }
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise ValueError(f"{path} has unknown keys: {', '.join(unknown)}")
    windows = _windows(document.get("windows"), path)
    turboseti = _mapping(document.get("turboseti"), "turboseti", path)
    plots = _mapping(document.get("plots"), "plots", path)
    commit = _mapping(document.get("commit"), "commit", path)
    return LiveConfig(
        campaign=_text(document, "campaign", path),
        queue_file=_text(document, "queue_file", path),
        window_mhz=_positive(document, "window_mhz", path),
        windows=windows,
        max_drift_hz_s=_positive(turboseti, "max_drift", path),
        minimum_snr=_non_negative(turboseti, "snr", path),
        filter_threshold=int(_positive(turboseti, "filter_threshold", path)),
        thumb_px=_pair(plots, "thumb_px", path),
        full_px=_pair(plots, "full_px", path),
        colormap=_text(plots, "colormap", path),
        commit_branch=_text(commit, "branch", path),
        commit_every_minutes=int(_positive(commit, "every_minutes", path)),
        commit_on_survivor=_bool(commit, "on_survivor", path),
        heartbeat_seconds=int(_positive(document, "heartbeat_seconds", path)),
        idle_sleep_minutes=int(_positive(document, "idle_sleep_minutes", path)),
        max_retries=int(_non_negative(document, "max_retries", path)),
        transfer_cap_bytes=int(_positive(document, "transfer_cap_bytes", path)),
        allow_plain_http=_bool(document, "allow_plain_http", path),
        measured_file_bands=tuple(_bands(document.get("measured_file_bands", []), path)),
    )


def _windows(raw: object, path: Path) -> dict[str, tuple[float, ...]]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"{path} windows must be a non-empty mapping")
    parsed: dict[str, tuple[float, ...]] = {}
    for name, starts in raw.items():
        if not isinstance(name, str) or not isinstance(starts, list) or not starts:
            raise ValueError(f"{path} window {name} must be a non-empty list")
        values = tuple(float(item) for item in starts)
        if any(item <= 0 for item in values):
            raise ValueError(f"{path} window {name} must be positive")
        parsed[name] = values
    return parsed


def _bands(raw: object, path: Path) -> list[MeasuredBand]:
    if not isinstance(raw, list):
        raise ValueError(f"{path} measured_file_bands must be a list")
    bands: list[MeasuredBand] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"{path} has a measured band that is not a mapping")
        low = _positive(entry, "low_mhz", path)
        high = _positive(entry, "high_mhz", path)
        if low >= high:
            raise ValueError(f"{path} measured band must increase in frequency")
        bands.append(
            MeasuredBand(
                cadence_id=_text(entry, "cadence_id", path),
                low_mhz=low,
                high_mhz=high,
                checked=_text(entry, "checked", path),
            )
        )
    return bands


def _mapping(raw: object, name: str, path: Path) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError(f"{path} {name} must be a mapping")
    return raw


def _text(entry: dict[str, object], key: str, path: Path) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} is missing text field {key}")
    return value.strip()


def _number(entry: dict[str, object], key: str, path: Path) -> float:
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{path} field {key} must be a number")
    return float(value)


def _positive(entry: dict[str, object], key: str, path: Path) -> float:
    value = _number(entry, key, path)
    if value <= 0:
        raise ValueError(f"{path} field {key} must be positive")
    return value


def _non_negative(entry: dict[str, object], key: str, path: Path) -> float:
    value = _number(entry, key, path)
    if value < 0:
        raise ValueError(f"{path} field {key} must be non-negative")
    return value


def _bool(entry: dict[str, object], key: str, path: Path) -> bool:
    value = entry.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{path} field {key} must be a boolean")
    return value


def _pair(entry: dict[str, object], key: str, path: Path) -> tuple[int, int]:
    value = entry.get(key)
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{path} field {key} must be a pair")
    width, height = value
    if isinstance(width, bool) or isinstance(height, bool):
        raise ValueError(f"{path} field {key} must be a pair of integers")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ValueError(f"{path} field {key} must be a pair of positive integers")
    return width, height
