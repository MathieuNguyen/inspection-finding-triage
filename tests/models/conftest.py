"""Factories for the model tests.

The CSV row factories are in ``tests/conftest.py``; what remains here is
specific to the output models.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from triage.models import ScoreBlock, Ticket, TicketFailure


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


@pytest.fixture
def failure() -> Callable[..., TicketFailure]:
    """A valid :class:`TicketFailure`."""

    def _make(**overrides: object) -> TicketFailure:
        fields: dict[str, object] = {
            "finding_id": "F-9002",
            "error": "OutputValidationError",
            "detail": "Synthetic failure detail.",
        }
        return TicketFailure(**(fields | overrides))

    return _make
