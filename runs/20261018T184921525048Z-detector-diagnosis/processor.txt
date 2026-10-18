"""PUB-002: reproduce empty archive tables and test detector health.

All original files are read-only. Diagnostic controls are synthetic additions
on separate copies, never telescope detections. No result is called a discovery.
"""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import shutil
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

import h5py
import numpy as np

from xenia.live.models import RunManifest
from xenia.live.slicer import CadenceFile, slice_cadence
from xenia.live.state import sha256_file
from xenia.provenance import create_run_manifest, input_ref, new_run_id, output_ref
from xenia.radio.detector import run_turboseti

SOURCE = "20261012T203545022355Z-exp-003-cadence"


def stats(power):
    """Independent float64 implementation of the declared normalization."""
    integrated = power.astype(np.float64).sum(axis=0)
    low, median, high = np.percentile(integrated, [5, 50, 95])
    clipped = integrated[(integrated >= low) & (integrated <= high)]
    std = clipped.std(ddof=0)
    if not np.isfinite(std) or std <= 0:
        raise ValueError("invalid detector normalization")
    return float(median), float(std)


def direct_grid(power, foff_hz, tsamp):
    """Independent straight-line, nearest-channel integration, with no tree code.

    Start and end sample centers are (N-1)*tsamp apart. Exclude tracks that
    leave the window. This reference does not promise identical Taylor paths.
    """
    data = power.astype(np.float64).copy()
    middle = data.shape[1] // 2
    median, std = stats(data)
    data[:, middle] = (data[:, middle - 1] + data[:, middle + 1]) / 2
    ntime, nfreq = data.shape
    limit = int(np.floor(4 * (ntime - 1) * tsamp / abs(foff_hz)))
    results = []
    for endpoint in range(-limit, limit + 1):
        offsets = np.rint(np.arange(ntime) * endpoint / (ntime - 1)).astype(int)
        left, right = max(0, -int(offsets.min())), min(nfreq, nfreq - int(offsets.max()))
        summed = np.zeros(right - left, dtype=np.float64)
        for time, offset in enumerate(offsets):
            summed += data[time, left + offset : right + offset]
        scores = (summed - median) / std
        index = int(np.argmax(scores))
        results.append(
            {
                "endpoint_channels": endpoint,
                "drift_hz_s": endpoint * foff_hz / ((ntime - 1) * tsamp),
                "max_snr": float(scores[index]),
                "channel": left + index,
                "above_10": int(np.count_nonzero(scores > 10)),
            }
        )
    return {
        "method": "float64 nearest-channel straight lines; includes zero drift",
        "median": median,
        "trimmed_std": std,
        "trials": results,
    }


def probe(path, destination, *, corrected=False):
    """Observe upstream normalization and trial maxima without changing arrays."""
    upstream = importlib.import_module("turbo_seti.find_doppler.find_doppler")
    original = upstream.hitsearch
    trials = []

    def observe(fd, spectrum, start, end, threshold, drift, header, width, maximum, median, std):
        # Read BEFORE upstream's in-place normalization.
        values = spectrum[start:end].astype(np.float64)
        scores = (values - float(median)) / float(std)
        trials.append(
            {
                "drift_hz_s": float(drift),
                "median": float(median),
                "trimmed_std": float(std),
                "max_snr": float(scores.max()),
                "above_threshold": int(np.count_nonzero(scores > threshold)),
                "finite_fraction": float(np.isfinite(scores).mean()),
            }
        )
        return original(
            fd, spectrum, start, end, threshold, drift, header, width, maximum, median, std
        )

    with patch.object(upstream, "hitsearch", observe):
        result = run_turboseti(
            path,
            output_directory=destination,
            max_drift_hz_s=4.0,
            minimum_snr=10.0,
            apply_compatibility=corrected,
        )
    return {
        "hits": [h.as_dict() for h in result.hits],
        "trials": trials,
        "warnings": result.warnings,
        "artifacts": [
            {"filename": a.filename, "sha256": a.sha256, "size_bytes": a.size_bytes}
            for a in result.artifacts
        ],
    }


