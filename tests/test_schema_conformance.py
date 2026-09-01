"""The supplied files, checked against the models for structure only.

Nothing here asserts on the content of a row or on the example ticket's scores:
these files are sample inputs and a structural reference, not fixtures.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from triage.models import INSPECTION_TYPES, Equipment, Finding, RedundancyKind, Ticket
from triage.registry import join, load_findings, load_registry


def test_every_findings_row_validates(repo_root: Path) -> None:
    with (repo_root / "data" / "inspection_findings.csv").open(newline="") as handle:
        rows = [Finding(**row) for row in csv.DictReader(handle)]
    assert rows


def test_supplied_findings_stay_inside_the_inspection_type_vocabulary(
    repo_root: Path,
) -> None:
    """Guards the closed vocabulary against a drifting input file."""
    with (repo_root / "data" / "inspection_findings.csv").open(newline="") as handle:
        used = {row["inspection_type"] for row in csv.DictReader(handle)}
    assert used <= set(INSPECTION_TYPES)


def test_every_registry_row_validates(repo_root: Path) -> None:
    with (repo_root / "data" / "equipment_registry.csv").open(newline="") as handle:
        rows = [Equipment(**row) for row in csv.DictReader(handle)]
    assert rows
    assert all(e.redundancy.kind is not RedundancyKind.UNRECOGNISED for e in rows)


def test_example_ticket_validates_against_the_model(repo_root: Path) -> None:
    """The example defines the output structure; only its shape is asserted."""
    payload = json.loads((repo_root / "reference" / "example_ticket.json").read_text())
    assert Ticket.model_validate(payload).model_dump(mode="json") == payload


def test_the_supplied_files_load_and_join(repo_root: Path) -> None:
    """Structure only: every finding resolves to a registry row."""
    findings = load_findings(repo_root / "data" / "inspection_findings.csv")
    registry = load_registry(repo_root / "data" / "equipment_registry.csv")
    enriched = join(findings, registry)
    assert len(enriched) == len(findings)
