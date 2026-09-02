"""The ticket models: the acceptance gate for anything a model authored."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from triage.models import (
    SCORE_RANGE,
    TICKET_TEXT_LIMIT,
    URGENCY_OVERRIDE_FLOOR,
    ScoreBlock,
    Ticket,
    TicketDocument,
    TicketTextBlock,
    UrgencyBlock,
    UrgencyOverride,
)


@pytest.mark.parametrize("value", [SCORE_RANGE[0] - 1, SCORE_RANGE[1] + 1, -1])
def test_score_outside_range_rejected(value: int) -> None:
    with pytest.raises(ValidationError):
        ScoreBlock(score=value, rationale="Out of range.")


def test_score_rationale_must_say_something() -> None:
    with pytest.raises(ValidationError):
        ScoreBlock(score=5, rationale="   ")


def test_urgency_override_forces_the_top_band() -> None:
    """An override condition is immediate; a score below the floor contradicts it."""
    with pytest.raises(ValidationError):
        UrgencyBlock(
            score=URGENCY_OVERRIDE_FLOOR - 1,
            rationale="Says immediate, scores otherwise.",
            override=UrgencyOverride.PROTECTION_LAYER,
        )


@pytest.mark.parametrize("score", [URGENCY_OVERRIDE_FLOOR, SCORE_RANGE[1]])
def test_urgency_override_leaves_room_inside_the_top_band(score: int) -> None:
    """A floor, not a fixed 10: defeated and degraded do not score the same."""
    block = UrgencyBlock(
        score=score,
        rationale="Evacuation capacity reduced; POB margin not verifiable.",
        override=UrgencyOverride.EVACUATION_CAPACITY,
    )
    assert block.score == score


def test_urgency_without_an_override_takes_any_score_in_range() -> None:
    assert UrgencyBlock(score=2, rationale="Backlog.", override=None).score == 2


def test_urgency_inherits_the_score_range() -> None:
    with pytest.raises(ValidationError):
        UrgencyBlock(score=SCORE_RANGE[1] + 1, rationale="Out of range.", override=None)


def test_urgency_override_must_be_answered() -> None:
    """Explicit null rather than an absent field: the question is always asked."""
    with pytest.raises(ValidationError):
        UrgencyBlock(score=5, rationale="Silent on the overrides.")


def test_text_block_takes_the_whole_budget() -> None:
    assert len(TicketTextBlock(text="x" * TICKET_TEXT_LIMIT).text) == TICKET_TEXT_LIMIT


def test_text_block_rejects_one_character_over() -> None:
    """The cap is a validator, not a schema keyword, so it has to be exercised."""
    with pytest.raises(ValidationError):
        TicketTextBlock(text="x" * (TICKET_TEXT_LIMIT + 1))


def test_text_block_must_say_something() -> None:
    with pytest.raises(ValidationError):
        TicketTextBlock(text="   ")


def test_summary_and_action_capped(ticket: Callable[..., Ticket]) -> None:
    overlong = "x" * (TICKET_TEXT_LIMIT + 1)
    with pytest.raises(ValidationError):
        ticket(summary=overlong)
    with pytest.raises(ValidationError):
        ticket(recommended_action=overlong)


def test_review_reason_required_when_flagged(ticket: Callable[..., Ticket]) -> None:
    with pytest.raises(ValidationError):
        ticket(review_required=True, review_reason=None)


def test_review_reason_forbidden_when_not_flagged(ticket: Callable[..., Ticket]) -> None:
    with pytest.raises(ValidationError):
        ticket(review_required=False, review_reason="Contradictory.")


def test_ticket_rejects_extra_fields(ticket: Callable[..., Ticket]) -> None:
    with pytest.raises(ValidationError):
        ticket(confidence=0.8)


def test_document_counts_tickets_when_not_given(ticket: Callable[..., Ticket]) -> None:
    assert TicketDocument(tickets=[ticket()]).tickets_generated == 1


def test_document_rejects_wrong_count(ticket: Callable[..., Ticket]) -> None:
    with pytest.raises(ValidationError):
        TicketDocument(tickets_generated=2, tickets=[ticket()])


def test_document_rejects_duplicate_ids(ticket: Callable[..., Ticket]) -> None:
    with pytest.raises(ValidationError):
        TicketDocument(tickets=[ticket(), ticket()])


def test_document_requires_aware_timestamp(ticket: Callable[..., Ticket]) -> None:
    with pytest.raises(ValidationError):
        TicketDocument(generated_at=datetime(2026, 1, 1), tickets=[ticket()])


def test_document_serialises_to_the_required_shape(ticket: Callable[..., Ticket]) -> None:
    document = TicketDocument(
        generated_at=datetime(2026, 1, 1, tzinfo=UTC), tickets=[ticket()]
    )
    payload = json.loads(document.model_dump_json())
    assert list(payload) == ["generated_at", "tickets_generated", "tickets"]
    assert payload["generated_at"].startswith("2026-01-01T00:00:00")
    assert list(payload["tickets"][0]) == [
        "ticket_id",
        "finding_id",
        "equipment_id",
        "summary",
        "likelihood_of_failure",
        "impact_of_failure",
        "urgency",
        "recommended_action",
        "review_required",
        "review_reason",
    ]
