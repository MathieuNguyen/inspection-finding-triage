"""Fixtures shared by the whole suite.

Two kinds of scaffolding live here, both because more than one directory needs
them. The CSV row factories are used by the model tests, the registry tests and
the triage tests; the LLM doubles are used by the LLM tests and the triage tests.
Every fixture returns a callable so a test can override just the field it cares
about, and every value is synthetic: nothing is copied from ``data/``.

There is no mocking library. The stubs are hand-written for the same reason the
rest of the suite avoids mocks: what the client sends is part of the contract, so
a test should be able to read it back and assert on it.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from triage.llm import LlmSettings
from triage.models import (
    TICKET_TEXT_LIMIT,
    Equipment,
    Finding,
    ScoreBlock,
    TicketTextBlock,
)
from triage.registry import EnrichedFinding, join

CsvRow = dict[str, str]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository root, for tests that read the supplied files."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def finding_row() -> Callable[..., CsvRow]:
    """A well-formed ``inspection_findings.csv`` row, as strings."""

    def _make(**overrides: str) -> CsvRow:
        row: CsvRow = {
            "finding_id": "F-9001",
            "reported_date": "2026-01-15",
            "equipment_id": "XX-0001",
            "equipment_type": "Widget",
            "inspection_type": "Routine Operator Round",
            "inspection_method": "Visual",
            "finding_description": "Synthetic description used only for schema tests.",
            "reported_by": "A. Tester",
            "reporter_role": "Test Engineer",
        }
        return row | overrides

    return _make


@pytest.fixture
def equipment_row() -> Callable[..., CsvRow]:
    """A well-formed ``equipment_registry.csv`` row, as strings."""

    def _make(**overrides: str) -> CsvRow:
        row: CsvRow = {
            "equipment_id": "XX-0001",
            "equipment_type": "Widget",
            "service_description": "Synthetic item",
            "criticality_score": "6",
            "reliability_score": "7",
            "safety_critical_element": "No",
            "redundancy": "None",
            "engineer_comment": "",
        }
        return row | overrides

    return _make


@pytest.fixture
def csv_file(tmp_path: Path) -> Callable[..., Path]:
    """Write rows to a throwaway CSV and return its path.

    ``header`` defaults to the keys of the first row; pass it explicitly to
    write a file whose header is wrong or incomplete.
    """

    def _make(
        rows: Sequence[CsvRow],
        *,
        name: str = "rows.csv",
        header: Sequence[str] | None = None,
        encoding: str = "utf-8",
    ) -> Path:
        fields = list(header) if header is not None else list(rows[0])
        path = tmp_path / name
        with path.open("w", newline="", encoding=encoding) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return path

    return _make


@pytest.fixture
def enriched(
    finding_row: Callable[..., CsvRow], equipment_row: Callable[..., CsvRow]
) -> Callable[..., list[EnrichedFinding]]:
    """Enriched findings, built from synthetic rows through the real join.

    Each argument is a sequence of override dicts, one per row. The defaults are
    a single finding against a single registry item, which share an
    ``equipment_id``; a test that needs a redundant pair passes two of each.
    Going through :func:`triage.registry.join` rather than constructing
    :class:`~triage.registry.EnrichedFinding` directly means the partner tuples
    are worked out the way a run works them out.
    """

    def _make(
        findings: Sequence[Mapping[str, str]] = ({},),
        equipment: Sequence[Mapping[str, str]] = ({},),
    ) -> list[EnrichedFinding]:
        return join(
            [Finding.model_validate(finding_row(**dict(o))) for o in findings],
            [Equipment.model_validate(equipment_row(**dict(o))) for o in equipment],
        )

    return _make


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


def too_long() -> ValidationError:
    """The other failure the output retry exists for: prose over the cap.

    The one actually seen in a run — a model that writes a good summary and
    writes too much of it. Built the same way as :func:`out_of_range`, from the
    model rather than by hand.
    """
    try:
        TicketTextBlock(text="x" * (TICKET_TEXT_LIMIT + 17))
    except ValidationError as exc:
        return exc
    raise AssertionError("TicketTextBlock accepted an overlong text")


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


class KeyedStubResponses:
    """Answers by ``prompt_cache_key`` rather than by call order."""

    def __init__(self, outcomes: Mapping[str, Any]) -> None:
        self._outcomes = dict(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        key = kwargs.get("prompt_cache_key")
        if key not in self._outcomes:
            raise AssertionError(f"the stub has no outcome for cache key {key!r}")
        outcome = self._outcomes[key]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class KeyedStubClient:
    """Stands in for ``AsyncOpenAI`` when several passes are in flight at once.

    :class:`StubClient` hands out its outcomes in call order, which is right for
    one call and unusable for three that go out together: which of them reaches
    the stub first is a scheduling detail, not part of the contract. Keying on
    the cache key lets a multi-pass test say what each pass answers instead.

    An outcome is reused for every call under its key, so a
    :class:`~pydantic.ValidationError` here exercises the output retry to
    exhaustion.
    """

    def __init__(self, outcomes: Mapping[str, Any]) -> None:
        self.responses = KeyedStubResponses(outcomes)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.responses.calls

    def calls_for(self, cache_key: str) -> list[dict[str, Any]]:
        """Every request sent under one cache key, in the order it was sent."""
        return [call for call in self.calls if call.get("prompt_cache_key") == cache_key]


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
def keyed_client() -> Callable[..., KeyedStubClient]:
    """A stand-in for ``AsyncOpenAI``, given one outcome per cache key."""
    return KeyedStubClient


@pytest.fixture
def invalid_output() -> Callable[[], ValidationError]:
    """The failure the output retry exists for: a score outside 1-10."""
    return out_of_range


@pytest.fixture
def overlong_output() -> Callable[[], ValidationError]:
    """The same retry, driven by ticket prose over the character cap."""
    return too_long
