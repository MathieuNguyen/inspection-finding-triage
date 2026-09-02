"""The urgency derivation: pure arithmetic, so asserted as invariants.

There are only 200 inputs — ten likelihoods, ten impacts and the SCE flag — so
the whole space is enumerable, and these tests say what must hold across it
rather than picking examples out of it. Example tests would pin the one- and
two-point adjustments in place; these pin the properties those adjustments exist
to produce, which is what would actually be wrong if the arithmetic were changed.

Nothing here is a score for a row in ``data/``. The inputs are every integer pair
there is, which is a fact about the function rather than about the sample
findings.
"""

from __future__ import annotations

from itertools import product

import pytest
from pydantic import ValidationError

from triage.models import SCORE_RANGE
from triage.urgency import UrgencyBounds, derive_urgency

SCORES = range(SCORE_RANGE[0], SCORE_RANGE[1] + 1)
GRID = list(product(SCORES, SCORES, (False, True)))


def bounds(likelihood: int, impact: int, sce: bool = False) -> UrgencyBounds:
    return derive_urgency(
        likelihood=likelihood, impact=impact, safety_critical=sce
    )


def test_every_range_is_ordered_and_on_the_scale() -> None:
    """Whichever guardrails collided producing it, the range is usable."""
    for likelihood, impact, sce in GRID:
        result = bounds(likelihood, impact, sce)
        assert SCORE_RANGE[0] <= result.low <= result.high <= SCORE_RANGE[1], (
            f"L={likelihood} I={impact} SCE={sce} gave {result}"
        )


def test_raising_impact_never_lowers_urgency() -> None:
    for likelihood, sce in product(SCORES, (False, True)):
        for impact in SCORES[:-1]:
            lower, higher = bounds(likelihood, impact, sce), bounds(
                likelihood, impact + 1, sce
            )
            assert (higher.low, higher.high) >= (lower.low, lower.high), (
                f"L={likelihood} SCE={sce}: I={impact} gave {lower}, "
                f"I={impact + 1} gave {higher}"
            )


def test_raising_likelihood_never_lowers_urgency() -> None:
    for impact, sce in product(SCORES, (False, True)):
        for likelihood in SCORES[:-1]:
            lower, higher = bounds(likelihood, impact, sce), bounds(
                likelihood + 1, impact, sce
            )
            assert (higher.low, higher.high) >= (lower.low, lower.high), (
                f"I={impact} SCE={sce}: L={likelihood} gave {lower}, "
                f"L={likelihood + 1} gave {higher}"
            )


def test_impact_outranks_likelihood() -> None:
    """The asymmetry the whole derivation exists for.

    A remote failure of something consequential is more urgent than a near-certain
    failure of something trivial, and the two ranges do not even overlap.
    """
    for low, high in product(range(1, 4), range(7, 11)):
        remote_and_severe = bounds(likelihood=low, impact=high)
        certain_and_trivial = bounds(likelihood=high, impact=low)
        assert remote_and_severe.low > certain_and_trivial.high


def test_something_inconsequential_can_wait() -> None:
    """However certain the failure, a trivial consequence waits for a shutdown."""
    for likelihood, impact, sce in GRID:
        if impact <= 3:
            assert bounds(likelihood, impact, sce).high <= 4


def test_a_remote_failure_is_not_todays_problem() -> None:
    """Low likelihood reaches this week on the derived range, never today."""
    for likelihood, impact, sce in GRID:
        if likelihood <= 3:
            assert bounds(likelihood, impact, sce).high <= 8


def test_an_sce_consequence_does_not_slip_past_this_week() -> None:
    for likelihood, impact in product(SCORES, SCORES):
        if impact >= 7:
            assert bounds(likelihood, impact, sce=True).low >= 7


def test_a_remote_failure_on_an_sce_holds_at_this_week() -> None:
    """The one case where a ceiling and the floor cross. The floor wins."""
    assert bounds(likelihood=3, impact=7, sce=True) == UrgencyBounds(low=7, high=7)


@pytest.mark.parametrize(
    ("likelihood", "impact"), [(SCORE_RANGE[0],) * 2, (SCORE_RANGE[1],) * 2]
)
def test_the_corners_clamp(likelihood: int, impact: int) -> None:
    """The adjustment runs off the end of the scale at both extremes."""
    assert bounds(likelihood, impact) == UrgencyBounds(low=impact, high=impact)


@pytest.mark.parametrize(
    ("score", "inside"), [(4, False), (5, True), (6, True), (7, False)]
)
def test_contains_includes_its_endpoints(score: int, inside: bool) -> None:
    assert UrgencyBounds(low=5, high=6).contains(score) is inside


def test_an_inverted_range_is_not_a_range() -> None:
    with pytest.raises(ValidationError):
        UrgencyBounds(low=6, high=5)
