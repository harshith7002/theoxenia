"""Compare two Mission Control pages after removing clock-only text.

Heartbeat label, ticker sentence, and the "State built" clock are rewritten to
a fixed token. Search results, verdicts, and manifest links are not.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_STATUS_LABEL = re.compile(r'(<div class="status-pill[^"]*" aria-label=")Worker status: [^"]*(")')
_STATUS_TEXT = re.compile(
    r'(<div class="status-pill\b.*?<span class="status-dot[^"]*" aria-hidden="true"></span>\s*'
    r"<span>)(.*?)(</span>)",
    re.DOTALL,
)
_TICKER = re.compile(
    r'(<section class="ticker-panel" aria-label="Search ticker">\s*<p>)(.*?)(</p>)',
    re.DOTALL,
)
_BUILT = re.compile(r"State built [^<]*")


def normalize_index(html: str) -> str:
    """Replace heartbeat, ticker, and build-clock text with fixed tokens."""
    text = _STATUS_LABEL.sub(r"\1Worker status: NORMALISED\2", html, count=1)
    text = _STATUS_TEXT.sub(r"\1NORMALISED\3", text, count=1)
    text = _TICKER.sub(r"\1NORMALISED\3", text, count=1)
    return _BUILT.sub("State built NORMALISED", text)


def pages_match(left: str, right: str) -> bool:
    """Return whether two rendered pages agree once clock text is removed."""
    return normalize_index(left) == normalize_index(right)


def main(argv: list[str] | None = None) -> int:
    """Exit 0 when the two index files match after normalisation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    args = parser.parse_args(argv)
    left = args.left.read_text(encoding="utf-8")
    right = args.right.read_text(encoding="utf-8")
    if pages_match(left, right):
        print("recovery-check: match")
        return 0
    print("recovery-check: differ", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
