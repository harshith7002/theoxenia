"""Negative tests for the banned-word scanner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from xenia.text_policy import find_banned_words

ROOT = Path(__file__).resolve().parents[1]
CLEAN = "Latest hits, and the checks applied."
BANNED = ("alien", "extraterrestrial", "candidate", "anomaly", "mysterious")


@pytest.mark.parametrize("word", BANNED)
def test_inserting_one_banned_word_is_found(word: str) -> None:
    """Each banned word is found on its own, including a changed case."""
    assert find_banned_words(CLEAN) == ()
    assert find_banned_words(f"{CLEAN} {word} end") == (word,)
    assert find_banned_words(f"{CLEAN} {word.upper()} end") == (word.upper(),)


@pytest.mark.parametrize(
    "text",
    (
        "alienate",
        "mysteriously",
        "candidates",
        "anomalies",
        "The canonical channel.",
    ),
)
def test_a_banned_word_inside_a_longer_word_is_not_a_match(text: str) -> None:
    """The scan uses word boundaries, so a longer word is not a hit."""
    assert find_banned_words(text) == ()


@pytest.mark.parametrize("word", BANNED)
def test_deleting_one_character_removes_the_match(word: str) -> None:
    """A one-character deletion of a banned word is not itself a banned word."""
    for index in range(len(word)):
        mutant = word[:index] + word[index + 1 :]
        assert find_banned_words(mutant) == ()
        assert find_banned_words(f"start {mutant} end") == ()


@pytest.mark.parametrize("word", BANNED)
def test_punctuation_does_not_hide_a_banned_word(word: str) -> None:
    """Parentheses and a trailing period still leave a whole-word match."""
    assert find_banned_words(f"({word}).") == (word,)


def test_checked_in_templates_have_no_banned_words() -> None:
    """The templates that ship in this branch stay inside the policy."""
    root = ROOT / "site" / "templates"
    assert root.is_dir()
    for path in root.rglob("*"):
        if path.is_file():
            assert find_banned_words(path.read_text(encoding="utf-8")) == ()


def test_template_scan_rejects_one_inserted_word(tmp_path: Path) -> None:
    """The pre-commit script fails when a template file gains one banned word."""
    template = tmp_path / "page.html.j2"
    template.write_text(f"{CLEAN}\n", encoding="utf-8")
    assert _scan(tmp_path) == 0
    template.write_text(f"{CLEAN} mysterious\n", encoding="utf-8")
    assert _scan(tmp_path) == 1


def test_template_scan_accepts_the_checked_in_tree() -> None:
    """The hook command exits 0 on the templates committed in this branch."""
    assert _scan(ROOT / "site" / "templates") == 0


def _scan(root: Path) -> int:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_banned_words.py"), str(root)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode
