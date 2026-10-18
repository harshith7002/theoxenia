"""Select comparable evidence and validate complete, manifest-backed hit counts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from xenia.live.models import CadencePayload, RunManifest, Verdict


def is_synthetic(manifest: RunManifest) -> bool:
    return (
        manifest.demo
        or manifest.parameters.get("synthetic") is True
        or any(str(item.uri).startswith("synthetic://") for item in manifest.inputs)
    )


def selected_cadences(
    manifests: Sequence[RunManifest],
) -> list[tuple[RunManifest, CadencePayload]]:
    """Keep the latest attempt per window; never mix observations and controls.

    A synthetic-only collection remains useful as an explicitly labelled demo.
    Once observational evidence exists, fixtures and synthetic cadences are omitted.
    """
    observed = any(
        not is_synthetic(item)
        and item.mission_control is not None
        and item.mission_control.kind in {"hero", "cadence"}
        for item in manifests
    )
    latest: dict[tuple[str, tuple[float, float]], tuple[RunManifest, CadencePayload]] = {}
    for item in sorted(manifests, key=lambda m: (m.finished_at, m.run_id)):
        payload = item.mission_control
        if not isinstance(payload, CadencePayload) or (observed and is_synthetic(item)):
            continue
        latest[(payload.cadence_id, payload.window_mhz)] = (item, payload)
    return list(latest.values())


def verdict_counts(manifest: RunManifest, payload: CadencePayload) -> Counter[Verdict]:
    """Read complete counts when recorded; gallery previews are only a subset."""
    previews = Counter(hit.verdict for hit in payload.hits)
    raw = manifest.parameters.get("verdict_counts")
    if raw is None:
        return previews
    if not isinstance(raw, dict) or set(raw) != {v.value for v in Verdict}:
        raise ValueError(f"{manifest.run_id}: invalid verdict_counts keys")
    if any(type(value) is not int or value < 0 for value in raw.values()):
        raise ValueError(f"{manifest.run_id}: verdict_counts must be nonnegative integers")
    counts = Counter({Verdict(key): value for key, value in raw.items()})
    hit_count = manifest.parameters.get("hit_count")
    if type(hit_count) is not int or sum(counts.values()) != hit_count:
        raise ValueError(f"{manifest.run_id}: verdict_counts do not match hit_count")
    if any(counts[v] < previews[v] for v in Verdict):
        raise ValueError(f"{manifest.run_id}: verdict_counts omit preview hits")
    if counts[Verdict.UNEXPLAINED] != previews[Verdict.UNEXPLAINED]:
        raise ValueError(f"{manifest.run_id}: reviewed hits must have full records")
    return counts
