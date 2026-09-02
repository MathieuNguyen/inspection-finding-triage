"""The two primitives every pass is built on: one typed call, and a bounded batch.

:meth:`TriageClient.structured` is the only place in the project that talks to a
model. It goes through the Responses API with structured outputs, so the answer
arrives as a validated Pydantic model or not at all.

:func:`map_bounded` runs that call across a batch under a concurrency ceiling and
reports every failure together, the way :class:`triage.registry.CsvValidationError`
reports every bad row together. A run that fails tells you about all of it.

**Two retry budgets, deliberately separate.** Transport failures — 429s, 5xx,
dropped connections — are the SDK's ``max_retries`` with its own backoff, and
nothing here duplicates it. What this module retries is different: a response
that arrived intact and failed *our* validation. A strict structured-output
schema cannot express a numeric bound, so a score of 12 is well-formed JSON that
:class:`~triage.models.ScoreBlock` rejects. That is worth re-asking once, with
the validation errors quoted back. Folding the two budgets into one would
multiply them.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, cast

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from triage.llm.exceptions import (
    BatchError,
    EmptyResponseError,
    IncompleteResponseError,
    ItemFailure,
    OutputValidationError,
    RefusalError,
)
from triage.llm.settings import Effort, LlmSettings

logger = logging.getLogger(__name__)


def build_client(settings: LlmSettings) -> AsyncOpenAI:
    """The configured SDK client.

    ``max_retries`` and ``timeout`` are handed over here so retry and backoff
    stay the SDK's job.
    """
    return AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
    )


def _refusal(response: Any) -> str | None:
    """The refusal text, if the model declined."""
    for item in response.output:
        if getattr(item, "type", None) != "message":
            continue
        for part in item.content:
            if getattr(part, "type", None) == "refusal":
                return part.refusal
    return None


class TriageClient:
    """A model, its settings, and the one call the rest of the project makes.

    The SDK client is injected rather than constructed here, which is what makes
    the layer testable: a test passes an object exposing ``responses.parse`` and
    no network is involved. Use :func:`build_client` to make the real one.

    This is the only plain class in the layer. It holds a live ``AsyncOpenAI``,
    which is not a validatable type; everything that carries data is a model.
    """

    def __init__(self, client: AsyncOpenAI, settings: LlmSettings) -> None:
        self.client = client
        self.settings = settings

    async def structured[T: BaseModel](
        self,
        *,
        instructions: str,
        user_input: str,
        text_format: type[T],
        effort: Effort,
        cache_key: str | None = None,
    ) -> T:
        """One structured-output call, returned as a validated model.

        ``instructions`` is the system-level text — the prompt with its policies
        already composed. ``user_input`` is the finding under assessment.

        ``cache_key`` is worth passing whenever a batch shares its instructions:
        the policy text is byte-identical across every finding in a run, and a
        stable key lets the provider cache it instead of re-reading it each time.

        Raises :class:`OutputValidationError` once the attempts are spent, and
        :class:`RefusalError`, :class:`IncompleteResponseError` or
        :class:`EmptyResponseError` for a response that cannot be used at all.
        """
        level = self.settings.effort_for(effort)
        conversation: list[dict[str, str]] = [{"role": "user", "content": user_input}]
        last_error: ValidationError | None = None

        for attempt in range(1, self.settings.max_output_attempts + 1):
            logger.info(
                "Requesting %s from %s at %s effort (attempt %d of %d)",
                text_format.__name__,
                self.settings.model,
                level,
                attempt,
                self.settings.max_output_attempts,
            )
            try:
                response = await self.client.responses.parse(
                    model=self.settings.model,
                    instructions=instructions,
                    input=cast(Any, conversation),
                    text_format=text_format,
                    reasoning={"effort": level},
                    prompt_cache_key=cache_key,
                    store=False,
                )
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "Attempt %d produced output that failed validation: %s",
                    attempt,
                    exc.error_count(),
                )
                conversation.append(
                    {"role": "user", "content": _correction(exc)}
                )
                continue

            _log_usage(response)

            if getattr(response, "status", None) == "incomplete":
                details = getattr(response, "incomplete_details", None)
                raise IncompleteResponseError(getattr(details, "reason", None))
            if refusal := _refusal(response):
                raise RefusalError(refusal)

            parsed = response.output_parsed
            if parsed is None:
                raise EmptyResponseError(
                    f"no {text_format.__name__} in the response output"
                )
            return parsed

        if last_error is None:  # pragma: no cover - the loop only exits via a retry
            raise EmptyResponseError("the request loop ended without an answer")
        raise OutputValidationError(self.settings.max_output_attempts, last_error)


def _correction(error: ValidationError) -> str:
    """The re-ask.

    ``parse`` raises before the response object reaches us, so the offending
    output cannot be quoted back — only what was wrong with it.

    Which is why this asks for the answer again in full rather than for an edit.
    The model cannot see the text it would be editing, so "change only what was
    wrong" is an instruction it has no way to follow; for a length overrun,
    the one failure where the previous wording matters most, it is worse than
    saying nothing.
    """
    problems = "\n".join(
        f"- {'.'.join(str(part) for part in err['loc']) or '<root>'}: {err['msg']}"
        for err in error.errors()
    )
    return (
        "Your previous answer was rejected by the output schema:\n"
        f"{problems}\n"
        "Your previous answer is not shown back to you. Write the answer again "
        "in full, satisfying every constraint."
    )


def _log_usage(response: Any) -> None:
    """Record what the call cost, for anyone totting up a run."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    details = getattr(usage, "output_tokens_details", None)
    logger.debug(
        "Usage: %s input, %s output (%s reasoning)",
        getattr(usage, "input_tokens", "?"),
        getattr(usage, "output_tokens", "?"),
        getattr(details, "reasoning_tokens", "?"),
    )


