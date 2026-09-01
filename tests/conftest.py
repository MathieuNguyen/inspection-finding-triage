"""Fixtures shared by the whole suite.

The two row factories live here rather than in ``tests/models/`` because both
the model tests and the registry tests build CSV rows. Every fixture returns a
callable so a test can override just the field it cares about, and every value
is synthetic: nothing is copied from ``data/``.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

CsvRow = dict[str, str]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository root, for tests that read the supplied files."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def finding_row() -> Callable[..., CsvRow]:
    """A well-formed ``inspection_findings.csv`` row, as strings."""

    def _make(**overrides: str) -> CsvRow:
        row: CsvRow = {
            "finding_id": "F-9001",
            "reported_date": "2026-01-15",
            "equipment_id": "XX-0001",
            "equipment_type": "Widget",
            "inspection_type": "Routine Operator Round",
            "inspection_method": "Visual",
            "finding_description": "Synthetic description used only for schema tests.",
            "reported_by": "A. Tester",
            "reporter_role": "Test Engineer",
        }
        return row | overrides

    return _make


@pytest.fixture
def equipment_row() -> Callable[..., CsvRow]:
    """A well-formed ``equipment_registry.csv`` row, as strings."""

    def _make(**overrides: str) -> CsvRow:
        row: CsvRow = {
            "equipment_id": "XX-0001",
            "equipment_type": "Widget",
            "service_description": "Synthetic item",
            "criticality_score": "6",
            "reliability_score": "7",
            "safety_critical_element": "No",
            "redundancy": "None",
            "engineer_comment": "",
        }
        return row | overrides

    return _make


@pytest.fixture
def csv_file(tmp_path: Path) -> Callable[..., Path]:
    """Write rows to a throwaway CSV and return its path.

    ``header`` defaults to the keys of the first row; pass it explicitly to
    write a file whose header is wrong or incomplete.
    """

    def _make(
        rows: Sequence[CsvRow],
        *,
        name: str = "rows.csv",
        header: Sequence[str] | None = None,
        encoding: str = "utf-8",
    ) -> Path:
        fields = list(header) if header is not None else list(rows[0])
        path = tmp_path / name
        with path.open("w", newline="", encoding=encoding) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return path

    return _make