def injected_copy(source, target, power, attrs, *, corrected=False):
    """Three deterministic single-channel tracks, 40 normalized sum units each."""
    shutil.copyfile(source, target)
    ntime, nfreq = power.shape
    _, sigma = stats(power)
    increment = 40.0 * sigma / ntime
    truth = []
    with h5py.File(target, "r+") as f:
        d = f["data"]
        tracks = [(0.23, -1), (0.48, 1), (0.73, 10)]
        if corrected:
            tracks.extend([(0.35, 26), (0.60, -26)])
        for fraction, speed in tracks:
            start = int(nfreq * fraction)
            for t in range(ntime):
                channel = start + speed * t
                d[t, 0, channel] = float(d[t, 0, channel]) + increment
            truth.append(
                {
                    "start_channel": start,
                    "channels_per_integration": speed,
                    "frequency_mhz": float(attrs["fch1"]) + start * float(attrs["foff"]),
                    "drift_hz_s": speed * float(attrs["foff"]) * 1e6 / float(attrs["tsamp"]),
                    "added_power_per_sample": increment,
                    "nominal_added_sum_snr": 40.0,
                }
            )
    return truth


def run(root, *, reuse_cache=False, corrected=False):
    started = datetime.now(UTC)
    run_id = new_run_id(started, "detector-corrected" if corrected else "detector-diagnosis")
    out = root / "runs" / run_id
    out.mkdir(parents=True)
    source = root / "runs" / SOURCE / "manifest.json"
    manifest = RunManifest.model_validate_json(source.read_text())
    summary_path = source.parent / "slice_summary.json"
    summary = json.loads(summary_path.read_text())
    for artifact in manifest.outputs:
        if artifact.sha256 and sha256_file(root / artifact.path) != artifact.sha256:
            raise ValueError("original evidence checksum failed")
    cache = root / "data" / "detector-diagnosis" / "slices"
    files = tuple(
        CadenceFile(
            url=x["url"],
            role=x["role"],
            expected_source_name=x["expected_source_name"],
            catalog_md5=x["catalog_md5"],
            catalog_size_bytes=x["catalog_size_bytes"],
        )
        for x in summary["files"]
    )
    transfer = []
    if not reuse_cache:
        slices = slice_cadence(
            files, output_dir=cache, frequency_low_mhz=1380, frequency_high_mhz=1381
        )
        transfer = [s.transfer.as_dict() for s in slices]
    paths = [cache / f"scan-{i}-{f.role}.h5" for i, f in enumerate(files)]
    for p, ref in zip(paths, manifest.inputs, strict=True):
        if sha256_file(p) != ref.sha256:
            raise ValueError(f"input does not exactly reproduce original slice: {p.name}")
    processor = out / "processor.txt"
    processor.write_bytes(Path(__file__).read_bytes())
    work = root / "data" / "detector-diagnosis" / run_id
    work.mkdir(parents=True)
    records = []
    for i, path in enumerate(paths):
        print(f"SCAN {i + 1}: original, independent grid, injected controls", flush=True)
        with h5py.File(path, "r") as f:
            power = f["data"][:, 0, :]
            attrs = dict(f["data"].attrs)
        if not np.isfinite(power).all() or not (power > 0).all():
            raise ValueError("invalid input power")
        native = {
            "shape": list(power.shape),
            "min": float(power.min()),
            "max": float(power.max()),
            "integration_median": np.median(power, axis=1).tolist(),
            "integration_mean": power.mean(axis=1, dtype=np.float64).tolist(),
        }
        observed = probe(path, work / f"original-{i}", corrected=corrected)
        reference = direct_grid(power, float(attrs["foff"]) * 1e6, float(attrs["tsamp"]))
        injected = work / f"injected-{i}.h5"
        truth = injected_copy(path, injected, power, attrs, corrected=corrected)
        controls = probe(injected, work / f"controls-{i}", corrected=corrected)
        legacy_controls = probe(injected, work / f"legacy-controls-{i}") if corrected else None
        for t in truth:
            matches = [
                h
                for h in controls["hits"]
                if abs(h["uncorrected_frequency_mhz"] - t["frequency_mhz"]) * 1e6
                <= 3 * abs(float(attrs["foff"])) * 1e6
                and abs(h["drift_hz_s"] - t["drift_hz_s"]) <= 0.03
            ]
            t["recovered"] = bool(matches)
            t["matches"] = matches
        record = {
            "scan_index": i,
            "role": files[i].role,
            "source": files[i].expected_source_name,
            "slice_sha256": sha256_file(path),
            "native_power": native,
            "original": observed,
            "independent": reference,
            "injected_truth": truth,
            "injected_search": controls,
            "legacy_injected_search": legacy_controls,
            "injected_sha256": sha256_file(injected),
        }
        records.append(record)
        (out / f"scan-{i}.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
        print(
            f"SCAN {i + 1}: {len(observed['hits'])} hits; max upstream "
            f"{max((t['max_snr'] for t in observed['trials']), default=0):.4f}; "
            f"reference {max(t['max_snr'] for t in reference['trials']):.4f}; "
            f"controls {sum(t['recovered'] for t in truth)}/{len(truth)}",
            flush=True,
        )
    upstream_file = Path(importlib.import_module("turbo_seti.find_doppler.find_doppler").__file__)
    result = {
        "schema_version": 1,
        "source_run_id": SOURCE,
        "scans": len(records),
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {p: version(p) for p in ("numpy", "turbo-seti", "blimpy", "h5py", "numba")},
        "upstream_find_doppler_sha256": sha256_file(upstream_file),
        "transfer": transfer,
        "cache_reused": reuse_cache,
        "compatibility_corrected": corrected,
        "original_counts": [len(r["original"]["hits"]) for r in records],
        "control_recoveries": [sum(t["recovered"] for t in r["injected_truth"]) for r in records],
    }
    (out / "diagnosis.json").write_text(json.dumps(result, indent=2) + "\n")
    outputs = [output_ref(p, repository_root=root) for p in sorted(out.iterdir())]
    _, destination = create_run_manifest(
        run_id=run_id,
        command=[
            "uv",
            "run",
            "--locked",
            "--extra",
            "radio",
            "python",
            "scripts/diagnose_archive.py",
        ]
        + (["--reuse-cache"] if reuse_cache else [])
        + (["--corrected"] if corrected else []),
        parameters={
            "source_run_id": SOURCE,
            "minimum_snr": 10,
            "max_drift_hz_s": 4,
            "min_drift_hz_s": 1e-5,
            "precision": "float32",
            "coarse_channels": 1,
            "controls_per_scan": 5 if corrected else 3,
            "compatibility_corrected": corrected,
            "control_nominal_sum_snr": 40,
            "frequency_tolerance_channels": 3,
            "drift_tolerance_hz_s": 0.03,
        },
        inputs=[
            input_ref(source, repository_root=root),
            input_ref(summary_path, repository_root=root),
            input_ref(Path(__file__), repository_root=root),
            input_ref(root / "uv.lock", repository_root=root),
            *manifest.inputs,
        ],
        outputs=outputs,
        started_at=started,
        finished_at=datetime.now(UTC),
        outcome="diagnosed",
        notes=[
            "Original slices exactly match all six historical SHA-256 values; originals unchanged.",
            "Synthetic injections use separate copies. They are health checks, not observations.",
            "Independent nearest-channel integration differs from Taylor-tree paths; "
            "not an exact algorithm reproduction.",
            "This is a rerun of one archived 1 MHz cadence, not additional observing exposure.",
            "Exact processor source retained. No external scientific review "
            "or survey completeness claim.",
        ],
        repository_root=root,
        demo=False,
        pillar="I - Sensor",
        experiment_id="PUB-002",
    )
    print(destination, flush=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reuse-cache", action="store_true", help="Use checksum-verified local slices"
    )
    parser.add_argument(
        "--corrected", action="store_true", help="Test audited compatibility fix and edge controls"
    )
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], reuse_cache=args.reuse_cache, corrected=args.corrected)
