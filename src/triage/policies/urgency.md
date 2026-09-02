---
version: 1.1
author: Mathieu Nguyen
date: 2026-09-02
---

## Definition
Not an average of likelihood and impact, and not the maximum, though the maximum is closer. A low-likelihood, high-impact finding on an SCE still requires attention this week. A near-certain failure of something inconsequential can wait for the next shutdown. 

**Urgency** expresses how soon a human must act.

## Scoring scale
* 9–10: today
* 7–8: this week
* 5–6: this month
* 3–4: next planned shutdown
* 1–2: backlog

## Override conditions
1. Anything that leaves a protection layer impaired without a recorded deviation is immediate, because the installation is out of compliance from the point the impairment is known.
2. Anything that reduces evacuation capacity below the POB (Personal On Board) count. It means that the safety of people working on the offshores is at risk in case of emergency.

## How likelihood and impact combine

Impact sets the anchor and likelihood moves it. What happens if the item fails decides roughly how soon someone must act; how likely that failure is moves the answer up or down from there. The asymmetry is deliberate, and it is what separates urgency from an average: a remote failure of something catastrophic outranks a certain failure of something trivial.

Three limits hold at the edges.

* **Something inconsequential can wait**, however certain the failure. A near-certain failure with a trivial consequence belongs at the next planned shutdown, not sooner.
* **A remote failure is not today's problem** on the derived assessment alone. Where likelihood is low, this week is as soon as it reaches without an override.
* **An SCE consequence does not slip past this week.** Where the item is a Safety Critical Element and the consequence of its failure is severe, low likelihood does not push it out to next month.

## What counts as an impairment

A protection layer can be impaired while it is still working. One dead detector head in a 2oo3 group is a degradation of the arrangement rather than its defeat, which is why the consequence of the failure is moderate — and it is an impairment of that layer from the moment it is known, which is what the first override condition turns on.

The two readings are not in conflict. One is about how bad the failure would be; the other is about whether the installation is compliant right now. A voted arrangement's surviving margin is not a reason the override does not apply.

## When the evidence is not in the record

Neither override condition can be confirmed from the inputs. There is no deviation register and no POB figure among them.

* Where a finding leaves a protection layer impaired, nothing in the inputs records a deviation against it. Treat the impairment as undeclared and the condition as met.
* Where a finding reduces evacuation capacity, the margin against POB cannot be checked from here. Treat the condition as met, and say plainly that the margin was not verifiable rather than implying it was.

Neither of these is an invitation to reach for an override. The question they answer is what to do once a finding is already known to impair a protection layer or to reduce evacuation capacity. Where it does neither, none of this applies.

## How far an override goes

An override makes the finding immediate: the top band, today. It does not flatten every such finding to the same number. The very top of that band is for a protection layer that is defeated, or one with no margin left to lose. A layer that is degraded but still performing its function sits just below it.
