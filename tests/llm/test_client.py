"""The structured call: what it sends, and what it does with what comes back.

Every test runs against a hand-written stub. Nothing here opens a socket or needs
an API key, and the stub records each request so the outgoing shape is asserted
rather than assumed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from triage.llm import (
    Effort,
    EmptyResponseError,
    IncompleteResponseError,
    LlmSettings,
    OutputValidationError,
    RefusalError,
    TriageClient,
)
from triage.models import ScoreBlock

Settings = Callable[..., LlmSettings]
Client = Callable[..., Any]
Response = Callable[..., Any]
Invalid = Callable[[], Exception]

ANSWER = ScoreBlock(score=7, rationale="Synthetic rationale.")


def _wire(stub: Any, settings: Settings, **overrides: object) -> TriageClient:
    return TriageClient(stub, settings(**overrides))


async def _call(client: TriageClient, effort: Effort = Effort.JUDGING) -> ScoreBlock:
    return await client.structured(
        instructions="Synthetic instructions.",
        user_input="Synthetic finding.",
        text_format=ScoreBlock,
        effort=effort,
    )


async def test_a_completed_response_returns_the_parsed_model(
    settings: Settings, stub_client: Client, response: Response
) -> None:
    stub = stub_client(response(ANSWER))
    assert await _call(_wire(stub, settings)) is ANSWER


@pytest.mark.parametrize(
    ("effort", "level"), [(Effort.WRITING, "medium"), (Effort.JUDGING, "high")]
)
async def test_the_reasoning_budget_matches_the_kind_of_work(
    settings: Settings,
    stub_client: Client,
    response: Response,
    effort: Effort,
    level: str,
) -> None:
    """Writing thinks at medium, judging at high. The requirement, pinned."""
    stub = stub_client(response(ANSWER))
    await _call(_wire(stub, settings), effort)
    assert stub.calls[0]["reasoning"] == {"effort": level}


async def test_a_retuned_budget_reaches_the_request(
    settings: Settings, stub_client: Client, response: Response
) -> None:
    stub = stub_client(response(ANSWER))
    await _call(_wire(stub, settings, judging_effort="xhigh"), Effort.JUDGING)
    assert stub.calls[0]["reasoning"] == {"effort": "xhigh"}


async def test_the_request_carries_the_model_schema_and_instructions(
    settings: Settings, stub_client: Client, response: Response
) -> None:
    stub = stub_client(response(ANSWER))
    await _call(_wire(stub, settings, model="gpt-test"))

    sent = stub.calls[0]
    assert sent["model"] == "gpt-test"
    assert sent["text_format"] is ScoreBlock
    assert sent["instructions"] == "Synthetic instructions."
    assert sent["input"] == [{"role": "user", "content": "Synthetic finding."}]


async def test_a_cache_key_is_passed_through(
    settings: Settings, stub_client: Client, response: Response
) -> None:
    """A batch shares its instructions; a stable key lets them be cached."""
    stub = stub_client(response(ANSWER))
    await _wire(stub, settings).structured(
        instructions="Synthetic instructions.",
        user_input="Synthetic finding.",
        text_format=ScoreBlock,
        effort=Effort.WRITING,
        cache_key="triage-batch",
    )
    assert stub.calls[0]["prompt_cache_key"] == "triage-batch"


async def test_an_incomplete_response_is_refused(
    settings: Settings, stub_client: Client, response: Response
) -> None:
    """A truncated answer is not a cheap answer; it is a wrong one."""
    stub = stub_client(
        response(None, status="incomplete", incomplete_reason="max_output_tokens")
    )
    with pytest.raises(IncompleteResponseError, match="max_output_tokens"):
        await _call(_wire(stub, settings))


async def test_a_refusal_carries_its_explanation(
    settings: Settings, stub_client: Client, response: Response
) -> None:
    stub = stub_client(response(None, refusal="Cannot assess this."))
    with pytest.raises(RefusalError, match="Cannot assess this."):
        await _call(_wire(stub, settings))


async def test_a_response_with_no_parsed_output_is_refused(
    settings: Settings, stub_client: Client, response: Response
) -> None:
    stub = stub_client(response(None))
    with pytest.raises(EmptyResponseError, match="ScoreBlock"):
        await _call(_wire(stub, settings))


async def test_invalid_output_is_re_asked_and_can_succeed(
    settings: Settings, stub_client: Client, response: Response, invalid_output: Invalid
) -> None:
    """A score outside 1-10 is well-formed JSON the models reject. Ask again."""
    stub = stub_client(invalid_output(), response(ANSWER))
    assert await _call(_wire(stub, settings, max_output_attempts=2)) is ANSWER
    assert len(stub.calls) == 2


async def test_the_re_ask_quotes_what_was_wrong(
    settings: Settings, stub_client: Client, response: Response, invalid_output: Invalid
) -> None:
    """Naming the constraint is what makes the second attempt better than the first."""
    stub = stub_client(invalid_output(), response(ANSWER))
    await _call(_wire(stub, settings, max_output_attempts=2))

    correction = stub.calls[1]["input"][-1]
    assert correction["role"] == "user"
    assert "score" in correction["content"]
    assert "between 1 and 10" in correction["content"]


async def test_the_original_input_survives_the_re_ask(
    settings: Settings, stub_client: Client, response: Response, invalid_output: Invalid
) -> None:
    stub = stub_client(invalid_output(), response(ANSWER))
    await _call(_wire(stub, settings, max_output_attempts=2))
    assert stub.calls[1]["input"][0] == {"role": "user", "content": "Synthetic finding."}


async def test_output_that_never_validates_gives_up_and_says_why(
    settings: Settings, stub_client: Client, invalid_output: Invalid
) -> None:
    stub = stub_client(invalid_output(), invalid_output(), invalid_output())
    with pytest.raises(OutputValidationError) as caught:
        await _call(_wire(stub, settings, max_output_attempts=3))

    assert caught.value.attempts == 3
    assert "score" in str(caught.value)
    assert len(stub.calls) == 3


async def test_a_single_attempt_does_not_re_ask(
    settings: Settings, stub_client: Client, invalid_output: Invalid
) -> None:
    """Retrying invalid output is a budget, and it can be set to no retries at all."""
    stub = stub_client(invalid_output())
    with pytest.raises(OutputValidationError):
        await _call(_wire(stub, settings, max_output_attempts=1))
    assert len(stub.calls) == 1


async def test_usage_is_recorded(
    settings: Settings,
    stub_client: Client,
    response: Response,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Someone has to be able to total up what a run cost."""
    usage = SimpleNamespace(
        input_tokens=1200,
        output_tokens=300,
        output_tokens_details=SimpleNamespace(reasoning_tokens=250),
    )
    stub = stub_client(response(ANSWER, usage=usage))
    with caplog.at_level(logging.DEBUG, logger="triage.llm.client"):
        await _call(_wire(stub, settings))

    assert "1200" in caplog.text
    assert "250" in caplog.text
