"""Factories for the model tests.

Every fixture returns a callable so a test can override just the field it cares
about. The values are synthetic: no fixture is copied from ``data/``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from triage.models import ScoreBlock, Ticket

CsvRow = dict[str, str]


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
def score() -> Callable[..., ScoreBlock]:
    """A valid :class:`ScoreBlock`."""

    def _make(value: int = 5, rationale: str = "Synthetic rationale.") -> ScoreBlock:
        return ScoreBlock(score=value, rationale=rationale)

    return _make


@pytest.fixture
def ticket(score: Callable[..., ScoreBlock]) -> Callable[..., Ticket]:
    """A valid :class:`Ticket`."""

    def _make(**overrides: object) -> Ticket:
        fields: dict[str, object] = {
            "ticket_id": "TKT-9001",
            "finding_id": "F-9001",
            "equipment_id": "XX-0001",
            "summary": "Synthetic summary.",
            "likelihood_of_failure": score(),
            "impact_of_failure": score(),
            "urgency": score(),
            "recommended_action": "Replace the synthetic widget.",
            "review_required": False,
            "review_reason": None,
        }
        return Ticket(**(fields | overrides))

    return _make
