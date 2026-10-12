#!/usr/bin/env python3
"""Validate committed repository paths against the large/raw-data policy."""

from __future__ import annotations

import subprocess
import sys

from check_staged_files import problems


def main() -> int:
    """Inspect all Git-tracked paths and return a CI-compatible exit code."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    paths = [item.decode("utf-8", errors="surrogateescape") for item in result.stdout.split(b"\0")]
    violations = problems([path for path in paths if path])
    if not violations:
        print("Tracked files comply with the 2 MiB and raw-data policy.")
        return 0
    print("Repository file policy failed:", file=sys.stderr)
    for violation in violations:
        print(f"  - {violation}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
