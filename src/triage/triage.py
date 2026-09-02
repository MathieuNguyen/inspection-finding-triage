"""Run the five passes over a batch of findings and assemble the tickets.

This is the layer that calls everything below it. The registry has already joined
each finding to its equipment and worked out where it sits in the batch; the LLM
layer already knows how to make one typed call and how to run a bounded batch of
them; ``urgency.py`` already knows what range a likelihood and an impact imply.
Nothing had put those together.

**Five passes, three stages.** Summary, likelihood and impact depend only on the
finding, so they go out together. Urgency needs both scores and the range they
derive, so it waits for them. The recommended action needs the urgency it is
scheduling against, so it waits for that. Every pass is one
:meth:`~triage.llm.TriageClient.structured` call against one prompt from
``src/triage/prompts``.

**The prompt/input split is the reason this module exists in the shape it does.**
A template takes policies and nothing else, so ``instructions`` is byte-identical
for every finding in a run and worth a ``prompt_cache_key``. The finding's own
data goes over as ``user_input``, which means something has to turn an
:class:`~triage.registry.EnrichedFinding` into exactly the fields its prompt says
it will be handed. That is what the builders below do, one per pass, mirroring
the field lists in the prompt bodies.

**No scoring rule is written here.** The judgement is the policies'; the
arithmetic is ``urgency.py``'s. What this module decides is narrower and entirely
procedural: what each pass is shown, what order they run in, which ticket id a
finding gets, and what a human is told to look at when the ticket reaches them.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from functools import cache

from triage.llm import (
    Effort,
    ItemFailure,
    TriageClient,
    build_prompt,
    gather_bounded,
    load_policy,
)
from triage.models import (
    ScoreBlock,
    Ticket,
    TicketDocument,
    TicketFailure,
    TicketTextBlock,
    UrgencyBlock,
)
from triage.registry import EnrichedFinding
from triage.urgency import UrgencyBounds, derive_urgency

_POLICY_SLOTS: dict[str, dict[str, str]] = {
    "summary": {},
    "scoring_likelihood": {"likelihood_policy": "likelihood"},
    "scoring_impact": {"impact_policy": "impact", "errors_policy": "errors"},
    "scoring_urgency": {"urgency_policy": "urgency"},
    "actions": {"urgency_policy": "urgency"},
}
"""Which policy fills which slot, per prompt. The table in ``prompts/README.md``.

