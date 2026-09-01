"""The shared annotated primitives, exercised directly.

``TypeAdapter`` lets these be tested without a model in the way, so a change to
one constraint fails here rather than in whichever model happens to use it.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from triage.models import (
    SCORE_RANGE,
    TICKET_TEXT_LIMIT,
    FindingId,
    NonEmptyStr,
    RegistryScore,
    TicketId,
    TicketText,
    TrimmedStr,
    YesNo,
)


def _validate(annotation: Any, value: Any) -> Any:
    return TypeAdapter(annotation).validate_python(value)


def test_non_empty_str_trims() -> None:
    assert _validate(NonEmptyStr, "  spaced  ") == "spaced"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_non_empty_str_rejects_blank(value: str) -> None:
    with pytest.raises(ValidationError):
        _validate(NonEmptyStr, value)


def test_trimmed_str_allows_empty() -> None:
    """``engineer_comment`` may legitimately be blank."""
    assert _validate(TrimmedStr, "   ") == ""


def test_ticket_text_accepts_up_to_the_limit() -> None:
    assert len(_validate(TicketText, "x" * TICKET_TEXT_LIMIT)) == TICKET_TEXT_LIMIT


def test_ticket_text_rejects_beyond_the_limit() -> None:
    with pytest.raises(ValidationError):
        _validate(TicketText, "x" * (TICKET_TEXT_LIMIT + 1))


def test_registry_score_coerces_csv_strings() -> None:
    assert _validate(RegistryScore, "7") == 7


@pytest.mark.parametrize("value", [SCORE_RANGE[0] - 1, SCORE_RANGE[1] + 1])
def test_registry_score_bounded(value: int) -> None:
    with pytest.raises(ValidationError):
        _validate(RegistryScore, value)


@pytest.mark.parametrize(
    ("annotation", "valid", "invalid"),
    [
        (FindingId, "F-1001", "1001"),
        (FindingId, "F-1001", "F-101"),
        (TicketId, "TKT-1001", "TKT-1001-A"),
    ],
)
def test_id_patterns(annotation: Any, valid: str, invalid: str) -> None:
    assert _validate(annotation, valid) == valid
    with pytest.raises(ValidationError):
        _validate(annotation, invalid)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("Yes", True), ("yes", True), ("  NO  ", False), ("No", False)],
)
def test_yes_no_coercion(value: str, expected: bool) -> None:
    assert _validate(YesNo, value) is expected


@pytest.mark.parametrize("value", ["Maybe", "", "unknown"])
def test_yes_no_rejects_anything_else(value: str) -> None:
    """A registry cell that is neither Yes nor No is a data problem, not a False."""
    with pytest.raises(ValidationError):
        _validate(YesNo, value)
