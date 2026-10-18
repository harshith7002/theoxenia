"""Load the known-transmitter ranges used by the prosaic verdict taxonomy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DOWNLINK_HALF_WIDTH_MHZ = 0.05


@dataclass(frozen=True, slots=True)
class KnownRange:
    """One inclusive frequency interval from the known-source catalog."""

    name: str
    freq_min_mhz: float
    freq_max_mhz: float
    source: str
    source_url: str = ""
    checked: str = ""


@dataclass(frozen=True, slots=True)
class Downlink:
    """One deep-space downlink centre. The match window is ±50 kHz."""

    name: str
    freq_mhz: float
    source: str = ""
    source_url: str = ""
    checked: str = ""


@dataclass(frozen=True, slots=True)
class KnownCatalog:
    """Ranges and downlinks that force a KNOWN_SOURCE verdict."""

    ranges: tuple[KnownRange, ...]
    downlinks: tuple[Downlink, ...]

    def match(self, frequency_mhz: float) -> str | None:
        """Return the catalog name that contains this frequency, if any."""
        for item in self.ranges:
            if item.freq_min_mhz <= frequency_mhz <= item.freq_max_mhz:
                return item.name
        for downlink in self.downlinks:
            if abs(frequency_mhz - downlink.freq_mhz) <= DOWNLINK_HALF_WIDTH_MHZ:
                return downlink.name
        return None


def load_known_sources(path: Path) -> KnownCatalog:
    """Read configs/known_sources.yaml. An empty catalog is valid."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - radio extra installation failure
        raise RuntimeError("reading known sources requires PyYAML from the radio extra") from exc

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must be a mapping with ranges and downlinks")
    ranges = _ranges(document.get("ranges", []), path)
    downlinks = _downlinks(document.get("downlinks", []), path)
    return KnownCatalog(ranges=tuple(ranges), downlinks=tuple(downlinks))


def _ranges(raw: object, path: Path) -> list[KnownRange]:
    if not isinstance(raw, list):
        raise ValueError(f"{path} ranges must be a list")
    items: list[KnownRange] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"{path} has a range that is not a mapping")
        name = _text(entry, "name", path)
        source = _text(entry, "source", path)
        source_url = _text(entry, "source_url", path)
        checked = _text(entry, "checked", path)
        low = _frequency(entry, "freq_min_mhz", path)
        high = _frequency(entry, "freq_max_mhz", path)
        if low >= high:
            raise ValueError(f"{path} range {name} must increase in frequency")
        items.append(
            KnownRange(
                name=name,
                freq_min_mhz=low,
                freq_max_mhz=high,
                source=source,
                source_url=source_url,
                checked=checked,
            )
        )
    return items


def _downlinks(raw: object, path: Path) -> list[Downlink]:
    if not isinstance(raw, list):
        raise ValueError(f"{path} downlinks must be a list")
    items: list[Downlink] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"{path} has a downlink that is not a mapping")
        items.append(
            Downlink(
                name=_text(entry, "name", path),
                freq_mhz=_frequency(entry, "freq_mhz", path),
                source=_text(entry, "source", path),
                source_url=_text(entry, "source_url", path),
                checked=_text(entry, "checked", path),
            )
        )
    return items


def _text(entry: dict[str, object], key: str, path: Path) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} is missing text field {key}")
    return value.strip()


def _frequency(entry: dict[str, object], key: str, path: Path) -> float:
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{path} field {key} must be a number")
    frequency = float(value)
    if frequency <= 0:
        raise ValueError(f"{path} field {key} must be positive")
    return frequency
