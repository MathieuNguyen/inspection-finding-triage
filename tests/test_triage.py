"""The triage layer: what each pass is shown, in what order, and what comes out.

Nothing here opens a socket. Every pass answers from a stub keyed on its cache
key, so a test says what the urgency pass replies without depending on which of
the three concurrent passes reached the stub first.

Two things are being pinned. The first is the **wiring**: each prompt names the
fields it will be handed, and the payload read back off the stub has to be
exactly that list — a builder that quietly gains a field the prompt does not
mention is the failure these tests exist for. The second is the **assembly**: the
ticket id, the narrowing of the urgency block, and what a human is told to look
at. No test asserts on a score, on what a policy says, or against
``reference/example_ticket.json``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from types import SimpleNamespace
from typing import Any

import pytest

from triage.llm import LlmSettings, RefusalError, TriageClient
from triage.models import (
    ScoreBlock,
    Ticket,
    TicketTextBlock,
    UrgencyBlock,
    UrgencyOverride,
)
from triage.registry import EnrichedFinding
from triage.triage import (
    REVIEW_STANDING_REASON,
    ticket_id_for,
    triage_batch,
    triage_finding,
)
from triage.urgency import derive_urgency

Settings = Callable[..., LlmSettings]
Client = Callable[..., Any]
Response = Callable[..., Any]
Enriched = Callable[..., list[EnrichedFinding]]

SUMMARY = "triage-summary"
LIKELIHOOD = "triage-scoring_likelihood"
IMPACT = "triage-scoring_impact"
URGENCY = "triage-scoring_urgency"
ACTIONS = "triage-actions"

PASSES = (SUMMARY, LIKELIHOOD, IMPACT, URGENCY, ACTIONS)

FIELDS: dict[str, set[str]] = {
    SUMMARY: {
        "finding_description",
        "inspection_type",
        "inspection_method",
        "equipment_type",
        "safety_critical_element",
        "engineer_comment",
    },
    LIKELIHOOD: {
        "finding_description",
        "inspection_type",
        "inspection_method",
        "equipment_type",
        "service_description",
        "reliability_score",
        "engineer_comment",
    },
    IMPACT: {
        "finding_description",
        "equipment_type",
        "service_description",
        "safety_critical_element",
        "criticality_score",
        "redundancy",
        "partners_with_findings",
        "unresolved_partners",
        "engineer_comment",
    },
    URGENCY: {
        "finding_description",
        "inspection_type",
        "inspection_method",
        "equipment_type",
        "service_description",
        "safety_critical_element",
        "engineer_comment",
        "likelihood_of_failure",
        "impact_of_failure",
        "derived_range",
    },
    ACTIONS: {
        "finding_description",
        "inspection_type",
        "inspection_method",
        "equipment_type",
        "service_description",
        "safety_critical_element",
        "redundancy",
        "engineer_comment",
        "urgency",
    },
}
"""What each prompt says it will be handed. The prompt markdown is the contract."""


def _answers(
    response: Response,
    *,
    summary: str = "Synthetic summary.",
    likelihood: int = 4,
    impact: int = 6,
    urgency: int = 6,
    override: UrgencyOverride | None = None,
    action: str = "Replace the synthetic widget.",
    replace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One answer per pass.

    The default scores derive a range of 5 to 7, so the default urgency of 6
    sits inside it and nothing incidental trips the review notes.
    """
    answers = {
        SUMMARY: response(TicketTextBlock(text=summary)),
        LIKELIHOOD: response(ScoreBlock(score=likelihood, rationale="Likelihood rationale.")),
        IMPACT: response(ScoreBlock(score=impact, rationale="Impact rationale.")),
        URGENCY: response(
            UrgencyBlock(score=urgency, rationale="Urgency rationale.", override=override)
        ),
        ACTIONS: response(TicketTextBlock(text=action)),
    }
    return answers | dict(replace or {})


def _wire(
    stub_factory: Client, settings: Settings, answers: Mapping[str, Any], **overrides: object
) -> tuple[TriageClient, Any]:
    stub = stub_factory(answers)
    return TriageClient(stub, settings(**overrides)), stub


class _FailsOneFinding:
    """A stub that fails every pass for one finding and answers for the rest.

    ``keyed_client`` answers by cache key, which is right when every finding
    gets the same answer and useless for a batch where one fails and another
    does not. The finding is picked out by its description, since that is what
    every pass's payload carries.
    """

    def __init__(self, inner: Any, description: str, error: Exception) -> None:
        self._inner = inner
        self._description = description
        self._error = error
        self.responses = SimpleNamespace(parse=self._parse)

    async def _parse(self, **kwargs: Any) -> Any:
        payload = json.loads(kwargs["input"][0]["content"])
        if payload.get("finding_description") == self._description:
            raise self._error
        return await self._inner.responses.parse(**kwargs)