Stated once here rather than spelled out at five call sites, so a prompt that
gains a policy slot is a one-line change in the place the slot is named.
"""


@cache
def _instructions(name: str) -> str:
    """The composed prompt for one pass.

    Cached because it is constant for a run: the same bytes go out with every
    finding, which is the premise :func:`_cache_key` trades on.
    """
    slots = _POLICY_SLOTS[name]
    return build_prompt(name, **{slot: load_policy(policy) for slot, policy in slots.items()})


def _cache_key(name: str) -> str:
    """The provider-side cache key for a pass.

    Names the pass and nothing else. Putting a finding in here would defeat the
    point: the prefix worth caching is the policy text, which every finding in
    the run shares.
    """
    return f"triage-{name}"


def _payload(**fields: object) -> str:
    """A pass's ``user_input``: the fields its prompt names, as JSON.

    Insertion order is preserved, so the payload reads in the order the prompt
    introduces the fields.
    """
    return json.dumps(fields, indent=2, ensure_ascii=False, default=str)


def _summary_input(item: EnrichedFinding) -> str:
    """What ``prompts/summary.md`` says it will be handed."""
    return _payload(
        finding_description=item.finding.finding_description,
        inspection_type=item.finding.inspection_type,
        inspection_method=item.finding.inspection_method,
        equipment_type=item.equipment.equipment_type,
        safety_critical_element=item.equipment.safety_critical_element,
        engineer_comment=item.equipment.engineer_comment,
    )


def _likelihood_input(item: EnrichedFinding) -> str:
    """What ``prompts/scoring_likelihood.md`` says it will be handed.

    ``reliability_score`` reaches this pass and only this pass. It runs opposite
    to likelihood, and the policy is what says so.
    """
    return _payload(
        finding_description=item.finding.finding_description,
        inspection_type=item.finding.inspection_type,
        inspection_method=item.finding.inspection_method,
        equipment_type=item.equipment.equipment_type,
        service_description=item.equipment.service_description,
        reliability_score=item.equipment.reliability_score,
        engineer_comment=item.equipment.engineer_comment,
    )


def _impact_input(item: EnrichedFinding) -> str:
    """What ``prompts/scoring_impact.md`` says it will be handed.

    The two partner tuples are the batch-scope facts the registry worked out.
    They go over uninterpreted: what they mean for the score is the recurring
    errors policy's business, not this function's.
    """
    return _payload(
        finding_description=item.finding.finding_description,
        equipment_type=item.equipment.equipment_type,
        service_description=item.equipment.service_description,
        safety_critical_element=item.equipment.safety_critical_element,
        criticality_score=item.equipment.criticality_score,
        redundancy=item.equipment.redundancy.raw,
        partners_with_findings=list(item.partners_with_findings),
        unresolved_partners=list(item.unresolved_partners),
        engineer_comment=item.equipment.engineer_comment,
    )


def _urgency_input(
    item: EnrichedFinding,
    likelihood: ScoreBlock,
    impact: ScoreBlock,
    bounds: UrgencyBounds,
) -> str:
    """What ``prompts/scoring_urgency.md`` says it will be handed.

    Both scores go over with their rationales rather than as bare numbers: the
    prompt asks the pass to read the evidence and the stated uncertainty behind
    each, not just the integer.
    """
    return _payload(
        finding_description=item.finding.finding_description,
        inspection_type=item.finding.inspection_type,
        inspection_method=item.finding.inspection_method,
        equipment_type=item.equipment.equipment_type,
        service_description=item.equipment.service_description,
        safety_critical_element=item.equipment.safety_critical_element,
        engineer_comment=item.equipment.engineer_comment,
        likelihood_of_failure=likelihood.model_dump(),
        impact_of_failure=impact.model_dump(),
        derived_range=str(bounds),
    )


def _action_input(item: EnrichedFinding, urgency: UrgencyBlock) -> str:
    """What ``prompts/actions.md`` says it will be handed.

    ``override`` is included so the compliance step the policy asks for keys off
    a field rather than off whatever the urgency rationale happened to say.
    """
    return _payload(
        finding_description=item.finding.finding_description,
        inspection_type=item.finding.inspection_type,
        inspection_method=item.finding.inspection_method,
        equipment_type=item.equipment.equipment_type,
        service_description=item.equipment.service_description,
        safety_critical_element=item.equipment.safety_critical_element,
        redundancy=item.equipment.redundancy.raw,
        engineer_comment=item.equipment.engineer_comment,
        urgency=urgency.model_dump(),
    )


async def _summary(client: TriageClient, item: EnrichedFinding) -> TicketTextBlock:
    """The ticket's summary line."""
    return await client.structured(
        instructions=_instructions("summary"),
        user_input=_summary_input(item),
        text_format=TicketTextBlock,
        effort=Effort.WRITING,
        cache_key=_cache_key("summary"),
    )


async def _likelihood(client: TriageClient, item: EnrichedFinding) -> ScoreBlock:
    """How likely the item is to stop performing its function."""
    return await client.structured(
        instructions=_instructions("scoring_likelihood"),
        user_input=_likelihood_input(item),
        text_format=ScoreBlock,
        effort=Effort.JUDGING,
        cache_key=_cache_key("scoring_likelihood"),
    )


async def _impact(client: TriageClient, item: EnrichedFinding) -> ScoreBlock:
    """What happens if it does."""
    return await client.structured(
        instructions=_instructions("scoring_impact"),
        user_input=_impact_input(item),
        text_format=ScoreBlock,
        effort=Effort.JUDGING,
        cache_key=_cache_key("scoring_impact"),
    )


async def _urgency(
    client: TriageClient,
    item: EnrichedFinding,
    likelihood: ScoreBlock,
    impact: ScoreBlock,
    bounds: UrgencyBounds,
) -> UrgencyBlock:
    """How soon a human must act, and which override condition applies."""
    return await client.structured(
        instructions=_instructions("scoring_urgency"),
        user_input=_urgency_input(item, likelihood, impact, bounds),
        text_format=UrgencyBlock,
        effort=Effort.JUDGING,
        cache_key=_cache_key("scoring_urgency"),
    )


async def _action(
    client: TriageClient, item: EnrichedFinding, urgency: UrgencyBlock
) -> TicketTextBlock:
    """The next thing a person does about this finding."""
    return await client.structured(
        instructions=_instructions("actions"),
        user_input=_action_input(item, urgency),
        text_format=TicketTextBlock,
        effort=Effort.WRITING,
        cache_key=_cache_key("actions"),
    )


def ticket_id_for(finding_id: str) -> str:
    """``F-1005`` becomes ``TKT-1005``.

    One ticket per finding, and the same id on every run — which is worth more
    than a batch-order counter, because rerunning a subset of a file would
    otherwise renumber tickets that had not changed. Both id patterns are four
    digits, so the swap always lands inside :data:`~triage.models.TicketId`.
    """
    return f"TKT-{finding_id.removeprefix('F-')}"


