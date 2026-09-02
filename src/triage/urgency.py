"""Turn a likelihood and an impact into the urgency range they imply.

Urgency is not an average of the two and not their maximum. It **anchors on
impact** — what happens if the item fails — and is **moved by likelihood**. That
asymmetry is the whole point: a remote failure of something catastrophic still
needs attention this week, and a near-certain failure of something
inconsequential can wait for the next planned shutdown.

Three guardrails bound the result. Each is one sentence of
``src/triage/policies/urgency.md`` restated as arithmetic:

* Something inconsequential can wait, however certain the failure.
* Low likelihood tops out at "this week"; nothing that remote reaches "today"
  on the derived score alone.
* A Safety Critical Element's consequence does not slip past "this week",
  however remote the failure.

This is the one place in the project where a score is computed rather than
judged, and it is deliberately narrow: it returns a *range*, not an answer. The
model picks a number inside that range, writes the reasoning, and applies the two
override conditions — which carry it above the range and are the policy's
business, not this module's.

The numbers live here and the reasoning lives in the policy. Neither restates the
other, so there is still one authoritative copy of each.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from triage.models import SCORE_RANGE

_LOW = 3
"""At or below this, a dimension counts as low."""

_HIGH = 7
"""At or above this, a dimension counts as high."""

_NEXT_SHUTDOWN = 4
"""Top of the "next planned shutdown" band, where an inconsequential finding stops."""

_THIS_WEEK = (7, 8)
"""The "this week" band. Its floor holds SCEs up; its ceiling holds remote findings down."""


def _clamp(value: int) -> int:
    """Bring a derived score back inside 1-10."""
    low, high = SCORE_RANGE
    return max(low, min(high, value))


class UrgencyBounds(BaseModel):
    """The urgency range a likelihood and an impact imply.

    Advisory rather than a validation bound. The model is asked to score inside
    this range and is permitted to leave it with a stated reason, which is what
    :meth:`contains` is for — a departure is a review flag, not a rejection, and
    an override leaves the range by design. The hard 1-10 bound is
    :class:`~triage.models.ScoreBlock`'s, and stays a rejection.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    low: int = Field(ge=SCORE_RANGE[0], le=SCORE_RANGE[1])
    high: int = Field(ge=SCORE_RANGE[0], le=SCORE_RANGE[1])

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.low > self.high:
            raise ValueError(
                f"low ({self.low}) must not exceed high ({self.high})"
            )
        return self

    def contains(self, score: int) -> bool:
        """Whether ``score`` falls inside the range, endpoints included."""
        return self.low <= score <= self.high

    def __str__(self) -> str:
        """How the range is written into the prompt's user input."""
        return f"{self.low} to {self.high}"


def derive_urgency(
    *, likelihood: int, impact: int, safety_critical: bool
) -> UrgencyBounds:
    """The urgency range these two scores imply, before the model judges it.

    Impact sets the anchor and likelihood moves it, by one or two points in
    either direction. The guardrails then bound the result; see the module
    docstring for what each one is for.
    """
    if likelihood >= _HIGH:
        low, high = impact + 1, impact + 2
    elif likelihood <= _LOW:
        low, high = impact - 2, impact - 1
    else:
        low, high = impact - 1, impact + 1

    if impact <= _LOW:
        high = min(high, _NEXT_SHUTDOWN)
    if likelihood <= _LOW:
        high = min(high, _THIS_WEEK[1])
    if safety_critical and impact >= _HIGH:
        low = max(low, _THIS_WEEK[0])

    low, high = _clamp(low), _clamp(high)

    # A remote finding on an SCE at impact 7 is the one case where the two
    # collide: likelihood drags the top down to 6 while the SCE floor holds the
    # bottom at 7. The floor wins, because it is the stronger claim — an SCE
    # consequence does not drop below "this week" for being unlikely.
    high = max(high, low)

    return UrgencyBounds(low=low, high=high)


__all__ = ["UrgencyBounds", "derive_urgency"]