def _sent(stub: Any, key: str, index: int = 0) -> dict[str, Any]:
    """The JSON one pass was handed, read back off the stub."""
    return json.loads(stub.calls_for(key)[index]["input"][0]["content"])


async def test_a_pass_is_shown_exactly_the_fields_its_prompt_names(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, stub = _wire(keyed_client, settings, _answers(response))
    await triage_finding(client, enriched()[0])

    for key in PASSES:
        assert set(_sent(stub, key)) == FIELDS[key], key


async def test_the_registry_scores_do_not_cross_passes(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """The inversion trap, guarded at the wiring.

    ``reliability_score`` runs opposite to likelihood and ``criticality_score``
    does not. Neither pass is shown the other's prior, so neither can confuse
    them.
    """
    client, stub = _wire(keyed_client, settings, _answers(response))
    await triage_finding(client, enriched()[0])

    assert "reliability_score" in _sent(stub, LIKELIHOOD)
    assert "criticality_score" not in _sent(stub, LIKELIHOOD)
    assert "criticality_score" in _sent(stub, IMPACT)
    assert "reliability_score" not in _sent(stub, IMPACT)


async def test_the_registry_wins_the_equipment_type(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """``equipment_type`` is denormalised onto the finding; the registry is authoritative."""
    client, stub = _wire(keyed_client, settings, _answers(response))
    await triage_finding(
        client,
        enriched(findings=[{"equipment_type": "Doodad"}], equipment=[{"equipment_type": "Widget"}])[0],
    )

    for key in (SUMMARY, LIKELIHOOD, IMPACT, URGENCY, ACTIONS):
        assert _sent(stub, key)["equipment_type"] == "Widget", key


async def test_the_redundancy_cell_goes_over_as_written(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, stub = _wire(keyed_client, settings, _answers(response))
    await triage_finding(
        client, enriched(equipment=[{"redundancy": "N+1 (XX-0002)"}])[0]
    )

    assert _sent(stub, IMPACT)["redundancy"] == "N+1 (XX-0002)"
    assert _sent(stub, ACTIONS)["redundancy"] == "N+1 (XX-0002)"


async def test_the_impact_pass_is_shown_the_rest_of_the_batch(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """Findings against both legs of a pair mean the pair is not redundant."""
    client, stub = _wire(keyed_client, settings, _answers(response))
    items = enriched(
        findings=[
            {"finding_id": "F-9001", "equipment_id": "XX-0001"},
            {"finding_id": "F-9002", "equipment_id": "XX-0002"},
        ],
        equipment=[
            {"equipment_id": "XX-0001", "redundancy": "Duplicated (XX-0002)"},
            {"equipment_id": "XX-0002", "redundancy": "Duplicated (XX-9999)"},
        ],
    )
    await triage_finding(client, items[0])
    await triage_finding(client, items[1])

    assert _sent(stub, IMPACT, 0)["partners_with_findings"] == ["XX-0002"]
    assert _sent(stub, IMPACT, 0)["unresolved_partners"] == []
    assert _sent(stub, IMPACT, 1)["partners_with_findings"] == []
    assert _sent(stub, IMPACT, 1)["unresolved_partners"] == ["XX-9999"]


async def test_the_urgency_pass_is_given_the_range_the_two_scores_derive(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, stub = _wire(keyed_client, settings, _answers(response, likelihood=8, impact=9))
    await triage_finding(client, enriched(equipment=[{"safety_critical_element": "Yes"}])[0])

    expected = derive_urgency(likelihood=8, impact=9, safety_critical=True)
    assert _sent(stub, URGENCY)["derived_range"] == str(expected)


async def test_the_urgency_pass_is_given_both_rationales_not_only_the_numbers(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, stub = _wire(keyed_client, settings, _answers(response))
    await triage_finding(client, enriched()[0])

    payload = _sent(stub, URGENCY)
    assert payload["likelihood_of_failure"] == {
        "score": 4,
        "rationale": "Likelihood rationale.",
    }
    assert payload["impact_of_failure"] == {"score": 6, "rationale": "Impact rationale."}


async def test_the_actions_pass_is_given_the_override(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """The compliance step keys off a field, not off whatever the rationale said."""
    client, stub = _wire(
        keyed_client,
        settings,
        _answers(response, urgency=9, override=UrgencyOverride.PROTECTION_LAYER),
    )
    await triage_finding(client, enriched()[0])

    assert _sent(stub, ACTIONS)["urgency"] == {
        "score": 9,
        "rationale": "Urgency rationale.",
        "override": "protection_layer",
    }


async def test_the_instructions_are_identical_across_findings(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """What ``prompt_cache_key`` is worth passing for."""
    client, stub = _wire(keyed_client, settings, _answers(response))
    items = enriched(
        findings=[
            {"finding_id": "F-9001", "finding_description": "One thing."},
            {"finding_id": "F-9002", "finding_description": "Another thing entirely."},
        ]
    )
    await triage_finding(client, items[0])
    await triage_finding(client, items[1])

    for key in PASSES:
        first, second = stub.calls_for(key)
        assert first["instructions"] == second["instructions"], key
        assert first["input"] != second["input"], key


async def test_each_pass_is_cached_under_its_own_key(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, stub = _wire(keyed_client, settings, _answers(response))
    await triage_finding(client, enriched()[0])

    keys = [call["prompt_cache_key"] for call in stub.calls]
    assert sorted(keys) == sorted(PASSES)
    # Summary, likelihood and impact go out together, so their order among
    # themselves is a scheduling detail. The last two are forced: urgency needs
    # both scores, and the action needs the urgency.
    assert keys[-2:] == [URGENCY, ACTIONS]
    assert len({call["instructions"] for call in stub.calls}) == len(PASSES)


@pytest.mark.parametrize(
    ("finding_id", "ticket_id"),
    [("F-0001", "TKT-0001"), ("F-1005", "TKT-1005"), ("F-9999", "TKT-9999")],
)
def test_the_ticket_id_mirrors_the_finding_id(finding_id: str, ticket_id: str) -> None:
    """The same finding gets the same ticket on every run, whatever else is in the batch."""
    assert ticket_id_for(finding_id) == ticket_id


async def test_the_delivered_urgency_drops_the_override(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """Which override fired is how the number was reached, not part of the shape."""
    client, _ = _wire(
        keyed_client,
        settings,
        _answers(response, urgency=10, override=UrgencyOverride.EVACUATION_CAPACITY),
    )
    ticket = await triage_finding(client, enriched()[0])

    assert set(ticket.model_dump()["urgency"]) == {"score", "rationale"}
    assert ticket.urgency.score == 10


async def test_the_ticket_carries_what_each_pass_wrote(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, _ = _wire(keyed_client, settings, _answers(response))
    ticket = await triage_finding(client, enriched()[0])

    assert isinstance(ticket, Ticket)
    assert ticket.summary == "Synthetic summary."
    assert ticket.recommended_action == "Replace the synthetic widget."
    assert (ticket.likelihood_of_failure.score, ticket.impact_of_failure.score) == (4, 6)
    assert ticket.finding_id == "F-9001"
    assert ticket.equipment_id == "XX-0001"


async def test_every_ticket_is_flagged_for_review(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """Review is unconditional: nothing reaches the work queue unapproved."""
    client, _ = _wire(keyed_client, settings, _answers(response))
    ticket = await triage_finding(client, enriched()[0])

    assert ticket.review_required is True
    assert ticket.review_reason is not None
    assert ticket.review_reason.startswith(REVIEW_STANDING_REASON)


async def test_a_clean_finding_carries_only_the_standing_reason(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, _ = _wire(keyed_client, settings, _answers(response))
    ticket = await triage_finding(client, enriched()[0])

    assert ticket.review_reason == REVIEW_STANDING_REASON


async def test_the_review_reason_names_an_override_that_fired(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, _ = _wire(
        keyed_client,
        settings,
        _answers(response, urgency=9, override=UrgencyOverride.EVACUATION_CAPACITY),
    )
    ticket = await triage_finding(client, enriched()[0])

    assert ticket.review_reason is not None
    assert "evacuation capacity override" in ticket.review_reason


async def test_the_review_reason_names_a_score_that_left_its_range(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """A departure from the derived range is reported, not rejected."""
    bounds = derive_urgency(likelihood=4, impact=6, safety_critical=False)
    assert not bounds.contains(2)

    client, _ = _wire(keyed_client, settings, _answers(response, urgency=2))
    ticket = await triage_finding(client, enriched()[0])

    assert ticket.review_reason is not None
    assert f"outside the derived range of {bounds}" in ticket.review_reason


async def test_the_review_reason_names_a_redundancy_the_batch_contradicts(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, _ = _wire(keyed_client, settings, _answers(response))
    items = enriched(
        findings=[
            {"finding_id": "F-9001", "equipment_id": "XX-0001"},
            {"finding_id": "F-9002", "equipment_id": "XX-0002"},
        ],
        equipment=[
            {"equipment_id": "XX-0001", "redundancy": "Duplicated (XX-0002)"},
            {"equipment_id": "XX-0002", "redundancy": "Duplicated (XX-0001)"},
        ],
    )
    ticket = await triage_finding(client, items[0])

    assert ticket.review_reason is not None
    assert "XX-0002 also carries a finding in this batch" in ticket.review_reason


async def test_the_review_reason_names_an_unresolved_partner(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, _ = _wire(keyed_client, settings, _answers(response))
    ticket = await triage_finding(
        client, enriched(equipment=[{"redundancy": "N+1 (XX-9999)"}])[0]
    )

    assert ticket.review_reason is not None
    assert "XX-9999 has no registry row" in ticket.review_reason


async def test_the_review_reason_names_a_safety_critical_element(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, _ = _wire(keyed_client, settings, _answers(response))
    ticket = await triage_finding(
        client, enriched(equipment=[{"safety_critical_element": "Yes"}])[0]
    )

    assert ticket.review_reason is not None
    assert "Safety Critical Element" in ticket.review_reason


async def test_the_batch_keeps_input_order_and_counts_itself(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    client, _ = _wire(keyed_client, settings, _answers(response))
    items = enriched(
        findings=[{"finding_id": f"F-900{n}"} for n in (1, 2, 3)],
    )
    document = await triage_batch(client, items)

    assert [t.finding_id for t in document.tickets] == ["F-9001", "F-9002", "F-9003"]
    assert [t.ticket_id for t in document.tickets] == ["TKT-9001", "TKT-9002", "TKT-9003"]
    assert document.tickets_generated == 3
    assert document.generated_at.tzinfo is not None


async def test_an_empty_batch_is_an_empty_document(
    settings: Settings, keyed_client: Client, response: Response
) -> None:
    client, _ = _wire(keyed_client, settings, _answers(response))
    document = await triage_batch(client, [])

    assert document.tickets == []
    assert document.tickets_generated == 0


async def test_a_failing_pass_records_every_finding_it_failed_on(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """A broken run is still a document, and it says which findings have no ticket."""
    client, _ = _wire(
        keyed_client,
        settings,
        _answers(response, replace={URGENCY: response(refusal="Synthetic refusal.")}),
    )
    items = enriched(findings=[{"finding_id": "F-9001"}, {"finding_id": "F-9002"}])

    document = await triage_batch(client, items)

    assert document.tickets == []
    assert document.findings_failed == 2
    assert sorted(f.finding_id for f in document.failures) == ["F-9001", "F-9002"]
    assert {f.error for f in document.failures} == {"RefusalError"}


async def test_a_batch_keeps_the_tickets_it_did_produce(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """A finding that fails does not take its siblings' tickets with it.

    Their calls have already been made by the time it fails; throwing them away
    would cost the run and tell a reader less than keeping them does.
    """
    stub = _FailsOneFinding(
        keyed_client(_answers(response)),
        "Doomed.",
        RefusalError("Synthetic refusal."),
    )
    client = TriageClient(stub, settings())
    items = enriched(
        findings=[
            {"finding_id": "F-9001", "finding_description": "Fine."},
            {"finding_id": "F-9002", "finding_description": "Doomed."},
        ]
    )

    document = await triage_batch(client, items)

    assert [ticket.finding_id for ticket in document.tickets] == ["F-9001"]
    assert [failure.finding_id for failure in document.failures] == ["F-9002"]
    assert (document.tickets_generated, document.findings_failed) == (1, 1)


async def test_the_configured_ceiling_is_what_bounds_the_batch(
    settings: Settings, keyed_client: Client, response: Response, enriched: Enriched
) -> None:
    """The ceiling counts findings, not requests.

    At a ceiling of one, a finding's whole five-pass pipeline — its three-way
    fan-out included — finishes before the next finding starts.
    """
    client, stub = _wire(keyed_client, settings, _answers(response), max_concurrency=1)
    items = enriched(
        findings=[
            {"finding_id": "F-9001", "finding_description": "First."},
            {"finding_id": "F-9002", "finding_description": "Second."},
        ]
    )
    await triage_batch(client, items)

    sent = [
        json.loads(call["input"][0]["content"])["finding_description"]
        for call in stub.calls
    ]
    assert sent == ["First."] * len(PASSES) + ["Second."] * len(PASSES)
