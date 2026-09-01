"""Shared field types and coercions used across the model groups.

Nothing here is a model. These are the annotated primitives the input, value
object and output modules build on, kept in one place so a constraint such as
the 300-character ticket limit is stated once.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, Field, StringConstraints

SCORE_RANGE = (1, 10)
"""Inclusive bounds shared by the registry priors and the ticket scores."""

TICKET_TEXT_LIMIT = 300
"""Character cap on ``summary`` and ``recommended_action``."""

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Trimmed text that must carry at least one character."""

TrimmedStr = Annotated[str, StringConstraints(strip_whitespace=True)]
"""Trimmed text that is allowed to be empty."""

TicketText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=TICKET_TEXT_LIMIT
    ),
]
"""Trimmed prose capped at the ticket character limit."""

RegistryScore = Annotated[int, Field(ge=SCORE_RANGE[0], le=SCORE_RANGE[1])]
"""A 1-10 score read from the registry CSV, never authored by a model.

Because it cannot come from a model, ``ge``/``le`` are sufficient here — see the
package docstring on why model-authored scores are handled differently.
"""

FindingId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^F-\d{4}$")]
"""``F-####``, as issued by the inspection system."""

TicketId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^TKT-\d{4}$")]
"""``TKT-####``, as issued by this system."""

_TRUTHY = frozenset({"yes", "y", "true", "1"})
_FALSY = frozenset({"no", "n", "false", "0"})


def _parse_yes_no(value: Any) -> Any:
    """Coerce the registry's ``Yes``/``No`` spelling to a bool."""
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in _TRUTHY:
            return True
        if token in _FALSY:
            return False
        raise ValueError(f"expected Yes or No, got {value!r}")
    return value


YesNo = Annotated[bool, BeforeValidator(_parse_yes_no)]
"""A registry ``Yes``/``No`` column read as a bool."""


__all__ = [
    "FindingId",
    "NonEmptyStr",
    "RegistryScore",
    "SCORE_RANGE",
    "TICKET_TEXT_LIMIT",
    "TicketId",
    "TicketText",
    "TrimmedStr",
    "YesNo",
]
