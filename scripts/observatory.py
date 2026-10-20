"""Run one bounded archive-processing cycle; publication is explicit."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from xenia.live.observatory import publish_cycle, read_status, run_cycle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pairs", type=int, default=1)
    parser.add_argument("--hosted", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--publish-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.publish_only:
        status = read_status(root)
        if status is None:
            raise ValueError("no completed cycle to publish")
        publish_cycle(root, status)
        return
    dirty = subprocess.run(
        ["git", "diff", "HEAD", "--name-only"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    if dirty:
        raise ValueError("commit source changes before processing; preserve exact provenance")
    status = run_cycle(
        root, max_pairs=args.max_pairs, mode="hosted" if args.hosted else "scheduled"
    )
    print(status.model_dump_json(indent=2))
    if args.publish:
        publish_cycle(root, status)


if __name__ == "__main__":
    main()
