"""Output models: the contract for ``tickets.json``.

These define the shape of the deliverable and act as the acceptance gate for
model-authored content. A ticket that fails validation here never reaches the
file; the failure is what the caller retries on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from triage.models.fields import (
    SCORE_RANGE,
    TICKET_TEXT_LIMIT,
    FindingId,
    NonEmptyStr,
    TicketId,
    TicketText,
)


class ScoreBlock(BaseModel):
    """A 1-10 score with the reasoning that produced it.

    The range is enforced here rather than in the JSON Schema because a strict
    structured-output schema drops numeric bounds; a score outside the range is a
    validation failure the caller can retry on.
    """

    model_config = ConfigDict(extra="forbid")

    score: int = Field(
        description=(
            f"Integer from {SCORE_RANGE[0]} to {SCORE_RANGE[1]} inclusive. "
            "Values outside that range are rejected."
        )
    )
    rationale: NonEmptyStr = Field(
        description="Cites the specific evidence behind this score, including any uncertainty."
    )

    @field_validator("score")
    @classmethod
    def _within_range(cls, value: int) -> int:
        low, high = SCORE_RANGE
        if not low <= value <= high:
            raise ValueError(f"score must be between {low} and {high}, got {value}")
        return value


class TicketTextBlock(BaseModel):
    """One piece of ticket prose: a summary, or a recommended action.

    Separate from :class:`Ticket` because the two are written by two passes with
    two prompts, and neither pass has the rest of the ticket to hand yet.

    The cap is enforced in a validator for the same reason :class:`ScoreBlock`'s
    range is: a strict structured-output schema drops the constraint, so an
    overrun has to fail here, where the caller can re-ask on it.
    """

    model_config = ConfigDict(extra="forbid")

    text: NonEmptyStr = Field(
        description=(
            f"At most {TICKET_TEXT_LIMIT} characters, counting spaces. "
            "Longer answers are rejected."
        )
    )

    @field_validator("text")
    @classmethod
    def _within_limit(cls, value: str) -> str:
        if len(value) > TICKET_TEXT_LIMIT:
            raise ValueError(
                f"text must be at most {TICKET_TEXT_LIMIT} characters, "
                f"got {len(value)}"
            )
        return value


class Ticket(BaseModel):
    """One triage ticket. Field order matches ``reference/example_ticket.json``.

    ``extra="forbid"`` keeps the output to exactly the specified structure.
    """

    model_config = ConfigDict(extra="forbid")

    ticket_id: TicketId
    finding_id: FindingId
    equipment_id: NonEmptyStr = Field(
        description="Must match an equipment_id in the registry."
    )
    summary: TicketText = Field(
        description=(
            "What is wrong, on what, and why it matters, usable in a planning "
            "meeting without opening the inspection record. Not a restatement of "
            f"the finding text. At most {TICKET_TEXT_LIMIT} characters."
        )
    )
    likelihood_of_failure: ScoreBlock
    impact_of_failure: ScoreBlock
    urgency: ScoreBlock
    recommended_action: TicketText = Field(
        description=(
            "A specific activity, not 'investigate further'. At most "
            f"{TICKET_TEXT_LIMIT} characters."
        )
    )
    review_required: bool = Field(
        description="Whether a human must check this ticket before it enters the work queue."
    )
    review_reason: NonEmptyStr | None = Field(
        default=None, description="Required when review_required is true, otherwise null."
    )

    @model_validator(mode="after")
    def _review_fields_agree(self) -> Self:
        if self.review_required and self.review_reason is None:
            raise ValueError("review_reason is required when review_required is true")
        if not self.review_required and self.review_reason is not None:
            raise ValueError("review_reason must be null when review_required is false")
        return self


class TicketDocument(BaseModel):
    """The whole of ``tickets.json``: one ticket per input finding."""

    model_config = ConfigDict(extra="forbid")

    generated_at: AwareDatetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO-8601 timestamp; must carry a timezone.",
    )
    tickets_generated: int = Field(ge=0)
    tickets: list[Ticket]

    @model_validator(mode="before")
    @classmethod
    def _default_count(cls, data: Any) -> Any:
        """Derive ``tickets_generated`` when the caller has not supplied it."""
        if isinstance(data, dict) and "tickets_generated" not in data:
            tickets = data.get("tickets")
            if isinstance(tickets, list):
                return {**data, "tickets_generated": len(tickets)}
        return data

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.tickets_generated != len(self.tickets):
            raise ValueError(
                f"tickets_generated ({self.tickets_generated}) does not match "
                f"the {len(self.tickets)} tickets present"
            )
        for label, values in (
            ("ticket_id", [t.ticket_id for t in self.tickets]),
            ("finding_id", [t.finding_id for t in self.tickets]),
        ):
            duplicates = sorted({v for v in values if values.count(v) > 1})
            if duplicates:
                raise ValueError(f"duplicate {label}: {', '.join(duplicates)}")
        return self


__all__ = ["ScoreBlock", "Ticket", "TicketDocument", "TicketTextBlock"]
