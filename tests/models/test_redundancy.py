"""Parsing of the registry's free-text ``redundancy`` column."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from triage.models import Redundancy, RedundancyField, RedundancyKind


@pytest.mark.parametrize(
    ("raw", "kind", "partners"),
    [
        ("None", RedundancyKind.NONE, ()),
        ("", RedundancyKind.NONE, ()),
        ("N+1 (TAG-0001)", RedundancyKind.N_PLUS_1, ("TAG-0001",)),
        ("Duplicated (TAG-0002)", RedundancyKind.DUPLICATED, ("TAG-0002",)),
        ("Duplicated (TAG-A, TAG-B)", RedundancyKind.DUPLICATED, ("TAG-A", "TAG-B")),
        ("Voted 2oo3", RedundancyKind.VOTED, ()),
        ("Yes (bypass available)", RedundancyKind.BYPASS, ()),
    ],
)
def test_grammar(raw: str, kind: RedundancyKind, partners: tuple[str, ...]) -> None:
    parsed = Redundancy.parse(raw)
    assert parsed.kind is kind
    assert parsed.partner_equipment_ids == partners
    assert parsed.raw == raw.strip()


def test_voted_arrangement_keeps_k_and_n() -> None:
    parsed = Redundancy.parse("Voted 2oo3")
    assert (parsed.voting_k, parsed.voting_n) == (2, 3)


def test_unfamiliar_arrangement_degrades_to_raw_text() -> None:
    """An unseen arrangement must not fail the run."""
    parsed = Redundancy.parse("Three units, one standby offshore")
    assert parsed.kind is RedundancyKind.UNRECOGNISED
    assert parsed.raw == "Three units, one standby offshore"
    assert parsed.is_claimed is False


def test_is_claimed_flags_arrangements_only() -> None:
    assert Redundancy.parse("N+1 (TAG-0001)").is_claimed is True
    assert Redundancy.parse("None").is_claimed is False


def test_impossible_voting_arrangement_rejected() -> None:
    with pytest.raises(ValidationError):
        Redundancy(kind=RedundancyKind.VOTED, raw="Voted 4oo3", voting_k=4, voting_n=3)


def test_field_coerces_a_raw_cell() -> None:
    parsed = TypeAdapter(RedundancyField).validate_python("Voted 2oo3")
    assert parsed.kind is RedundancyKind.VOTED
