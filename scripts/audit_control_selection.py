"""Follow up PUB-002 control misses by observing turboSETI's local-maximum filter.

The same injected files and parameters are rerun. No signal strength, location,
matching rule or detector output is changed to make a control pass.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np

from xenia.live.state import sha256_file
from xenia.provenance import create_run_manifest, input_ref, new_run_id, output_ref
from xenia.radio.detector import run_turboseti

PARENT = "20261018T182502846875Z-detector-diagnosis"


def inspect_selection(snr, drifts, channel, offset, distance):
    center = channel + offset
    # Match the diagnosis tolerance, then inspect upstream's exact suppression window.
    candidates = list(range(center - 3, center + 4))
    candidate = max(candidates, key=lambda i: snr[i])
    left, right = max(0, candidate - distance), min(len(snr), candidate + distance)
    stronger = np.flatnonzero(snr[left:right] > snr[candidate])
    peak = left + int(np.argmax(snr[left:right]))
    return {
        "candidate_channel": candidate - offset,
        "candidate_snr": float(snr[candidate]),
        "candidate_drift_hz_s": float(drifts[candidate]),
        "suppression_radius_channels": distance,
        "stronger_neighbors": int(len(stronger)),
        "neighbor_channel": peak - offset,
        "neighbor_snr": float(snr[peak]),
        "neighbor_drift_hz_s": float(drifts[peak]),
        "suppressed": bool(stronger.any()),
    }


def run(root, parent_id=PARENT):
    started = datetime.now(UTC)
    run_id = new_run_id(started, "control-selection")
    out = root / "runs" / run_id
    out.mkdir(parents=True)
    parent = root / "runs" / parent_id
    if not parent.resolve().is_relative_to((root / "runs").resolve()):
        raise ValueError("diagnosis run must be inside runs")
    parent_manifest = json.loads((parent / "manifest.json").read_text())
    for a in parent_manifest["outputs"]:
        if a["sha256"] and sha256_file(root / a["path"]) != a["sha256"]:
            raise ValueError("parent evidence changed")
    module = importlib.import_module("turbo_seti.find_doppler.find_doppler")
    original = module.tophitsearch
    original_hitsearch = module.hitsearch
    results = []
    inputs = [input_ref(parent / "manifest.json", repository_root=root)]
    for scan in (0, 1):
        record_path = parent / f"scan-{scan}.json"
        record = json.loads(record_path.read_text())
        inputs.append(input_ref(record_path, repository_root=root))
        injected = root / "data" / "detector-diagnosis" / parent_id / f"injected-{scan}.h5"
        if sha256_file(injected) != record["injected_sha256"]:
            raise ValueError("injected copy checksum mismatch; reproduce parent diagnosis first")
        captured = []
        track_trials = []

        def observe_track(
            fd,
            spectrum,
            start,
            end,
            threshold,
            drift,
            header,
            width,
            maximum,
            median,
            std,
            *,
            record=record,
            track_trials=track_trials,
        ):
            offset = int((width - record["native_power"]["shape"][1]) / 2)
            for truth in record["injected_truth"]:
                if abs(drift - truth["drift_hz_s"]) < 1e-6:
                    center = truth["start_channel"] + offset
                    scores = (spectrum[center - 3 : center + 4].astype(np.float64) - median) / std
                    track_trials.append(
                        {
                            "start_channel": truth["start_channel"],
                            "drift_hz_s": float(drift),
                            "max_snr": float(scores.max()),
                        }
                    )
            return original_hitsearch(
                fd, spectrum, start, end, threshold, drift, header, width, maximum, median, std
            )

        def observe(
            fd,
            tree,
            maximum,
            tsteps,
            header,
            width,
            length,
            max_drift,
            resolution,
            *,
            record=record,
            captured=captured,
            **kwargs,
        ):
            offset = int((width - length) / 2)
            distance = 2 * math.ceil(max_drift / abs(resolution))
            for truth in record["injected_truth"]:
                found = inspect_selection(
                    maximum.maxsnr, maximum.maxdrift, truth["start_channel"], offset, distance
                )
                captured.append({"truth": truth, "selection": found})
            return original(
                fd, tree, maximum, tsteps, header, width, length, max_drift, resolution, **kwargs
            )

        with (
            patch.object(module, "tophitsearch", observe),
            patch.object(module, "hitsearch", observe_track),
        ):
            result = run_turboseti(
                injected,
                output_directory=root / "data" / "detector-diagnosis" / run_id / f"scan-{scan}",
                max_drift_hz_s=4,
                minimum_snr=10,
                apply_compatibility=False,
            )
        if [h.as_dict() for h in result.hits] != record["injected_search"]["hits"]:
            raise ValueError("passive selection observation changed returned results")
        results.append(
            {
                "scan_index": scan,
                "identical_returned_rows": True,
                "controls": captured,
                "injected_track_trials": track_trials,
                "warnings": result.warnings,
                "injected_sha256": record["injected_sha256"],
            }
        )
    (out / "selection.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
    (out / "processor.txt").write_bytes(Path(__file__).read_bytes())
    _, path = create_run_manifest(
        run_id=run_id,
        command=[
            "uv",
            "run",
            "--locked",
            "--extra",
            "radio",
            "python",
            "scripts/audit_control_selection.py",
            "--diagnosis-run",
            parent_id,
        ],
        parameters={
            "parent_run_id": parent_id,
            "synthetic_controls": True,
            "scans": [0, 1],
            "passive_observation": True,
            "matching_frequency_channels": 3,
        },
        inputs=inputs + [input_ref(Path(__file__), repository_root=root)],
        outputs=[output_ref(p, repository_root=root) for p in sorted(out.iterdir())],
        started_at=started,
        finished_at=datetime.now(UTC),
        outcome="selection_audited",
        notes=[
            "Follow-up motivated by three failed controls in PUB-002. No parameters changed.",
            "These are injected copies of measured backgrounds, not new observations.",
            "Every returned hit is exactly equal to the parent injected-search result.",
            "Exact processor source retained; no external review claimed.",
        ],
        repository_root=root,
        demo=False,
        pillar="I - Sensor",
        experiment_id="PUB-002",
    )
    print(path)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnosis-run", default=PARENT)
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], args.diagnosis_run)
