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
    print(
        "REPRODUCTION PASSED: exact counts and controls; maxima within 0.005 SNR; "
        "selection confirmed."
    )
    print(f"Diagnosis: {path}\nSelection: {audit_path}")


if __name__ == "__main__":
    main()
