"""The entry point: argv in, an exit code and a ticket document out.

Nothing here opens a socket. The SDK client comes in through ``main``'s ``build``
seam, the same reason :class:`~triage.llm.TriageClient` takes its client rather
than making one, and every run happens in a working directory with no ``.env`` in
it so a developer's own key is never what a test runs against.

What is pinned is the entry point's own job and nothing below it: what ``argv``
selects, where the document lands, that a dry run sends nothing, and that a
failure comes out as one message and exit code 1 rather than a traceback. The
scores in the stubbed answers are arbitrary — no test asserts on one.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from triage.cli import main
from triage.models import ScoreBlock, TicketDocument, TicketTextBlock, UrgencyBlock

CsvRow = dict[str, str]
Client = Callable[..., Any]
Response = Callable[..., Any]
Row = Callable[..., CsvRow]
Csv = Callable[..., Path]

TRIAGE_VARS = (
    "TRIAGE_MODEL",
    "TRIAGE_WRITING_EFFORT",
    "TRIAGE_JUDGING_EFFORT",
    "TRIAGE_MAX_CONCURRENCY",
    "TRIAGE_REQUEST_TIMEOUT",
    "TRIAGE_MAX_RETRIES",
    "TRIAGE_MAX_OUTPUT_ATTEMPTS",
)

KEY = "test-key-not-a-real-one"


class ClosingStub:
    """A stand-in for ``AsyncOpenAI`` that the entry point can close.

    ``main`` closes the client it was handed whether the batch succeeded or not,
    which the shared stubs have no reason to support. Wrapping one rather than
    replacing it keeps the recorded calls readable, and ``closed`` makes the
    close itself something a test can assert on.
    """

    def __init__(self, inner: Any) -> None:
        self.responses = inner.responses
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.responses.calls


def _refuse(_settings: object) -> Any:
    """A factory for the runs that must never reach the network."""
    raise AssertionError("a client was built when none should have been")


def _answers(response: Response) -> Mapping[str, Any]:
    """One answer per pass, under the cache key that pass sends."""
    return {
        "triage-summary": response(TicketTextBlock(text="Synthetic summary.")),
        "triage-scoring_likelihood": response(
            ScoreBlock(score=4, rationale="Likelihood rationale.")
        ),
        "triage-scoring_impact": response(
            ScoreBlock(score=6, rationale="Impact rationale.")
        ),
        "triage-scoring_urgency": response(
            UrgencyBlock(score=6, rationale="Urgency rationale.", override=None)
        ),
        "triage-actions": response(TicketTextBlock(text="Replace the widget.")),
    }


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A run that reads no ``.env`` and inherits no tuning from the shell.

    ``LlmSettings`` resolves ``.env`` against the working directory, so moving
    into ``tmp_path`` is what makes the suite behave the same on a machine that
    has one and a machine that does not. It is also where the output lands.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    for name in TRIAGE_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def inputs(csv_file: Csv, finding_row: Row, equipment_row: Row) -> Callable[..., list[str]]:
    """The two positional arguments, written from synthetic rows."""

    def _make(
        findings: list[Mapping[str, str]] | None = None,
        equipment: list[Mapping[str, str]] | None = None,
    ) -> list[str]:
        findings_path = csv_file(
            [finding_row(**dict(o)) for o in (findings or [{}])], name="findings.csv"
        )
        registry_path = csv_file(
            [equipment_row(**dict(o)) for o in (equipment or [{}])], name="registry.csv"
        )
        return [str(findings_path), str(registry_path)]

    return _make


def _document(path: Path) -> TicketDocument:
    return TicketDocument.model_validate_json(path.read_text(encoding="utf-8"))


def test_a_dry_run_reports_the_batch_and_builds_no_client(
    inputs: Callable[..., list[str]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([*inputs(), "--dry-run"], build=_refuse)
    out = capsys.readouterr().out

    assert code == 0
    assert "1 finding(s) joined to 1 registry row(s); 1 to triage." in out
    assert "no requests sent" in out
    assert not (tmp_path / "tickets.json").exists()


def test_a_dry_run_never_prints_the_key(
    inputs: Callable[..., list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    main([*inputs(), "--dry-run"], build=_refuse)
    captured = capsys.readouterr()

    assert "API key: loaded" in captured.out
    assert KEY not in captured.out + captured.err


def test_a_dry_run_names_what_a_human_would_want_to_see_first(
    inputs: Callable[..., list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    """The registry's own facts, so the cost is committed to knowingly."""
    argv = inputs(
        equipment=[{"safety_critical_element": "Yes", "redundancy": "N+1 (XX-9999)"}]
    )
    main([*argv, "--dry-run"], build=_refuse)
    out = capsys.readouterr().out

    assert "safety critical element" in out
    assert "XX-9999" in out


