"""Run configuration, and the two reasoning budgets.

Every test builds settings explicitly. Nothing here reads the environment or a
``.env``, so the suite behaves the same on a machine that has one and a machine
that does not.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from triage.llm import Effort, LlmSettings

Settings = Callable[..., LlmSettings]


def test_the_defaults_are_the_intended_production_values(settings: Settings) -> None:
    """These defaults are the configuration, not placeholders for it."""
    config = settings()
    assert config.model == "gpt-5.6-luna"
    assert config.writing_effort == "medium"
    assert config.judging_effort == "high"
    assert config.max_retries == 3
    assert config.max_output_attempts == 3


def test_writing_thinks_less_than_judging(settings: Settings) -> None:
    """The split the whole layer exists to express: reading is cheaper than deciding."""
    config = settings()
    assert config.effort_for(Effort.WRITING) == "medium"
    assert config.effort_for(Effort.JUDGING) == "high"


def test_either_budget_can_be_retuned_without_a_code_change(settings: Settings) -> None:
    config = settings(writing_effort="low", judging_effort="xhigh")
    assert config.effort_for(Effort.WRITING) == "low"
    assert config.effort_for(Effort.JUDGING) == "xhigh"


def test_every_effort_member_resolves(settings: Settings) -> None:
    """A new Effort member without a budget should fail here, not at a call site."""
    config = settings()
    assert all(config.effort_for(effort) for effort in Effort)


@pytest.mark.parametrize("level", ["none", "max", "medium-ish", ""])
def test_an_unsupported_effort_is_rejected(settings: Settings, level: str) -> None:
    """A typo in an environment variable should not reach the API as-is."""
    with pytest.raises(ValidationError):
        settings(judging_effort=level)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_concurrency", 0),
        ("request_timeout", 0),
        ("max_retries", -1),
        ("max_output_attempts", 0),
    ],
)
def test_nonsensical_limits_are_rejected(
    settings: Settings, field: str, value: float
) -> None:
    with pytest.raises(ValidationError):
        settings(**{field: value})


def test_one_attempt_is_allowed(settings: Settings) -> None:
    """Retrying on invalid output is a choice, not a requirement."""
    assert settings(max_output_attempts=1).max_output_attempts == 1


def test_the_api_key_does_not_appear_in_a_repr(settings: Settings) -> None:
    """A settings object in a traceback or a log line must not leak the key."""
    config = settings(openai_api_key="sk-should-never-be-printed")
    assert "sk-should-never-be-printed" not in repr(config)
    assert "sk-should-never-be-printed" not in str(config)
    assert config.openai_api_key.get_secret_value() == "sk-should-never-be-printed"


def test_a_blank_key_is_rejected(settings: Settings) -> None:
    """``.env.example`` ships the key empty; copying it unfilled must fail here.

    Otherwise the first symptom is an opaque 401 partway through a run.
    """
    with pytest.raises(ValidationError):
        settings(openai_api_key="")
