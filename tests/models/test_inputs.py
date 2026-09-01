"""The CSV row models."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from pydantic import ValidationError

from triage.models import INSPECTION_TYPES, Equipment, Finding, RedundancyKind

CsvRow = dict[str, str]


def test_finding_parses_csv_strings(finding_row: Callable[..., CsvRow]) -> None:
    finding = Finding(**finding_row())
    assert finding.reported_date == date(2026, 1, 15)


def test_finding_id_pattern_enforced(finding_row: Callable[..., CsvRow]) -> None:
    with pytest.raises(ValidationError):
        Finding(**finding_row(finding_id="1001"))


def test_unknown_csv_column_is_ignored(finding_row: Callable[..., CsvRow]) -> None:
    """A new column in either CSV must not break loading."""
    finding = Finding(**finding_row(), work_order_ref="WO-1")
    assert not hasattr(finding, "work_order_ref")


def test_open_categoricals_accept_unseen_values(
    finding_row: Callable[..., CsvRow],
) -> None:
    """inspection_method and reporter_role are not specified as fixed sets."""
    finding = Finding(
        **finding_row(
            inspection_method="Acoustic Emission",
            reporter_role="Subsea Inspection Engineer",
        )
    )
    assert finding.inspection_method == "Acoustic Emission"
    assert finding.reporter_role == "Subsea Inspection Engineer"


@pytest.mark.parametrize("value", INSPECTION_TYPES)
def test_every_specified_inspection_type_loads(
    value: str, finding_row: Callable[..., CsvRow]
) -> None:
    assert Finding(**finding_row(inspection_type=value)).inspection_type == value


def test_unknown_inspection_type_is_rejected(
    finding_row: Callable[..., CsvRow],
) -> None:
    """A closed vocabulary: an unlisted programme fails the load."""
    with pytest.raises(ValidationError):
        Finding(**finding_row(inspection_type="Thermographic Survey"))


def test_equipment_yes_no_becomes_bool(equipment_row: Callable[..., CsvRow]) -> None:
    assert Equipment(**equipment_row(safety_critical_element="Yes")).safety_critical_element
    assert not Equipment(**equipment_row(safety_critical_element="No")).safety_critical_element


def test_equipment_rejects_unparseable_sce_flag(
    equipment_row: Callable[..., CsvRow],
) -> None:
    with pytest.raises(ValidationError):
        Equipment(**equipment_row(safety_critical_element="Maybe"))


def test_registry_scores_bounded(equipment_row: Callable[..., CsvRow]) -> None:
    with pytest.raises(ValidationError):
        Equipment(**equipment_row(criticality_score="11"))
    with pytest.raises(ValidationError):
        Equipment(**equipment_row(reliability_score="0"))


def test_redundancy_is_parsed_from_the_cell(
    equipment_row: Callable[..., CsvRow],
) -> None:
    equipment = Equipment(**equipment_row(redundancy="Voted 2oo3"))
    assert equipment.redundancy.kind is RedundancyKind.VOTED


def test_engineer_comment_may_be_blank(equipment_row: Callable[..., CsvRow]) -> None:
    assert Equipment(**equipment_row(engineer_comment="  ")).engineer_comment == ""
