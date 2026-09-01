"""Prompt templates, and the checks that keep a spec honest about its markdown.

The two prompt files ship empty, so the consistency rule is exercised here on
synthetic text rather than on the real files. That is the point of it: the rule
has to be right *before* there is anything to check, because its whole job is to
catch an edit made months from now.
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from triage.llm import (
    PROMPTS,
    Effort,
    Policy,
    PromptError,
    PromptName,
    PromptSpec,
    check_placeholders,
    check_prompt,
    placeholders,
    render_prompt,
)
from triage.llm.prompts import RESERVED_VARIABLE


@pytest.mark.parametrize("name", list(PromptName))
def test_every_prompt_is_declared_and_backed_by_a_file(name: PromptName) -> None:
    """The spec's validator refuses a missing file, so reaching here proves both."""
    assert PROMPTS[name].name is name


@pytest.mark.parametrize("name", list(PromptName))
def test_every_declared_prompt_agrees_with_its_markdown(name: PromptName) -> None:
    """Passes trivially while the file is empty, and enforces from the first word."""
    check_prompt(PROMPTS[name])


def test_scoring_judges_and_extraction_writes() -> None:
    """Where the medium/high split is declared: once per pass, not per call site."""
    assert PROMPTS[PromptName.SCORING].effort is Effort.JUDGING
    assert PROMPTS[PromptName.EXTRACTION].effort is Effort.WRITING


def test_scoring_reads_every_policy() -> None:
    """Urgency has overrides that outrank the derived score; none of it can be omitted."""
    assert set(PROMPTS[PromptName.SCORING].policies) == set(Policy)


def test_the_registry_covers_the_whole_enum() -> None:
    """Adding a PromptName without a spec, or a file, must fail at import.

    ``PROMPTS`` is built at module scope and every spec validates its own file,
    so a member added without one never gets as far as this assertion.
    """
    assert set(PROMPTS) == set(PromptName)


def test_a_spec_cannot_claim_the_reserved_variable() -> None:
    """``$policies`` is filled from the spec; declaring it would fight the machinery."""
    with pytest.raises(ValidationError, match="reserved"):
        PromptSpec(
            name=PromptName.SCORING,
            variables=frozenset({RESERVED_VARIABLE}),
            effort=Effort.JUDGING,
        )


def test_a_spec_is_frozen() -> None:
    """A declaration, not a knob: nothing reconfigures a prompt at run time."""
    with pytest.raises(ValidationError):
        PROMPTS[PromptName.SCORING].effort = Effort.WRITING  # type: ignore[misc]


def test_policies_are_expected_only_when_the_spec_injects_them() -> None:
    plain = PromptSpec(
        name=PromptName.EXTRACTION, variables=frozenset({"finding"}), effort=Effort.WRITING
    )
    assert plain.expected_variables == frozenset({"finding"})
    assert PROMPTS[PromptName.EXTRACTION].expected_variables == frozenset(
        {"finding", RESERVED_VARIABLE}
    )


def test_placeholders_are_dollar_names_so_braces_stay_literal() -> None:
    """Prompt text carries JSON; ``str.format`` would choke on every brace."""
    text = 'Return {"score": 7} for $finding.'
    assert placeholders(text) == frozenset({"finding"})


def test_a_stray_dollar_sign_is_caught_with_advice() -> None:
    with pytest.raises(PromptError, match=r"\$\$"):
        placeholders("A repair costing $ 4000.")


def test_an_undeclared_placeholder_is_rejected() -> None:
    """It would otherwise reach the model as the literal text ``$equipment``."""
    with pytest.raises(PromptError, match=r"undeclared \$equipment"):
        check_placeholders("Assess $finding on $equipment.", frozenset({"finding"}))


def test_a_declared_but_unused_variable_is_rejected() -> None:
    """The value would be assembled at the call site and silently dropped."""
    with pytest.raises(PromptError, match=r"unused \$equipment"):
        check_placeholders(
            "Assess $finding.", frozenset({"finding", "equipment"})
        )


def test_both_directions_are_reported_together() -> None:
    with pytest.raises(PromptError) as caught:
        check_placeholders("Assess $wrong.", frozenset({"right"}))
    assert "$wrong" in str(caught.value)
    assert "$right" in str(caught.value)


def test_an_empty_prompt_warns_rather_than_failing(caplog: pytest.LogCaptureFixture) -> None:
    """The stubs ship empty and the layer still has to import and test."""
    with caplog.at_level(logging.WARNING, logger="triage.llm.prompts"):
        check_prompt(PROMPTS[PromptName.SCORING])
    assert "empty" in caplog.text


def test_an_empty_prompt_refuses_to_render() -> None:
    """Warning is right at import; sending a blank instruction to the model is not."""
    with pytest.raises(PromptError, match="empty"):
        render_prompt(
            PromptName.SCORING, finding="x", equipment="y", redundancy="z"
        )