def test_a_run_writes_one_ticket_per_finding(
    inputs: Callable[..., list[str]],
    keyed_client: Client,
    response: Response,
    tmp_path: Path,
) -> None:
    argv = inputs(
        findings=[
            {"finding_id": "F-9001", "equipment_id": "XX-0001"},
            {"finding_id": "F-9002", "equipment_id": "XX-0002"},
        ],
        equipment=[{"equipment_id": "XX-0001"}, {"equipment_id": "XX-0002"}],
    )
    stub = ClosingStub(keyed_client(_answers(response)))

    code = main(argv, build=lambda _settings: stub)

    document = _document(tmp_path / "tickets.json")
    assert code == 0
    assert document.tickets_generated == 2
    assert [ticket.finding_id for ticket in document.tickets] == ["F-9001", "F-9002"]
    assert [ticket.ticket_id for ticket in document.tickets] == ["TKT-9001", "TKT-9002"]
    assert stub.closed


def test_limit_caps_what_is_triaged(
    inputs: Callable[..., list[str]],
    keyed_client: Client,
    response: Response,
    tmp_path: Path,
) -> None:
    argv = inputs(
        findings=[
            {"finding_id": "F-9001", "equipment_id": "XX-0001"},
            {"finding_id": "F-9002", "equipment_id": "XX-0002"},
        ],
        equipment=[{"equipment_id": "XX-0001"}, {"equipment_id": "XX-0002"}],
    )
    stub = ClosingStub(keyed_client(_answers(response)))

    code = main([*argv, "--limit", "1"], build=lambda _settings: stub)

    document = _document(tmp_path / "tickets.json")
    assert code == 0
    assert [ticket.finding_id for ticket in document.tickets] == ["F-9001"]
    assert len(stub.calls) == 5


def test_a_limited_run_still_knows_the_whole_batch(
    inputs: Callable[..., list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    """The slice comes after the join, so the redundancy index stays whole."""
    argv = inputs(
        findings=[
            {"finding_id": "F-9001", "equipment_id": "XX-0001"},
            {"finding_id": "F-9002", "equipment_id": "XX-0002"},
        ],
        equipment=[
            {"equipment_id": "XX-0001", "redundancy": "Duplicated (XX-0002)"},
            {"equipment_id": "XX-0002", "redundancy": "Duplicated (XX-0001)"},
        ],
    )
    main([*argv, "--limit", "1", "--dry-run"], build=_refuse)
    out = capsys.readouterr().out

    assert "2 finding(s) joined to 2 registry row(s); 1 to triage." in out
    assert "partner(s) also with findings: XX-0002" in out


def test_the_document_can_go_to_stdout(
    inputs: Callable[..., list[str]],
    keyed_client: Client,
    response: Response,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub = ClosingStub(keyed_client(_answers(response)))

    code = main([*inputs(), "--out", "-"], build=lambda _settings: stub)
    out = capsys.readouterr().out

    assert code == 0
    assert TicketDocument.model_validate(json.loads(out)).tickets_generated == 1
    assert not (tmp_path / "tickets.json").exists()


def test_a_malformed_csv_reports_every_bad_line(
    inputs: Callable[..., list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    argv = inputs(
        findings=[{"finding_id": "not-an-id"}, {"reported_date": "the fifteenth"}]
    )

    code = main(argv, build=_refuse)
    err = capsys.readouterr().err

    assert code == 1
    assert "2 invalid row(s)" in err
    assert "line 2" in err
    assert "line 3" in err


def test_a_finding_with_no_registry_row_is_named(
    inputs: Callable[..., list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    argv = inputs(
        findings=[{"finding_id": "F-9001", "equipment_id": "XX-9999"}],
        equipment=[{"equipment_id": "XX-0001"}],
    )

    code = main(argv, build=_refuse)
    err = capsys.readouterr().err

    assert code == 1
    assert "F-9001" in err


def test_a_missing_csv_is_reported_without_a_traceback(
    inputs: Callable[..., list[str]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, registry = inputs()

    code = main([str(tmp_path / "absent.csv"), registry], build=_refuse)

    assert code == 1
    assert "absent.csv" in capsys.readouterr().err


def test_a_missing_key_points_at_the_template(
    monkeypatch: pytest.MonkeyPatch,
    inputs: Callable[..., list[str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY")

    code = main(inputs(), build=_refuse)
    err = capsys.readouterr().err

    assert code == 1
    assert "OPENAI_API_KEY" in err
    assert ".env.example" in err


def test_every_failed_finding_is_named(
    inputs: Callable[..., list[str]],
    keyed_client: Client,
    response: Response,
    invalid_output: Callable[[], Exception],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = inputs(
        findings=[
            {"finding_id": "F-9001", "equipment_id": "XX-0001"},
            {"finding_id": "F-9002", "equipment_id": "XX-0002"},
        ],
        equipment=[{"equipment_id": "XX-0001"}, {"equipment_id": "XX-0002"}],
    )
    answers = dict(_answers(response)) | {"triage-scoring_urgency": invalid_output()}
    stub = ClosingStub(keyed_client(answers))

    code = main(argv, build=lambda _settings: stub)
    err = capsys.readouterr().err

    assert code == 1
    assert "2 of 2 item(s) failed" in err
    assert "F-9001" in err
    assert "F-9002" in err
    assert not (tmp_path / "tickets.json").exists()
    assert stub.closed


def test_limit_must_be_at_least_one(inputs: Callable[..., list[str]]) -> None:
    with pytest.raises(SystemExit) as caught:
        main([*inputs(), "--limit", "0"], build=_refuse)

    assert caught.value.code == 2
