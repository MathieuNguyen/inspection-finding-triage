# Triage policies

These four files are the **only** triage guidance that reaches the model. No scoring rule is written
in Python, and `reference/domain_knowledge.md` is not read at run time.

| File | Question it answers |
| --- | --- |
| `likelihood.md` | Given what the inspection found, how likely is the item to stop performing its function? |
| `impact.md` | What happens if it does? |
| `urgency.md` | How soon must a human act — including the conditions that override the derived score? |
| `errors.md` | Which recurring assessment mistakes must be avoided? |

## Provenance

Derived from `reference/domain_knowledge.md`, the handover notes from the outgoing Integrity
Engineer. That file is read-only and stays the record of where this text came from; these files are
the working copy. Where the two differ, these files are what the system actually does.

## Editing

Edit the markdown. There is no code change, no schema to update and no release step — the text is
read at import and composed into the prompt that needs it. `src/triage/llm/prompts.py` declares which
policies each prompt pulls in.

An empty file logs a warning and contributes an empty section rather than failing, so the scaffold
holds while these are being written. Nothing else validates the *content*: what a policy says is an
engineering judgement, and the code deliberately has no opinion on it.

## Traceability

`policy_fingerprint()` is a short digest of the exact text behind a run. Log it with the output and a
ticket can be traced to the wording that produced it — the difference between "the scoring changed"
and "the policy changed", which is otherwise unanswerable after the fact.
