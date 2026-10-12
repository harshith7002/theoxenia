"""Shared, deterministic fixtures for Mission Control M0 tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from xenia.live.models import LiveState, RunManifest
from xenia.live.state import build_state, load_manifests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEMO_RUNS = REPOSITORY_ROOT / "tests" / "fixtures" / "live"
FIXED_TIME = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


@pytest.fixture
def demo_manifests() -> list[RunManifest]:
    """Return all checked-in synthetic fixture manifests."""
    return load_manifests(DEMO_RUNS)


@pytest.fixture
def demo_state(demo_manifests: list[RunManifest]) -> LiveState:
    """Return a reproducible state document from the synthetic fixtures."""
    return build_state(
        demo_manifests,
        generated_at=FIXED_TIME,
        git_sha="test-sha",
        package_version="0.1.0",
    )


@pytest.fixture
def fixed_time() -> datetime:
    """Return the fixed UTC test clock."""
    return FIXED_TIME
