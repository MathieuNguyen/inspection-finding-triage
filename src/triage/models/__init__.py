"""Pydantic models for the inspection finding triage pipeline.

The models are split by the direction data flows, one module per group:

* :mod:`triage.models.inputs` — :class:`Finding` and :class:`Equipment`, one per
  row of the two read-only CSVs.
* :mod:`triage.models.redundancy` — :class:`Redundancy`, structure recovered
  from a free-text registry column so later passes can reason over it.
* :mod:`triage.models.outputs` — :class:`ScoreBlock`, :class:`UrgencyBlock`,
  :class:`TicketTextBlock`, :class:`Ticket` and :class:`TicketDocument`: the shape
  of ``tickets.json``, the pieces the individual passes author, and the acceptance
  gate for all of it.

:mod:`triage.models.fields` holds the annotated primitives the three share, so a
constraint such as the 300-character ticket limit is stated once.

Everything public is re-exported here: import from ``triage.models``, not from
the submodules.

No triage guidance is encoded in this package. What the model scores against
lives in the markdown under ``src/triage/policies`` and is composed into the
prompts that need it; field descriptions here stay structural for the same
reason: scoring guidance belongs with the policies, not duplicated in source
where the two can drift apart.

:class:`UrgencyBlock`'s override floor is the one number here that came from a
policy, and it is a consistency gate rather than guidance. The policy is what
tells the model an override condition is immediate; the validator only checks the
score it returned against the override it declared.

**On numeric bounds.** Structured-output schemas are a strict JSON Schema subset
in which numeric bounds are not enforced, so ``Field(ge=1, le=10)`` would not
constrain a model-authored score. Anything a model may author therefore states
its range in ``description`` (which the model reads) and enforces it in a
``@field_validator`` after parsing. Fields that only ever come from the CSVs use
plain ``ge``/``le``.
"""

from triage.models.fields import (
    INSPECTION_TYPES,
    SCORE_RANGE,
    TICKET_TEXT_LIMIT,
    TICKET_TEXT_TARGET,
    URGENCY_OVERRIDE_FLOOR,
    FindingId,
    InspectionType,
    NonEmptyStr,
    RegistryScore,
    TicketId,
    TicketText,
    TrimmedStr,
    YesNo,
)
from triage.models.inputs import Equipment, Finding
from triage.models.outputs import (
    ScoreBlock,
    Ticket,
    TicketDocument,
    TicketFailure,
    TicketTextBlock,
    UrgencyBlock,
    UrgencyOverride,
)
from triage.models.redundancy import Redundancy, RedundancyField, RedundancyKind

__all__ = [
    "INSPECTION_TYPES",
    "SCORE_RANGE",
    "TICKET_TEXT_LIMIT",
    "TICKET_TEXT_TARGET",
    "URGENCY_OVERRIDE_FLOOR",
    "Equipment",
    "Finding",
    "FindingId",
    "InspectionType",
    "NonEmptyStr",
    "Redundancy",
    "RedundancyField",
    "RedundancyKind",
    "RegistryScore",
    "ScoreBlock",
    "Ticket",
    "TicketDocument",
    "TicketFailure",
    "TicketId",
    "TicketText",
    "TicketTextBlock",
    "TrimmedStr",
    "UrgencyBlock",
    "UrgencyOverride",
    "YesNo",
]
