"""Load the two read-only CSVs, validate every row, and join findings to equipment.

Three concerns, in the order the data moves:

* **Load** — :func:`load_findings` and :func:`load_registry` turn a CSV into
  validated models. A malformed file is reported once, naming every bad line,
  rather than one exception per run.
* **Index** — :func:`index_registry` keys the registry by ``equipment_id`` and
  refuses a duplicate, which would silently drop an item from the join.
* **Join** — :func:`join` attaches each finding's registry row and records which
  of its named redundancy partners also carry a finding in this batch.

That last part is why the join exists at batch scope rather than per row: the
registry's ``redundancy`` cell is a claim about an arrangement, and whether the
partner leg is healthy is a question about the rest of the batch.

Nothing here interprets what it finds. ``partners_with_findings`` is a fact;
what it does to a score is the triage pass's decision.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, ValidationError

from triage.models import Equipment, Finding

logger = logging.getLogger(__name__)


class RowError(NamedTuple):
    """One row that failed validation, with the line it sits on."""

    line: int
    error: ValidationError

    def __str__(self) -> str:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']) or '<row>'}: {err['msg']}"
            for err in self.error.errors()
        )
        return f"line {self.line}: {detail}"


class CsvValidationError(ValueError):
    """Every invalid row in one file, reported together.

    Collecting rather than failing on the first one means a broken CSV is fixed
    in a single pass.
    """

    def __init__(self, path: Path, errors: Sequence[RowError]) -> None:
        self.path = path
        self.errors = tuple(errors)
        listing = "\n  ".join(str(row) for row in self.errors)
        super().__init__(
            f"{len(self.errors)} invalid row(s) in {path}:\n  {listing}"
        )


class RegistryJoinError(ValueError):
    """A finding could not be matched to a registry row."""


def _rows(path: Path) -> Iterator[tuple[int, dict[str, str | None]]]:
    """Yield ``(line, row)`` pairs from a CSV.

    ``utf-8-sig`` drops a byte-order mark if the file was written by a
    spreadsheet, and ``reader.line_num`` is the physical line, so the number in
    an error message matches what the reader sees on opening the file even when
    a quoted ``finding_description`` spans several lines.
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield reader.line_num, row


def _load[M: BaseModel](path: Path, model: type[M]) -> list[M]:
    """Validate every row of ``path`` into ``model``, reporting all failures."""
    loaded: list[M] = []
    failures: list[RowError] = []
    for line, row in _rows(path):
        try:
            loaded.append(model.model_validate(row))
        except ValidationError as error:
            failures.append(RowError(line, error))
    if failures:
        raise CsvValidationError(path, failures)
    return loaded


def load_findings(path: Path) -> list[Finding]:
    """Read ``inspection_findings.csv`` into :class:`Finding` models."""
    return _load(path, Finding)


def load_registry(path: Path) -> list[Equipment]:
    """Read ``equipment_registry.csv`` into :class:`Equipment` models."""
    return _load(path, Equipment)


def index_registry(items: Iterable[Equipment]) -> dict[str, Equipment]:
    """Key the registry by ``equipment_id``.

    A repeated id means one of the two rows would be lost silently, so it fails
    here instead.
    """
    index: dict[str, Equipment] = {}
    duplicates: list[str] = []
    for item in items:
        if item.equipment_id in index:
            duplicates.append(item.equipment_id)
        index[item.equipment_id] = item
    if duplicates:
        raise RegistryJoinError(
            f"duplicate equipment_id in registry: {', '.join(sorted(set(duplicates)))}"
        )
    return index


class EnrichedFinding(BaseModel):
    """A finding with its registry row and its place in the batch.

    Not part of the output contract — nothing serialises this — so it stays here
    rather than in :mod:`triage.models`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding: Finding
    equipment: Equipment
    partners_with_findings: tuple[str, ...] = ()
    """Named redundancy partners that also carry a finding in this batch.

    Non-empty means the claimed redundancy is not available: findings against
    both legs of a pair mean the pair is not redundant.
    """

    unresolved_partners: tuple[str, ...] = ()
    """Partner tags with no matching registry row.

    Their health is unknown, which is a stated uncertainty rather than grounds
    for crediting or discrediting the redundancy.
    """


def join(
    findings: Iterable[Finding], registry: Iterable[Equipment]
) -> list[EnrichedFinding]:
    """Attach each finding's registry row and its partners' status in this batch.

    Raises :class:`RegistryJoinError` naming every finding whose ``equipment_id``
    is absent from the registry, so an incomplete registry surfaces in one run.

    ``Finding.equipment_type`` is denormalised; where it disagrees with the
    registry the registry wins and the disagreement is logged, because a
    mismatch is a data problem worth seeing but not one worth stopping for.
    """
    findings = list(findings)
    index = index_registry(registry)

    orphans = [f.finding_id for f in findings if f.equipment_id not in index]
    if orphans:
        raise RegistryJoinError(
            f"{len(orphans)} finding(s) reference an equipment_id absent from the "
            f"registry: {', '.join(orphans)}"
        )

    affected = {f.equipment_id for f in findings}

    enriched: list[EnrichedFinding] = []
    for finding in findings:
        equipment = index[finding.equipment_id]
        if finding.equipment_type != equipment.equipment_type:
            logger.warning(
                "%s: equipment_type %r disagrees with the registry's %r for %s; "
                "using the registry value",
                finding.finding_id,
                finding.equipment_type,
                equipment.equipment_type,
                equipment.equipment_id,
            )
        partners = equipment.redundancy.partner_equipment_ids
        enriched.append(
            EnrichedFinding(
                finding=finding,
                equipment=equipment,
                partners_with_findings=tuple(
                    p for p in partners if p in index and p in affected
                ),
                unresolved_partners=tuple(p for p in partners if p not in index),
            )
        )
    return enriched


__all__ = [
    "CsvValidationError",
    "EnrichedFinding",
    "RegistryJoinError",
    "RowError",
    "index_registry",
    "join",
    "load_findings",
    "load_registry",
]
