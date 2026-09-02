"""Entry point: two CSVs in, one ticket document out.

Everything this module does, some other module already knows how to do.
:mod:`triage.registry` loads and joins, :mod:`triage.triage` runs the passes,
:class:`~triage.llm.LlmSettings` resolves the run configuration. What is left is
the part nobody else can own: reading argv, deciding where the output goes, and
turning an exception into a line on stderr and a non-zero exit.

**The CLI composes; it does not decide.** No scoring rule, no default that
depends on the sample data in ``data/`` — the two CSV paths are required
arguments, because those files are two inputs the system can be run against and
not the system's subject.

``--dry-run`` exists for the run before the first real one. It resolves the
settings, loads both files and joins them, reports what it would triage, and
returns without building a client, so the wiring — the ``.env``, the CSVs, the
registry join — is proven at no cost. ``--limit`` bounds what a real run spends:
a finding costs five model calls, so a full batch is not the right thing to
discover a typo with.

Failures are reported the way the layers below report them: one message naming
everything that went wrong, not a traceback and not the first problem only.

A finding that fails is not one of those. It does not stop the run: the document
is written with the tickets that came through and the failures recorded beside
them, and the exit code — 1 rather than 0 — is what says the run was not clean.
Only the failures that make a run impossible at all, a malformed CSV or a
missing key, end it before anything is written.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from openai import AsyncOpenAI
from pydantic import ValidationError

from triage.llm import (
    BatchError,
    LlmError,
    LlmSettings,
    PolicyError,
    PromptError,
    TriageClient,
    build_client,
)
from triage.models import TicketDocument
from triage.registry import (
    CsvValidationError,
    EnrichedFinding,
    RegistryJoinError,
    join,
    load_findings,
    load_registry,
)
from triage.triage import triage_batch

ClientFactory = Callable[[LlmSettings], AsyncOpenAI]
"""How the SDK client is obtained.

Injected for the same reason :class:`~triage.llm.TriageClient` takes its client
rather than building one: it is the seam that lets the entry point be tested
without a socket.
"""

DEFAULT_OUT = "tickets.json"
STDOUT = "-"

_CONFIG_HINT = "Copy .env.example to .env and set OPENAI_API_KEY."
_LEVELS = (logging.WARNING, logging.INFO, logging.DEBUG)


class ConfigError(ValueError):
    """The run configuration is unusable."""


def _positive(value: str) -> int:
    """An ``int`` of at least one, for ``--limit``."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return number


def build_parser() -> argparse.ArgumentParser:
    """The command line."""
    parser = argparse.ArgumentParser(
        prog="triage",
        description=(
            "Triage offshore inspection findings into structured tickets: "
            "likelihood, impact and urgency with a rationale each, a summary, "
            "a recommended action, and a human-review flag."
        ),
    )
    parser.add_argument(
        "findings_csv", type=Path, help="the inspection findings to triage"
    )
    parser.add_argument(
        "registry_csv", type=Path, help="the equipment registry to enrich them with"
    )
    parser.add_argument(
        "-o",
        "--out",
        default=DEFAULT_OUT,
        metavar="PATH",
        help=f"where the ticket document is written; {STDOUT!r} for stdout "
        f"(default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--limit",
        type=_positive,
        metavar="N",
        help="triage only the first N findings, at five model calls each",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="load, join and report what would be triaged; send no requests",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="log each request (-v) or add token usage (-vv)",
    )
    return parser