REVIEW_STANDING_REASON = "Every ticket is approved by a human before it enters the work queue."
"""Why every ticket carries the flag today.

Review is unconditional for now. The per-ticket notes below do not decide
*whether* a human looks — they decide what the human looks at first.
"""


def review_reason(
    item: EnrichedFinding, urgency: UrgencyBlock, bounds: UrgencyBounds
) -> str:
    """The standing rule, plus anything about this ticket worth checking first.

    Each note is a fact about how the ticket was produced — an override that
    fired, a score that left its derived range, a redundancy claim the batch
    contradicts. None of them is a scoring rule; the reasoning behind each lives
    in the policy that produced it and in the rationale on the ticket.
    """
    notes: list[str] = []

    if urgency.override is not None:
        condition = urgency.override.value.replace("_", " ")
        notes.append(f"Urgency was set by the {condition} override.")
    if not bounds.contains(urgency.score):
        notes.append(
            f"The urgency score of {urgency.score} sits outside the derived range "
            f"of {bounds}."
        )
    if item.partners_with_findings:
        partners = ", ".join(item.partners_with_findings)
        notes.append(
            f"The claimed redundancy is not available: {partners} also carries a "
            "finding in this batch."
        )
    if item.unresolved_partners:
        partners = ", ".join(item.unresolved_partners)
        notes.append(
            f"Redundancy partner {partners} has no registry row, so its condition "
            "is unknown."
        )
    if item.equipment.safety_critical_element:
        notes.append("The equipment is a Safety Critical Element.")

    return " ".join([REVIEW_STANDING_REASON, *notes])


async def triage_finding(client: TriageClient, item: EnrichedFinding) -> Ticket:
    """Score one finding and assemble its ticket.

    The three independent passes go out together; urgency and the action follow
    in turn because each needs what the step before it produced.
    """
    summary, likelihood, impact = await asyncio.gather(
        _summary(client, item),
        _likelihood(client, item),
        _impact(client, item),
    )

    bounds = derive_urgency(
        likelihood=likelihood.score,
        impact=impact.score,
        safety_critical=item.equipment.safety_critical_element,
    )
    urgency = await _urgency(client, item, likelihood, impact, bounds)
    action = await _action(client, item, urgency)

    return Ticket(
        ticket_id=ticket_id_for(item.finding.finding_id),
        finding_id=item.finding.finding_id,
        equipment_id=item.equipment.equipment_id,
        summary=summary.text,
        likelihood_of_failure=likelihood,
        impact_of_failure=impact,
        # Narrowed deliberately rather than left to serialisation: which override
        # fired is how this ticket got its number, not part of the delivered shape.
        urgency=ScoreBlock(score=urgency.score, rationale=urgency.rationale),
        recommended_action=action.text,
        review_required=True,
        review_reason=review_reason(item, urgency, bounds),
    )


def _failure(failure: ItemFailure) -> TicketFailure:
    """One batch failure, as the document records it.

    ``str`` on an exception can be empty — a bare ``raise SomeError`` — and
    ``detail`` may not be blank, so the type stands in for a silent one.
    """
    return TicketFailure(
        finding_id=failure.key,
        error=type(failure.error).__name__,
        detail=str(failure.error) or type(failure.error).__name__,
    )


async def triage_batch(
    client: TriageClient, items: Sequence[EnrichedFinding]
) -> TicketDocument:
    """Triage every finding in the batch, at most ``max_concurrency`` at a time.

    The ceiling counts findings rather than requests, which is what the setting
    says it means; a finding's own three-way fan-out sits inside one slot.

    **A finding that fails does not take the batch down with it.** The other
    findings' calls have already been made and paid for by then, and a run that
    threw them away would be both expensive and less informative than one that
    says which findings came through and which did not. So this gathers rather
    than reduces: tickets come back in input order, failures come back beside
    them, and both go into the document. What a caller does about a non-empty
    :attr:`~triage.models.TicketDocument.failures` is the caller's business —
    the CLI writes the file and exits non-zero.

    The :class:`~triage.models.TicketDocument` is built here rather than by the
    caller because its validators are batch-scope checks — the two counts, and
    the absence of a duplicated ticket id or a finding id claimed twice.
    """
    tickets, failures = await gather_bounded(
        items,
        lambda item: triage_finding(client, item),
        limit=client.settings.max_concurrency,
        key=lambda item: item.finding.finding_id,
    )
    return TicketDocument(
        tickets=tickets, failures=[_failure(failure) for failure in failures]
    )


__all__ = [
    "REVIEW_STANDING_REASON",
    "review_reason",
    "ticket_id_for",
    "triage_batch",
    "triage_finding",
]
