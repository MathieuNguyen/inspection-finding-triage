"""Input models: one per row of the read-only CSVs.

These are built from trusted, code-parsed data rather than model output, so
ordinary Pydantic constraints apply and a violation is a loud failure at load
time.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from triage.models.fields import (
    FindingId,
    InspectionType,
    NonEmptyStr,
    RegistryScore,
    TrimmedStr,
    YesNo,
)
from triage.models.redundancy import RedundancyField


class Finding(BaseModel):
    """One row of ``data/inspection_findings.csv``.

    ``extra="ignore"`` so a new column added to the CSV does not break loading.

    ``inspection_type`` is a closed vocabulary and is validated against it: the
    seven inspection programmes are specified, so a value outside them is a data
    error worth catching at load time rather than a new category. The remaining
    categoricals — ``inspection_method`` and ``reporter_role`` — are open
    strings, because neither is specified as a fixed set and an unfamiliar value
    there should reach the model as text.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    finding_id: FindingId
    reported_date: date
    equipment_id: NonEmptyStr = Field(description="Foreign key into the registry.")
    equipment_type: NonEmptyStr = Field(
        description="Denormalised from the registry; the registry row is authoritative."
    )
    inspection_type: InspectionType = Field(
        description="The inspection programme this finding came out of."
    )
    inspection_method: NonEmptyStr = Field(description="How the finding was detected.")
    finding_description: NonEmptyStr = Field(
        description="Free text written by the reporter. The primary signal."
    )
    reported_by: NonEmptyStr
    reporter_role: NonEmptyStr


class Equipment(BaseModel):
    """One row of ``data/equipment_registry.csv``.

    Both registry scores run 1-10 but in opposite directions, which is the single
    most common place to go wrong; see the field descriptions.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    equipment_id: NonEmptyStr
    equipment_type: NonEmptyStr
    service_description: NonEmptyStr
    criticality_score: RegistryScore = Field(
        description="1 = least critical, 10 = most critical."
    )
    reliability_score: RegistryScore = Field(
        description=(
            "1 = fails frequently, 10 = highly reliable. Runs opposite to "
            "likelihood of failure."
        )
    )
    safety_critical_element: YesNo = Field(
        description="Equipment on which a major accident scenario depends."
    )
    redundancy: RedundancyField
    engineer_comment: TrimmedStr = Field(
        default="", description="Unstructured notes about this specific item."
    )


__all__ = ["Equipment", "Finding"]