async def gather_bounded[I, O](
    items: Sequence[I],
    call: Callable[[I], Awaitable[O]],
    *,
    limit: int,
    key: Callable[[I], str],
) -> tuple[list[O], list[ItemFailure]]:
    """Run ``call`` over every item at most ``limit`` at a time, keeping both.

    Every item runs to completion whatever the others do, and what came back is
    handed over in two lists rather than reduced to one outcome: the results in
    input order, and every failure named by its key.

    That the successes survive a partial batch is the whole point of this
    function existing beside :func:`map_bounded`. The calls have already been
    made and paid for by the time a sibling fails, and a caller that would
    rather keep them than be told the run was not clean should be able to.

    ``key`` turns an item into the name it is reported under; for an enriched
    finding that is its ``finding_id``.
    """
    semaphore = asyncio.Semaphore(limit)

    async def guarded(item: I) -> O:
        async with semaphore:
            return await call(item)

    outcomes = await asyncio.gather(
        *(guarded(item) for item in items), return_exceptions=True
    )

    results: list[O] = []
    failures: list[ItemFailure] = []
    for item, outcome in zip(items, outcomes, strict=True):
        if isinstance(outcome, Exception):
            failures.append(ItemFailure(key(item), outcome))
        elif isinstance(outcome, BaseException):
            # Cancellation is not this function's to swallow.
            raise outcome
        else:
            results.append(cast("O", outcome))
    return results, failures


async def map_bounded[I, O](
    items: Sequence[I],
    call: Callable[[I], Awaitable[O]],
    *,
    limit: int,
    key: Callable[[I], str],
) -> list[O]:
    """Run ``call`` over every item, at most ``limit`` at a time.

    All or nothing. Results come back in input order, and if anything failed,
    every failure is reported together in one :class:`BatchError` naming the
    item it belongs to — the same contract as a malformed CSV, so a broken run
    is diagnosed in one pass rather than one finding at a time.

    Use this where a partial answer would be worse than none.
    :func:`gather_bounded` is the one to reach for otherwise; this is a thin
    reduction over it.
    """
    results, failures = await gather_bounded(items, call, limit=limit, key=key)
    if failures:
        raise BatchError(failures, len(items))
    return results


__all__ = ["TriageClient", "build_client", "gather_bounded", "map_bounded"]
