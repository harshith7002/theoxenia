#!/usr/bin/env python3
"""Pre-commit wrapper for the repository file policy."""

from xenia.file_policy import MAX_FILE_BYTES, main, problems

__all__ = ["MAX_FILE_BYTES", "main", "problems"]

if __name__ == "__main__":
    raise SystemExit(main())
