---
version: 1.1
author: Mathieu Nguyen
date: 2026-09-02
---

## Definition

**Likelihood of failure `likelihood_of_failure` (1–10).** 
Probability that the item fails to perform its function in the near term, given the evidence in this finding. A confirmed functional failure that has already occurred sits at the top of the range. `reliability_score` is a prior, not the answer, and runs in the opposite direction.

**Likelihood** concerns the item itself: given what the inspection found, how likely is it to stop performing its function in the near term. A hairline coating blister on a thick-walled vessel is low likelihood even on a critical vessel. A bearing with a vibration trend that has not plateaued is high likelihood even on a spare pump.

## What moves likelihood

**Up**: a trend that is still moving; a repeat of a failure that has already occurred this period; an active, unmitigated mechanism (corrosion under wet insulation is progressing now); detection by a method that only catches late-stage damage — a finding detected by ear or smell is further advanced than one detected by UT.

**Down**: design margin; a measurement inside its acceptance criterion; an item that is out of service and not required to be in service.