"""Value objects: structure recovered from free-text registry columns.

The registry's ``redundancy`` column is free text with a real grammar. Parsing it
once, here, means later passes reason over an arrangement rather than re-reading
a string.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


class RedundancyKind(StrEnum):
    """The arrangements the registry's ``redundancy`` column expresses."""

    NONE = "none"
    N_PLUS_1 = "n_plus_1"
    DUPLICATED = "duplicated"
    VOTED = "voted"
    BYPASS = "bypass"
    UNRECOGNISED = "unrecognised"


_VOTED_RE = re.compile(r"^voted\s*(?P<k>\d+)\s*oo\s*(?P<n>\d+)$", re.IGNORECASE)
_TAGGED_RE = re.compile(
    r"^(?P<kind>n\s*\+\s*1|duplicated)\s*\((?P<tags>[^)]*)\)$", re.IGNORECASE
)
_BYPASS_RE = re.compile(r"^yes\s*\(\s*bypass\b[^)]*\)$", re.IGNORECASE)
_ABSENT = frozenset({"", "none", "no", "n/a", "na", "-"})
_TAG_SEPARATORS = re.compile(r"[,;/]|\s+and\s+", re.IGNORECASE)


class Redundancy(BaseModel):
    """A parsed ``redundancy`` cell.

    Parsing is deliberately generic: the tag inside ``N+1 (TAG)`` is whatever the
    cell contains, so a partner never has to be known ahead of time. Anything the
    grammar does not cover becomes :attr:`RedundancyKind.UNRECOGNISED` while
    keeping :attr:`raw` intact, so an unfamiliar cell degrades to free text that
    can still be shown to the model rather than failing the run.

    The named partners matter downstream: whether a redundant leg is actually
    healthy is a question about other findings in the batch, not something this
    cell can answer.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: RedundancyKind
    raw: str = Field(description="The registry cell exactly as written.")
    partner_equipment_ids: tuple[str, ...] = ()
    voting_k: int | None = Field(default=None, description="k in a k-oo-n arrangement.")
    voting_n: int | None = Field(default=None, description="n in a k-oo-n arrangement.")

    @model_validator(mode="after")
    def _check_voting(self) -> Self:
        if (self.voting_k is None) != (self.voting_n is None):
            raise ValueError("voting_k and voting_n must be set together")
        if self.voting_k is not None and self.voting_n is not None:
            if not 1 <= self.voting_k <= self.voting_n:
                raise ValueError(
                    f"invalid voting arrangement {self.voting_k}oo{self.voting_n}"
                )
        return self

    @classmethod
    def parse(cls, raw: str) -> Self:
        """Build a :class:`Redundancy` from a registry cell."""
        text = (raw or "").strip()
        if text.casefold() in _ABSENT:
            return cls(kind=RedundancyKind.NONE, raw=text)
        if match := _VOTED_RE.match(text):
            return cls(
                kind=RedundancyKind.VOTED,
                raw=text,
                voting_k=int(match["k"]),
                voting_n=int(match["n"]),
            )
        if match := _TAGGED_RE.match(text):
            kind = (
                RedundancyKind.N_PLUS_1
                if match["kind"].casefold().startswith("n")
                else RedundancyKind.DUPLICATED
            )
            tags = tuple(
                tag.strip()
                for tag in _TAG_SEPARATORS.split(match["tags"])
                if tag.strip()
            )
            return cls(kind=kind, raw=text, partner_equipment_ids=tags)
        if _BYPASS_RE.match(text):
            return cls(kind=RedundancyKind.BYPASS, raw=text)
        return cls(kind=RedundancyKind.UNRECOGNISED, raw=text)

    @property
    def is_claimed(self) -> bool:
        """Whether the cell claims any redundancy at all.

        A claim, not a verified fact: confirming it is the triage pass's job.
        """
        return self.kind not in (RedundancyKind.NONE, RedundancyKind.UNRECOGNISED)

    def __str__(self) -> str:
        return self.raw or "None"


def _coerce_redundancy(value: Any) -> Any:
    return Redundancy.parse(value) if isinstance(value, str) else value


RedundancyField = Annotated[Redundancy, BeforeValidator(_coerce_redundancy)]
"""A :class:`Redundancy` that accepts the raw registry cell on the way in."""


__all__ = ["Redundancy", "RedundancyField", "RedundancyKind"]
