"""Reproduce the first report on the original archive; compare declared key results.

A new diagnosis and selection-audit manifest are always written. Cache reuse is
optional and requires the six original slice hashes. Nothing is submitted.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_control_selection import run as audit
from diagnose_archive import run as diagnose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-cache", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = diagnose(root, reuse_cache=args.reuse_cache)
    result = json.loads((path.parent / "diagnosis.json").read_text())
    expected = json.loads(
        (root / "runs" / "20261018T182502846875Z-detector-diagnosis" / "diagnosis.json").read_text()
    )
    for key in ("original_counts", "control_recoveries"):
        if result[key] != expected[key]:
            raise RuntimeError(
                f"Reproduction differs: {key}; new evidence retained at {path.parent}"
            )
    for i in range(6):
        current = json.loads((path.parent / f"scan-{i}.json").read_text())
        baseline = json.loads(
            (
                root / "runs" / "20261018T182502846875Z-detector-diagnosis" / f"scan-{i}.json"
            ).read_text()
        )
        for field in ("original", "independent"):
            a = max(t["max_snr"] for t in current[field]["trials"])
            b = max(t["max_snr"] for t in baseline[field]["trials"])
            if abs(a - b) > 0.005:
                raise RuntimeError(
                    f"Reproduction maximum differs: scan {i + 1}, {field}; {a} vs {b}"
                )
    audit_path = audit(root, path.parent.name)
    checks = json.loads((audit_path.parent / "selection.json").read_text())
    suppressed = [c["selection"]["suppressed"] for scan in checks for c in scan["controls"]]
    if suppressed != [True, True, False, True, False, False]:
        raise RuntimeError("Selection audit differs; retain new evidence for investigation")
    corrected_path = diagnose(root, reuse_cache=True, corrected=True)
    corrected = json.loads((corrected_path.parent / "diagnosis.json").read_text())
    if corrected["original_counts"] != [186, 150, 0, 0, 0, 0]:
        raise RuntimeError("Corrected counts differ; retain new evidence")
    if corrected["control_recoveries"] != [1, 3, 5, 5, 5, 5]:
        raise RuntimeError("Corrected control recovery differs; retain new evidence")
    for i in range(6):
        scan = json.loads((corrected_path.parent / f"scan-{i}.json").read_text())
        baseline = json.loads(
            (
                root / "runs" / "20261018T183744725763Z-detector-corrected" / f"scan-{i}.json"
            ).read_text()
        )
        for field in ("original", "independent"):
            current_max = max(t["max_snr"] for t in scan[field]["trials"])
            recorded_max = max(t["max_snr"] for t in baseline[field]["trials"])
            if abs(current_max - recorded_max) > 0.005:
                raise RuntimeError(f"Corrected maximum differs: scan {i + 1}, {field}")
        rates = {round(t["drift_hz_s"], 9) for t in scan["original"]["trials"]}
        if len(rates) != 782 or abs(max(rates) - 3.989863995) > 1e-8:
            raise RuntimeError("Corrected drift coverage differs")
        if i >= 2 and max(t["max_snr"] for t in scan["original"]["trials"]) >= 10:
            raise RuntimeError("A formerly empty scan crosses threshold; investigate")
    corrected_audit = audit(root, corrected_path.parent.name)
    for scan in json.loads((corrected_audit.parent / "selection.json").read_text()):
        for control in scan["controls"]:
            if control["selection"]["suppressed"] == control["truth"]["recovered"]:
                raise RuntimeError("Corrected control selection differs")
        if any(t["max_snr"] <= 10 for t in scan["injected_track_trials"]):
            raise RuntimeError("A crowded injected track no longer crosses threshold")
    print(
        "REPRODUCTION PASSED: exact counts and controls; maxima within 0.005 SNR; "
        "selection confirmed."
    )
    print(f"Diagnosis: {path}\nSelection: {audit_path}")
    print(f"Corrected diagnosis: {corrected_path}\nCorrected selection: {corrected_audit}")


if __name__ == "__main__":
    main()
