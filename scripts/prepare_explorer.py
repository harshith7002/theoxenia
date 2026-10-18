"""Export a complete measured hit table and optional bounded archive waterfall previews.

This creates a new provenance record. It never rewrites a source experiment or
reruns its detector. Raw slices stay in ignored data/ and are deleted on success.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from xenia.live.evidence import is_synthetic
from xenia.live.models import CadencePayload, RunManifest
from xenia.live.slicer import CadenceFile, slice_cadence
from xenia.live.state import sha256_file
from xenia.provenance import create_run_manifest, input_ref, new_run_id, output_ref


def prepare(root: Path, source_run: str, *, waterfalls: bool) -> Path:
    import polars as pl

    source = root / "runs" / source_run / "manifest.json"
    if not source.resolve().is_relative_to((root / "runs").resolve()):
        raise ValueError("source must be within runs")
    manifest = RunManifest.model_validate_json(source.read_text())
    payload = manifest.mission_control
    if not isinstance(payload, CadencePayload) or is_synthetic(manifest):
        raise ValueError("a measured archive cadence is required")
    artifact = next(a for a in manifest.outputs if a.path.endswith("/hits.parquet"))
    table = root / artifact.path
    if sha256_file(table) != artifact.sha256:
        raise ValueError("source hit table checksum mismatch")
    rows = pl.read_parquet(table).to_dicts()
    counts = Counter(str(row["verdict"]) for row in rows)
    recorded = manifest.parameters["verdict_counts"]
    if not isinstance(recorded, dict) or any(counts[k] != v for k, v in recorded.items()):
        raise ValueError("source counts disagree with the complete table")
    started = datetime.now(UTC)
    run_id = new_run_id(started, "public-evidence")
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True)
    processor = run_dir / "processor.txt"
    processor.write_bytes(Path(__file__).read_bytes())
    inputs = [input_ref(source, repository_root=root), input_ref(table, repository_root=root)]
    inputs.append(input_ref(Path(__file__), repository_root=root))
    scans: list[dict[str, object]] = []
    if waterfalls:
        import h5py
        import numpy as np

        summary_path = source.parent / "slice_summary.json"
        summary = json.loads(summary_path.read_text())
        expected = next(a for a in manifest.outputs if a.path.endswith("/slice_summary.json"))
        if sha256_file(summary_path) != expected.sha256:
            raise ValueError("source slice summary checksum mismatch")
        inputs.append(input_ref(summary_path, repository_root=root))
        files = tuple(
            CadenceFile(
                url=ref.uri,
                role=role,
                expected_source_name=info["expected_source_name"],
                catalog_md5=info["catalog_md5"],
                catalog_size_bytes=info["catalog_size_bytes"],
            )
            for ref, role, info in zip(
                manifest.inputs, ("A", "B", "A", "C", "A", "D"), summary["files"], strict=True
            )
        )
        scratch = root / "data" / "public-evidence" / run_id
        try:
            slices = slice_cadence(
                files,
                output_dir=scratch,
                frequency_low_mhz=payload.window_mhz[0],
                frequency_high_mhz=payload.window_mhz[1],
            )
            for item, original in zip(slices, manifest.inputs, strict=True):
                print(
                    f"Processing measured scan {item.scan_index + 1}: {item.expected_source_name}",
                    flush=True,
                )
                # HDF5 container metadata can change; exact byte equality is reported,
                # never assumed. The newly fetched slice has its own checksum.
                from xenia.live.models import InputRef

                inputs.append(
                    InputRef(
                        uri=item.url,
                        sha256=item.info.output_sha256,
                        size_bytes=item.info.output_size_bytes,
                    )
                )
                with h5py.File(item.path, "r") as h5:
                    power = np.asarray(h5["data"][:, 0, :], dtype=float)
                valid = np.isfinite(power) & (power > 0)
                if not valid.all():
                    raise ValueError("waterfall input has nonfinite or nonpositive power")
                if item.info.header.foff_mhz < 0:
                    power = power[:, ::-1]
                boundaries = np.linspace(0, power.shape[1], 1025, dtype=int)
                reduced = np.stack(
                    [
                        power[:, left:right].mean(axis=1)
                        for left, right in zip(boundaries[:-1], boundaries[1:], strict=True)
                    ],
                    axis=1,
                )
                relative_db = 10 * np.log10(reduced / np.median(power, axis=1)[:, None])
                half_channel = abs(item.info.header.foff_mhz) / 2
                scans.append(
                    {
                        "index": item.scan_index,
                        "role": item.role,
                        "source": item.expected_source_name,
                        "tstart_mjd": item.info.header.tstart_mjd,
                        "tsamp_seconds": item.info.header.tsamp_seconds,
                        "integrations": power.shape[0],
                        "channels": power.shape[1],
                        "frequency_low_mhz": min(
                            item.info.first_center_mhz, item.info.last_center_mhz
                        )
                        - half_channel,
                        "frequency_high_mhz": max(
                            item.info.first_center_mhz, item.info.last_center_mhz
                        )
                        + half_channel,
                        "relative_db": np.round(relative_db, 2).tolist(),
                        "slice_sha256": item.info.output_sha256,
                        "matches_original_slice_bytes": item.info.output_sha256 == original.sha256,
                        "bytes_transferred": item.transfer.bytes_transferred,
                        "finite_positive_fraction": float(valid.mean()),
                        "power_min": float(power.min()),
                        "power_max": float(power.max()),
                    }
                )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    document = {
        "schema_version": 1,
        "source_run_id": manifest.run_id,
        "source_table_sha256": artifact.sha256,
        "preparation_run_id": run_id,
        "target": payload.target,
        "window_mhz": payload.window_mhz,
        "rows": rows,
        "scans": scans,
        "waterfall_method": (
            "Mean power in 1024 frequency bins; dB relative to each integration's "
            "median native-channel power. Display only; detector used native "
            "resolution. No detector rerun."
        ),
    }
    target = run_dir / "explorer.json"
    target.write_text(json.dumps(document, separators=(",", ":"), allow_nan=False) + "\n")
    if target.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("public preview exceeds the 2 MiB artifact limit")
    command = [
        "uv",
        "run",
        "--locked",
        "--extra",
        "radio",
        "python",
        "scripts/prepare_explorer.py",
        "--source-run",
        source_run,
    ]
    if waterfalls:
        command.append("--waterfalls")
    _, path = create_run_manifest(
        run_id=run_id,
        command=command,
        parameters={
            "source_run_id": source_run,
            "row_count": len(rows),
            "waterfall_scans": len(scans),
            "detector_rerun": False,
        },
        inputs=inputs,
        outputs=[
            output_ref(target, repository_root=root),
            output_ref(processor, repository_root=root),
        ],
        started_at=started,
        finished_at=datetime.now(UTC),
        outcome="evidence_prepared",
        notes=[
            "Exact processor source: processor.txt. git_sha records the base revision.",
            "Derived presentation of recorded observations, not additional search exposure.",
            "Remote-input SHA-256 values identify local frequency slices, not full archive files.",
            (
                "Zero detector rows in later ON scans remain an open investigation; valid "
                "power alone does not resolve the detector result."
            ),
        ],
        repository_root=root,
        demo=False,
        pillar="Public evidence",
        experiment_id="PUB-001",
    )
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True)
    parser.add_argument(
        "--waterfalls", action="store_true", help="Fetch six bounded archive slices"
    )
    args = parser.parse_args()
    print(prepare(Path(__file__).resolve().parents[1], args.source_run, waterfalls=args.waterfalls))
