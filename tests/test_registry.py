"""Loading, indexing and joining the CSVs.

Every row here is synthetic. Nothing is copied from ``data/`` and no test
depends on a particular equipment id existing in the supplied registry.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from triage.registry import (
    CsvValidationError,
    RegistryJoinError,
    index_registry,
    join,
    load_findings,
    load_registry,
)

CsvRow = dict[str, str]
CsvFile = Callable[..., Path]
RowFactory = Callable[..., CsvRow]


def test_well_formed_findings_file_loads(
    csv_file: CsvFile, finding_row: RowFactory
) -> None:
    path = csv_file([finding_row(), finding_row(finding_id="F-9002")])
    findings = load_findings(path)
    assert [f.finding_id for f in findings] == ["F-9001", "F-9002"]


def test_well_formed_registry_file_loads(
    csv_file: CsvFile, equipment_row: RowFactory
) -> None:
    path = csv_file([equipment_row(), equipment_row(equipment_id="XX-0002")])
    registry = load_registry(path)
    assert [e.equipment_id for e in registry] == ["XX-0001", "XX-0002"]
    assert registry[0].safety_critical_element is False


def test_every_bad_row_is_reported_together(
    csv_file: CsvFile, finding_row: RowFactory
) -> None:
    """One run names every problem, so a broken file is fixed in one pass."""
    path = csv_file(
        [
            finding_row(finding_id="nonsense"),
            finding_row(finding_id="F-9002"),
            finding_row(finding_id="F-9003", inspection_type="Vibes Check"),
        ]
    )
    with pytest.raises(CsvValidationError) as caught:
        load_findings(path)

    error = caught.value
    assert [row.line for row in error.errors] == [2, 4]
    message = str(error)
    assert "line 2" in message
    assert "line 4" in message
    assert "line 3" not in message


def test_byte_order_mark_is_tolerated(
    csv_file: CsvFile, finding_row: RowFactory
) -> None:
    path = csv_file([finding_row()], encoding="utf-8-sig")
    assert load_findings(path)[0].finding_id == "F-9001"


def test_surrounding_whitespace_is_trimmed(
    csv_file: CsvFile, finding_row: RowFactory
) -> None:
    path = csv_file(
        [finding_row(finding_id="  F-9001  ", inspection_method="  Visual  ")]
    )
    finding = load_findings(path)[0]
    assert finding.finding_id == "F-9001"
    assert finding.inspection_method == "Visual"


def test_unknown_column_is_ignored(
    csv_file: CsvFile, finding_row: RowFactory
) -> None:
    """A column added upstream must not break the load."""
    row = finding_row() | {"added_later": "whatever"}
    path = csv_file([row], header=[*finding_row(), "added_later"])
    assert load_findings(path)[0].finding_id == "F-9001"


def test_missing_column_is_reported(
    csv_file: CsvFile, finding_row: RowFactory
) -> None:
    header = [name for name in finding_row() if name != "finding_description"]
    path = csv_file([finding_row()], header=header)
    with pytest.raises(CsvValidationError) as caught:
        load_findings(path)
    assert "finding_description" in str(caught.value)


def test_duplicate_equipment_id_is_rejected(equipment_row: RowFactory) -> None:
    """Two rows on one id would silently drop one of them from the join."""
    from triage.models import Equipment

    items = [
        Equipment(**equipment_row()),
        Equipment(**equipment_row(service_description="A different item")),
    ]
    with pytest.raises(RegistryJoinError, match="XX-0001"):
        index_registry(items)


def _load_pair(
    csv_file: CsvFile,
    findings: Sequence[CsvRow],
    registry: Sequence[CsvRow],
) -> tuple[list, list]:
    return (
        load_findings(csv_file(findings, name="findings.csv")),
        load_registry(csv_file(registry, name="registry.csv")),
    )


def test_join_attaches_the_registry_row(
    csv_file: CsvFile, finding_row: RowFactory, equipment_row: RowFactory
) -> None:
    findings, registry = _load_pair(csv_file, [finding_row()], [equipment_row()])
    enriched = join(findings, registry)
    assert len(enriched) == 1
    assert enriched[0].equipment.equipment_id == "XX-0001"
    assert enriched[0].partners_with_findings == ()
    assert enriched[0].unresolved_partners == ()


def test_orphan_finding_names_every_offender(
    csv_file: CsvFile, finding_row: RowFactory, equipment_row: RowFactory
) -> None:
    findings, registry = _load_pair(
        csv_file,
        [
            finding_row(equipment_id="XX-0404"),
            finding_row(finding_id="F-9002"),
            finding_row(finding_id="F-9003", equipment_id="XX-0405"),
        ],
        [equipment_row()],
    )
    with pytest.raises(RegistryJoinError) as caught:
        join(findings, registry)
    message = str(caught.value)
    assert "F-9001" in message
    assert "F-9003" in message
    assert "F-9002" not in message


def test_registry_wins_an_equipment_type_disagreement(
    csv_file: CsvFile,
    finding_row: RowFactory,
    equipment_row: RowFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The finding's copy is denormalised; the registry is authoritative."""
    findings, registry = _load_pair(
        csv_file,
        [finding_row(equipment_type="Sprocket")],
        [equipment_row(equipment_type="Widget")],
    )
    with caplog.at_level(logging.WARNING, logger="triage.registry"):
        enriched = join(findings, registry)

    assert enriched[0].equipment.equipment_type == "Widget"
    assert "Sprocket" in caplog.text
    assert "F-9001" in caplog.text


def test_a_partner_with_its_own_finding_is_recorded(
    csv_file: CsvFile, finding_row: RowFactory, equipment_row: RowFactory
) -> None:
    """Findings against both legs mean the pair is not redundant."""
    findings, registry = _load_pair(
        csv_file,
        [
            finding_row(),
            finding_row(finding_id="F-9002", equipment_id="XX-0002"),
        ],
        [
            equipment_row(redundancy="N+1 (XX-0002)"),
            equipment_row(equipment_id="XX-0002", redundancy="N+1 (XX-0001)"),
        ],
    )
    by_id = {e.finding.finding_id: e for e in join(findings, registry)}
    assert by_id["F-9001"].partners_with_findings == ("XX-0002",)
    assert by_id["F-9002"].partners_with_findings == ("XX-0001",)


def test_a_healthy_partner_is_not_recorded(
    csv_file: CsvFile, finding_row: RowFactory, equipment_row: RowFactory
) -> None:
    findings, registry = _load_pair(
        csv_file,
        [finding_row()],
        [
            equipment_row(redundancy="N+1 (XX-0002)"),
            equipment_row(equipment_id="XX-0002", redundancy="N+1 (XX-0001)"),
        ],
    )
    assert join(findings, registry)[0].partners_with_findings == ()


def test_a_partner_absent_from_the_registry_is_surfaced(
    csv_file: CsvFile, finding_row: RowFactory, equipment_row: RowFactory
) -> None:
    """An unknown partner is a stated uncertainty, not a crash."""
    findings, registry = _load_pair(
        csv_file,
        [finding_row()],
        [equipment_row(redundancy="Duplicated (XX-9999)")],
    )
    enriched = join(findings, registry)[0]
    assert enriched.unresolved_partners == ("XX-9999",)
    assert enriched.partners_with_findings == ()
