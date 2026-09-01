"""Doubles for the LLM tests.

No network, no API key, no mocking library. The stubs below are hand-written for
the same reason the rest of the suite avoids mocks: what the client sends is part
of the contract, so a test should be able to read it back and assert on it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from triage.llm import LlmSettings
from triage.models import ScoreBlock


def out_of_range() -> ValidationError:
    """A real :class:`ValidationError`, produced the way the model produces one.

    A score of 12 is well-formed JSON that ``ScoreBlock`` rejects — exactly the
    failure the output retry exists for. Raising the genuine article beats
    hand-building an error whose shape might not match.
    """
    try:
        ScoreBlock(score=12, rationale="Out of range.")
    except ValidationError as exc:
        return exc
    raise AssertionError("ScoreBlock accepted a score of 12")


class StubResponse:
    """Only the parts of a parsed response that the client actually reads."""

    def __init__(
        self,
        parsed: Any = None,
        *,
        status: str = "completed",
        incomplete_reason: str | None = None,
        refusal: str | None = None,
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.output_parsed = parsed
        self.status = status
        self.incomplete_details = SimpleNamespace(reason=incomplete_reason)
        self.usage = usage
        self.output: list[SimpleNamespace] = []
        if refusal is not None:
            self.output.append(
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="refusal", refusal=refusal)],
                )
            )


class StubResponses:
    """Returns each queued outcome in turn, recording what it was sent."""

    def __init__(self, outcomes: Sequence[Any]) -> None:
        self._outcomes: Iterator[Any] = iter(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        try:
            outcome = next(self._outcomes)
        except StopIteration:  # pragma: no cover - a test queued too few outcomes
            raise AssertionError("the client made more calls than the stub expected") from None
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class StubClient:
    """Stands in for ``AsyncOpenAI``, exposing only ``responses.parse``."""

    def __init__(self, *outcomes: Any) -> None:
        self.responses = StubResponses(outcomes)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.responses.calls


@pytest.fixture
def settings() -> Callable[..., LlmSettings]:
    """Settings built in full, never read from the environment or a ``.env``."""

    def _make(**overrides: object) -> LlmSettings:
        fields: dict[str, object] = {"openai_api_key": "test-key"}
        return LlmSettings(_env_file=None, **(fields | overrides))

    return _make


@pytest.fixture
def response() -> Callable[..., StubResponse]:
    """A parsed response carrying whatever the test needs it to."""
    return StubResponse


@pytest.fixture
def stub_client() -> Callable[..., StubClient]:
    """A stand-in for ``AsyncOpenAI``, given one outcome per expected call."""
    return StubClient


@pytest.fixture
def invalid_output() -> Callable[[], ValidationError]:
    """The failure the output retry exists for: a score outside 1-10."""
    return out_of_range
