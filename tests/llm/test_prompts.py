"""Loading the markdown and assembling one file into another.

Nothing here asserts on what a policy or a prompt *says*. That text is going to
be rewritten as the judgement behind it changes, and a test pinning its wording
would be friction the file-based arrangement exists to remove.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

import triage

from triage.llm import PolicyError, PromptError, build_prompt, load_policy, load_prompt

POLICIES = ["likelihood", "impact", "urgency", "errors"]
PROMPTS = [
    "summary",
    "scoring_likelihood",
    "scoring_impact",
    "scoring_urgency",
    "actions",
]


@pytest.mark.parametrize("name", POLICIES)
def test_every_policy_loads(name: str) -> None:
    assert load_policy(name)


@pytest.mark.parametrize("name", PROMPTS)
def test_every_prompt_file_exists(name: str) -> None:
    """Loading an empty file must still work: the prompts ship blank."""
    assert isinstance(load_prompt(name), str)


@pytest.mark.parametrize(
    ("load", "name"),
    [(load_policy, "likelihood"), (load_prompt, "summary")],
    ids=["policy", "prompt"],
)
def test_front_matter_does_not_reach_the_model(
    load: Callable[[str], str], name: str
) -> None:
    """Version, author and date are for whoever maintains the file."""
    text = load(name)
    assert not text.startswith("---")
    assert "author:" not in text


def test_a_missing_policy_says_where_it_looked() -> None:
    with pytest.raises(PolicyError, match="policies/nowhere.md"):
        load_policy("nowhere")


def test_a_missing_prompt_says_where_it_looked() -> None:
    with pytest.raises(PromptError, match="prompts/nowhere.md"):
        load_prompt("nowhere")


def test_an_empty_prompt_refuses_to_build(
    written_prompt: Callable[[str], None]
) -> None:
    """Sending a blank instruction to the model is never what was meant."""
    written_prompt("")
    with pytest.raises(PromptError, match="empty"):
        build_prompt("summary")


def test_an_empty_policy_warns_rather_than_failing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A policy being written must not stop the rest of the layer working."""
    load_policy.cache_clear()
    with caplog.at_level(logging.WARNING, logger="triage.llm.prompts"):
        empty = [name for name in POLICIES if not load_policy(name)]

    for name in empty:
        assert name in caplog.text


@pytest.fixture
def written_prompt() -> Iterator[Callable[[str], None]]:
    """Put text in ``summary.md`` for one test, then put it back.

    The prompts ship empty, so filling one has to be exercised against a real
    file rather than against a fixture that fakes the loading.
    """
    path = Path(triage.__file__).parent / "prompts" / "summary.md"
    original = path.read_bytes()

    def _write(text: str) -> None:
        path.write_text(text)
        load_prompt.cache_clear()

    try:
        yield _write
    finally:
        path.write_bytes(original)
        load_prompt.cache_clear()


def test_a_prompt_is_filled_with_the_values_it_is_given(
    written_prompt: Callable[[str], None]
) -> None:
    written_prompt("Summarise {finding} on {equipment}.\n\n{policy}")
    built = build_prompt(
        "summary",
        finding="Bearing vibration rising",
        equipment="Seawater lift pump",
        policy=load_policy("impact"),
    )
    assert "Summarise Bearing vibration rising on Seawater lift pump." in built
    assert "What moves impact" in built
    assert "{" not in built


def test_a_missing_value_names_the_prompt(
    written_prompt: Callable[[str], None]
) -> None:
    """Otherwise it reaches the model as the literal text ``{equipment}``."""
    written_prompt("Summarise {finding} on {equipment}.")
    with pytest.raises(PromptError, match="summary"):
        build_prompt("summary", finding="x")
