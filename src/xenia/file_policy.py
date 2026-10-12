"""Repository path and file-size policy shared by tests, pre-commit, and CI."""

from __future__ import annotations

import sys
from pathlib import Path

MAX_FILE_BYTES = 2 * 1024 * 1024
RAW_SUFFIXES = {".h5", ".hdf5", ".fil", ".fits", ".fit", ".raw", ".dat"}


def problems(paths: list[str]) -> list[str]:
    """Return staged-path policy violations without modifying the worktree."""
    violations: list[str] = []
    repository_root = Path.cwd().resolve()
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        if path.is_symlink():
            try:
                path.resolve().relative_to(repository_root)
            except ValueError:
                violations.append(f"{raw_path}: symlink resolves outside the repository")
                continue
        if "data" in path.parts:
            violations.append(f"{raw_path}: data/ files are not committed")
        if path.suffix.lower() in RAW_SUFFIXES:
            violations.append(f"{raw_path}: raw telescope/scan files are not committed")
        if path.is_file() and path.stat().st_size > MAX_FILE_BYTES:
            size_mib = path.stat().st_size / (1024 * 1024)
            violations.append(f"{raw_path}: {size_mib:.2f} MiB exceeds the 2 MiB repository limit")
    return violations


def main(argv: list[str] | None = None) -> int:
    """Print actionable violations and return a hook-compatible exit code."""
    violations = problems(sys.argv[1:] if argv is None else argv)
    if not violations:
        return 0
    print("Staged-file policy failed:", file=sys.stderr)
    for violation in violations:
        print(f"  - {violation}", file=sys.stderr)
    return 1
