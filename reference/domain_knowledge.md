# Integrity and Reliability Notes — Bravo Platform

Handover notes from the outgoing Integrity Engineer. Unedited. This is the only written record of how
findings are currently triaged.

## The two questions

**Likelihood** concerns the item itself: given what the inspection found, how likely is it to stop
performing its function in the near term. A hairline coating blister on a thick-walled vessel is low
likelihood even on a critical vessel. A bearing with a vibration trend that has not plateaued is high
likelihood even on a spare pump.

**Impact** concerns what happens if it does fail. This depends mainly on what the equipment does and
what sits behind it, not on the wording of the finding.

The common error is scoring by how severe the description sounds.

## What moves likelihood

Up: a trend that is still moving; a repeat of a failure that has already occurred this period; an
active, unmitigated mechanism (corrosion under wet insulation is progressing now); detection by a
method that only catches late-stage damage — a finding detected by ear or smell is further advanced
than one detected by UT.

Down: design margin; a measurement inside its acceptance criterion; an item that is out of service
and not required to be in service.

## What moves impact

Up: absence of redundancy; Safety Critical Elements, which exist because a major accident scenario
depends on them and are judged against that scenario rather than against repair cost; failures that
degrade a protection layer rather than causing direct loss; delayed or hidden consequences — loss of
corrosion inhibitor has no effect today and a substantial effect in eighteen months; escalation
potential.

Down: redundancy that is available and capable; items that can be bypassed without loss of function;
atmospheric, non-hydrocarbon, low-energy services; consequences limited to housekeeping or appearance.

## Two recurring errors

**Voted arrangements.** One detector head out of a 2oo3 group is a degradation, not a defeat. The
arrangement still functions, so impact is moderate rather than extreme. It is time-limited, because
the group has lost its margin and the next failure defeats it.

**Redundancy is a claim, not a fact.** Check whether the redundant partner is healthy before crediting
it. If findings exist against both legs of a redundant pair in the same batch, the pair is not
redundant. Assessing each finding in isolation misses this.

## Urgency

Not an average of likelihood and impact, and not the maximum, though the maximum is closer. A
low-likelihood, high-impact finding on an SCE still requires attention this week. A near-certain
failure of something inconsequential can wait for the next shutdown. Urgency expresses how soon a
human must act.

- 9–10: today
- 7–8: this week
- 5–6: this month
- 3–4: next planned shutdown
- 1–2: backlog

Two conditions override the derived value. Anything that leaves a protection layer impaired without a
recorded deviation is immediate, because the installation is out of compliance from the point the
impairment is known. The same applies to anything that reduces evacuation capacity below the POB
count.

## Registry scores

`reliability_score` is 10 = highly reliable, 1 = frequent failures. It runs in the opposite direction
to likelihood. New starters routinely invert it. `criticality_score` runs in the expected direction,
10 = most critical.

Neither is sufficient on its own. Criticality is a starting point for impact, reliability a starting
point for likelihood; the finding text moves both. A reliable item with a crack in it is still
cracked.

## Output expectations

Maintenance planning needs two lines: what is wrong, on what, and why it matters — readable without
opening the inspection record, and not a restatement of the original finding text. Where the
assessment is uncertain, that should be stated rather than resolved by picking a mid-range score.

Recurring causes of loss of confidence in a triage output, in order:

1. Confidently incorrect scores on safety critical equipment.
2. Summaries that omit a detail that changes the decision — a measurement, a repeat occurrence, the
   fact that the standby was already unavailable.
3. The same finding scored differently on different days.
4. Uniform mid-range scores across all findings.
