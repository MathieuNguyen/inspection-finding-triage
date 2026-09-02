"""Output models: the contract for ``tickets.json``.

These define the shape of the deliverable and act as the acceptance gate for
model-authored content. A ticket that fails validation here never reaches the
file; the failure is what the caller retries on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
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
    TICKET_TEXT_TARGET,
    URGENCY_OVERRIDE_FLOOR,
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


class UrgencyOverride(StrEnum):
    """A condition that forces immediate urgency, whatever the derived score.

    Both are stated in ``src/triage/policies/urgency.md``. Naming them here makes
    the model's determination a field rather than a claim buried in prose: a
    later pass can route on it, and the score can be checked against it.
    """

    PROTECTION_LAYER = "protection_layer"
    """A protection layer left impaired without a recorded deviation."""

    EVACUATION_CAPACITY = "evacuation_capacity"
    """Evacuation capacity reduced below the POB count."""


class UrgencyBlock(ScoreBlock):
    """The urgency pass's answer: a score, its reasoning, and any override.

    Separate from :class:`ScoreBlock` because urgency is the one dimension with
    conditions that force the score regardless of what likelihood and impact
    imply. ``Ticket.urgency`` stays a plain ``ScoreBlock``: which override fired
    is how this ticket got its number, not part of the delivered shape.

    The range from :func:`triage.urgency.derive_urgency` is deliberately not
    enforced here. Leaving it is a judgement the model is allowed to make and a
    human is asked to check, so a departure sets the review flag rather than
    failing. Only the 1-10 range and the override floor are hard.
    """

    override: UrgencyOverride | None = Field(
        description=(
            "The override condition this finding meets, or null if it meets "
            f"neither. When set, the score must be at least "
            f"{URGENCY_OVERRIDE_FLOOR}."
        )
    )

    @model_validator(mode="after")
    def _override_forces_immediate(self) -> Self:
        if self.override is not None and self.score < URGENCY_OVERRIDE_FLOOR:
            raise ValueError(
                f"{self.override.value} is an override condition: score must be "
                f"at least {URGENCY_OVERRIDE_FLOOR}, got {self.score}"
            )
        return self


class TicketTextBlock(BaseModel):
    """One piece of ticket prose: a summary, or a recommended action.

    Separate from :class:`Ticket` because the two are written by two passes with
    two prompts, and neither pass has the rest of the ticket to hand yet.

    The cap is enforced in a validator for the same reason :class:`ScoreBlock`'s
    range is: a strict structured-output schema drops the constraint, so an
    overrun has to fail here, where the caller can re-ask on it.

    The description asks for :data:`~triage.models.TICKET_TEXT_TARGET` rather
    than the cap. Aiming at the cap is what puts answers over it: the model has
    no way to count precisely, so the only reliable margin is one it was told to
    leave.
    """

    model_config = ConfigDict(extra="forbid")

    text: NonEmptyStr = Field(
        description=(
            f"Between {TICKET_TEXT_TARGET[0]} and {TICKET_TEXT_TARGET[1]} "
            f"characters, counting spaces. More than {TICKET_TEXT_LIMIT} is "
            "rejected."
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


class TicketFailure(BaseModel):
    """One finding that produced no ticket, and what stopped it.

    Recorded in the document rather than only on the terminal. A partial run is
    read later, by someone who no longer has the run's output in front of them,
    and a file that does not say what is missing from it reads as complete.

    What is kept is what identifies the failure and what a person needs to act
    on it. The exception itself is not serialisable and its traceback belongs in
    the log, not in the deliverable.
    """

    model_config = ConfigDict(extra="forbid")

    finding_id: FindingId
    error: NonEmptyStr = Field(
        description="The exception type that ended this finding."
    )
    detail: NonEmptyStr = Field(description="What it said.")


class TicketDocument(BaseModel):
    """The whole of ``tickets.json``: the tickets, and the findings that failed.

    A finding that could not be triaged does not silently vanish from the run.
    It appears in :attr:`failures` instead, so the document accounts for every
    finding it was given — either as a ticket or as a reason there is none.
    """

    model_config = ConfigDict(extra="forbid")

    generated_at: AwareDatetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO-8601 timestamp; must carry a timezone.",
    )
    tickets_generated: int = Field(ge=0)
    findings_failed: int = Field(default=0, ge=0)
    tickets: list[Ticket]
    failures: list[TicketFailure] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _default_counts(cls, data: Any) -> Any:
        """Derive each count from its list when the caller has not supplied it."""
        if not isinstance(data, dict):
            return data
        derived = {}
        for count, listing in (
            ("tickets_generated", "tickets"),
            ("findings_failed", "failures"),
        ):
            if count not in data and isinstance(data.get(listing), list):
                derived[count] = len(data[listing])
        return {**data, **derived} if derived else data

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        for count, label, length in (
            (self.tickets_generated, "tickets", len(self.tickets)),
            (self.findings_failed, "failures", len(self.failures)),
        ):
            if count != length:
                raise ValueError(
                    f"the count of {label} ({count}) does not match the "
                    f"{length} present"
                )
        for label, values in (
            ("ticket_id", [t.ticket_id for t in self.tickets]),
            (
                "finding_id",
                [t.finding_id for t in self.tickets]
                + [f.finding_id for f in self.failures],
            ),
        ):
            duplicates = sorted({v for v in values if values.count(v) > 1})
            if duplicates:
                raise ValueError(f"duplicate {label}: {', '.join(duplicates)}")
        return self


__all__ = [
    "ScoreBlock",
    "Ticket",
    "TicketDocument",
    "TicketFailure",
    "TicketTextBlock",
    "UrgencyBlock",
    "UrgencyOverride",
]
