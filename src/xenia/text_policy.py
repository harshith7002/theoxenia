"""Banned-word scan for public page templates."""

from __future__ import annotations

import re

_BANNED_WORD = re.compile(
    r"\b(alien|extraterrestrial|candidate|anomaly|mysterious)\b",
    re.IGNORECASE,
)


def find_banned_words(text: str) -> tuple[str, ...]:
    """Return each banned word match, in order, with the source casing."""
    return tuple(match.group(0) for match in _BANNED_WORD.finditer(text))
