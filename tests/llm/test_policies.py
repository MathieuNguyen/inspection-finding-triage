"""Loading the policy markdown and composing it for a prompt.

Nothing here asserts on what a policy *says*. The four files are about to be
written and rewritten, and a test that pinned their wording would have to be
edited every time the judgement behind them changed — which is exactly the
friction the file-based arrangement exists to remove. What is tested is
mechanical: the files resolve, the bundle is ordered and complete, and the
fingerprint tracks the text.
"""

from __future__ import annotations

import logging

import pytest

from triage.llm import Policy, load_policy, policy_bundle, policy_fingerprint
from triage.llm.policies import FINGERPRINT_LENGTH


@pytest.mark.parametrize("policy", list(Policy))
def test_every_policy_resolves_to_a_file(policy: Policy) -> None:
    """A member without a file is a packaging fault, not a runtime surprise."""
    assert isinstance(load_policy(policy), str)


def test_the_four_dimensions_are_all_declared() -> None:
    """Likelihood, impact and urgency are the ticket's three scores; errors guards them."""
    assert {p.value for p in Policy} == {"likelihood", "impact", "urgency", "errors"}


def test_an_empty_policy_warns_rather_than_failing(caplog: pytest.LogCaptureFixture) -> None:
    """The files ship empty, so the layer has to run before they are written."""
    load_policy.cache_clear()
    with caplog.at_level(logging.WARNING, logger="triage.llm.policies"):
        empty = [p for p in Policy if not load_policy(p)]

    for policy in empty:
        assert policy.value in caplog.text


def test_a_bundle_keeps_the_order_it_was_given() -> None:
    """The prompt decides what the model reads first, not the enum's declaration order."""
    forwards = policy_bundle(Policy.LIKELIHOOD, Policy.IMPACT)
    backwards = policy_bundle(Policy.IMPACT, Policy.LIKELIHOOD)
    assert forwards.index("## Likelihood") < forwards.index("## Impact")
    assert backwards.index("## Impact") < backwards.index("## Likelihood")


def test_every_requested_policy_gets_a_heading() -> None:
    """A visibly blank section is easier to notice than a silently absent one."""
    bundle = policy_bundle(*Policy)
    for policy in Policy:
        assert f"## {policy.title}" in bundle


def test_an_empty_selection_bundles_to_nothing() -> None:
    assert policy_bundle() == ""


def test_the_fingerprint_is_stable_for_the_same_text() -> None:
    """Two runs against unchanged policies must be attributable to the same wording."""
    assert policy_fingerprint(*Policy) == policy_fingerprint(*Policy)
    assert len(policy_fingerprint(*Policy)) == FINGERPRINT_LENGTH


def test_the_fingerprint_distinguishes_different_selections() -> None:
    """A prompt that reads three policies is not traceable to a run that read four."""
    assert policy_fingerprint(Policy.LIKELIHOOD) != policy_fingerprint(
        Policy.LIKELIHOOD, Policy.IMPACT
    )


def test_the_fingerprint_follows_the_order_read() -> None:
    assert policy_fingerprint(Policy.LIKELIHOOD, Policy.IMPACT) != policy_fingerprint(
        Policy.IMPACT, Policy.LIKELIHOOD
    )
