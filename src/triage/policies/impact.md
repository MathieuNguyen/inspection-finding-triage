---
version: 1.0
author: Mathieu Nguyen
date: 2026-09-01
---

## Definition
**Impact of failure `impact_of_failure` (1–10).** 
Consequence if the failure occurs. Accounts for redundancy where it is real, for delayed and hidden consequences, and for the fact that Safety Critical Elements are judged against the major accident they protect against rather than against repair cost. `criticality_score` is a prior, not the answer.

**Impact** concerns what happens if it does fail. This depends mainly on what the equipment does and what sits behind it, not on the wording of the finding.

## What moves impact
**Up**: absence of redundancy; Safety Critical Elements, which exist because a major accident scenario depends on them and are judged against that scenario rather than against repair cost; failures that degrade a protection layer rather than causing direct loss; delayed or hidden consequences — loss of corrosion inhibitor has no effect today and a substantial effect in eighteen months; escalation potential.

**Down**: redundancy that is available and capable; items that can be bypassed without loss of function: atmospheric, non-hydrocarbon, low-energy services; consequences limited to housekeeping or appearance.