def _configure_logging(verbosity: int) -> None:
    """Send the package's log records to stderr.

    Called from :func:`main` rather than at import, so importing this module
    leaves the root logger alone and the suites that assert on records through
    ``caplog`` see what they configured.

    ``force`` because this is the top of a process: whatever ``-v`` asked for is
    what the run should do, and a ``basicConfig`` that quietly does nothing
    because a handler already exists is a flag that silently fails.
    """
    logging.basicConfig(
        level=_LEVELS[min(verbosity, len(_LEVELS) - 1)],
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


def load_settings() -> LlmSettings:
    """Run configuration, with an incomplete one explained rather than dumped.

    Only the field names are reported. The API key is a ``SecretStr`` so that it
    stays out of reprs and log lines, and an error path is no place to undo that.
    """
    try:
        return LlmSettings()
    except ValidationError as error:
        fields = ", ".join(
            ".".join(str(part) for part in err["loc"]) or "<settings>"
            for err in error.errors()
        )
        raise ConfigError(
            f"run configuration is incomplete ({fields}). {_CONFIG_HINT}"
        ) from error


def _finding_line(item: EnrichedFinding) -> str:
    """One dry-run line: the finding, its equipment, and what to know about it.

    The notes are facts :mod:`triage.registry` already reports. What any of them
    means for a score is the policies' business, not this module's.
    """
    notes: list[str] = []
    if item.partners_with_findings:
        notes.append(
            f"partner(s) also with findings: {', '.join(item.partners_with_findings)}"
        )
    if item.unresolved_partners:
        notes.append(
            f"partner(s) not in registry: {', '.join(item.unresolved_partners)}"
        )
    if item.equipment.safety_critical_element:
        notes.append("safety critical element")
    trailer = f"  — {'; '.join(notes)}" if notes else ""
    return f"  {item.finding.finding_id}  {item.equipment.equipment_id}{trailer}"


def dry_run_report(
    settings: LlmSettings,
    findings: int,
    registry: int,
    items: Sequence[EnrichedFinding],
    stream: TextIO,
) -> None:
    """What a real run would do, and what it would be handed."""
    print(
        f"{findings} finding(s) joined to {registry} registry row(s); "
        f"{len(items)} to triage.",
        file=stream,
    )
    print(
        f"model={settings.model}  concurrency={settings.max_concurrency}  "
        f"effort writing={settings.writing_effort} judging={settings.judging_effort}",
        file=stream,
    )
    print("API key: loaded (not shown)", file=stream)
    for item in items:
        print(_finding_line(item), file=stream)
    print(f"Dry run: no requests sent. A real run is {len(items) * 5} call(s).", file=stream)


async def _triage(
    settings: LlmSettings, items: Sequence[EnrichedFinding], build: ClientFactory
) -> TicketDocument:
    """One batch, against a client closed whether or not it succeeded."""
    sdk = build(settings)
    try:
        return await triage_batch(TriageClient(sdk, settings), items)
    finally:
        await sdk.close()


def _write(document: TicketDocument, out: str) -> None:
    """Serialise the document, to a file or to stdout.

    The confirmation goes to stderr so that ``--out -`` can be piped.
    """
    payload = document.model_dump_json(indent=2)
    if out == STDOUT:
        print(payload)
        return
    path = Path(out)
    path.write_text(f"{payload}\n", encoding="utf-8")
    print(
        f"Wrote {document.tickets_generated} ticket(s) to {path}.", file=sys.stderr
    )


def _report_failures(document: TicketDocument) -> None:
    """Name every finding that produced no ticket.

    The document already records these, so this is the courtesy of not making
    someone open the file to find out the run was not clean.
    """
    if not document.failures:
        return
    total = document.tickets_generated + document.findings_failed
    print(
        f"{document.findings_failed} of {total} finding(s) produced no ticket:",
        file=sys.stderr,
    )
    for failure in document.failures:
        print(
            f"  {failure.finding_id}: {failure.error}: {failure.detail}",
            file=sys.stderr,
        )


def _run(args: argparse.Namespace, build: ClientFactory) -> int:
    """The pipeline, top to bottom."""
    settings = load_settings()
    findings = load_findings(args.findings_csv)
    registry = load_registry(args.registry_csv)
    items = join(findings, registry)

    # Sliced after the join, not before it: the redundancy index is built from
    # the whole file, so a limited run still knows which of a finding's partners
    # carry findings of their own.
    selected = items if args.limit is None else items[: args.limit]

    if args.dry_run:
        dry_run_report(settings, len(findings), len(registry), selected, sys.stdout)
        return 0

    # Written whether or not every finding came through. A partial document is
    # worth more than none: the calls behind it have been paid for, and it says
    # which findings to look at again. The exit code is what reports that the
    # run was not clean.
    document = asyncio.run(_triage(settings, selected, build))
    _write(document, args.out)
    _report_failures(document)
    return 1 if document.failures else 0


def main(
    argv: Sequence[str] | None = None, *, build: ClientFactory = build_client
) -> int:
    """Run the triage pipeline and return the process exit code.

    Every exception listed here already carries a complete message — every bad
    CSV line, every finding that failed — so it is printed rather than reworded.
    ``PolicyError`` and ``PromptError`` are ``ValueError``, not ``LlmError``, and
    have to be named separately or a missing policy file would come out as a
    traceback.
    """
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    try:
        return _run(args, build)
    except (
        BatchError,
        ConfigError,
        CsvValidationError,
        LlmError,
        OSError,
        PolicyError,
        PromptError,
        RegistryJoinError,
    ) as error:
        print(f"triage: {error}", file=sys.stderr)
        return 1


__all__ = [
    "ClientFactory",
    "ConfigError",
    "build_parser",
    "dry_run_report",
    "load_settings",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
