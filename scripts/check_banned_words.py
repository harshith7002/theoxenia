"""Fail when a public page template contains a banned word."""

from __future__ import annotations

import sys
from pathlib import Path

from xenia.text_policy import find_banned_words

TEMPLATE_ROOT = Path("site/templates")
SUFFIXES = {".html", ".j2", ".md", ".txt"}


def scan(root: Path) -> int:
    """Scan one template directory and print every match."""
    if not root.is_dir():
        print(f"missing template directory: {root}", file=sys.stderr)
        return 1
    failed = False
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        matches = find_banned_words(path.read_text(encoding="utf-8"))
        if matches:
            failed = True
            print(f"{path}: {', '.join(matches)}")
    return 1 if failed else 0


def main() -> int:
    """Scan site/templates, or the directory passed as the only argument."""
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else TEMPLATE_ROOT
    return scan(root)


if __name__ == "__main__":
    raise SystemExit(main())
