"""Fixtures shared by the whole suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository root, for tests that read the supplied files."""
    return Path(__file__).resolve().parents[1]
