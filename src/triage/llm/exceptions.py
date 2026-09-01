"""Failures the LLM layer raises.

Two ideas carry over from :mod:`triage.registry`. A batch reports every failure
together rather than dying on the first, so one run tells you everything that is
wrong. And an exception keeps the structured detail alongside its message, so a
caller can act on it without parsing prose.

The name is ``exceptions``, not ``errors``, because ``policies/errors.md`` is a
different thing entirely: the recurring *assessment* errors the triage notes warn
about. Nothing in this module is about those.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pydantic import ValidationError


class LlmError(RuntimeError):
    """Base for anything that goes wrong talking to the model."""


class EmptyResponseError(LlmError):
    """The call succeeded but carried no parsed output."""


class RefusalError(LlmError):
    """The model declined to answer.

    Carries the refusal text, which usually names what it objected to.
    """

    def __init__(self, refusal: str) -> None:
        self.refusal = refusal
        super().__init__(f"the model refused to answer: {refusal}")


class IncompleteResponseError(LlmError):
    """Generation stopped early, most often at the output token ceiling."""

    def __init__(self, reason: str | None) -> None:
        self.reason = reason
        super().__init__(f"the response is incomplete: {reason or 'no reason given'}")


class OutputValidationError(LlmError):
    """Every attempt produced output the models rejected.

    A structured-output schema cannot express a numeric bound, so a score outside
    1-10 arrives as a well-formed response that fails validation. That is what
    the retry exists for; this is raised once the attempts are spent.
    """

    def __init__(self, attempts: int, error: ValidationError) -> None:
        self.attempts = attempts
        self.error = error
        detail = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']) or '<root>'}: {err['msg']}"
            for err in error.errors()
        )
        super().__init__(
            f"output still invalid after {attempts} attempt(s): {detail}"
        )


class ItemFailure(NamedTuple):
    """One item of a batch that failed, with the key naming it.

    The counterpart of :class:`triage.registry.RowError`, which pairs a bad CSV
    row with its line number.
    """

    key: str
    error: Exception

    def __str__(self) -> str:
        return f"{self.key}: {type(self.error).__name__}: {self.error}"


class BatchError(LlmError):
    """Every failed item in one batch, reported together.

    Collecting rather than failing on the first one means a broken run is
    diagnosed in a single pass, the way a malformed CSV is.
    """

    def __init__(self, failures: Sequence[ItemFailure], total: int) -> None:
        self.failures = tuple(failures)
        self.total = total
        listing = "\n  ".join(str(failure) for failure in self.failures)
        super().__init__(
            f"{len(self.failures)} of {total} item(s) failed:\n  {listing}"
        )


class PolicyError(ValueError):
    """A policy file is missing or cannot be read."""


class PromptError(ValueError):
    """A prompt is missing, or its placeholders and its spec disagree."""


__all__ = [
    "BatchError",
    "EmptyResponseError",
    "IncompleteResponseError",
    "ItemFailure",
    "LlmError",
    "OutputValidationError",
    "PolicyError",
    "PromptError",
    "RefusalError",
]
