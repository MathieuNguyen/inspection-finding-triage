# Triage policies

These four files are the **only** triage guidance that reaches the model, and
`reference/domain_knowledge.md` is not read at run time.

Scoring guidance is not written in Python. The one exception is arithmetic rather than guidance:
`src/triage/urgency.py` derives the range `urgency.md`'s limits imply for a given likelihood and
impact, and hands it to the model as an input. The reasoning behind those limits lives in
`urgency.md` and only there — the two do not restate each other.

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
read at import and composed into the prompt that needs it, by `src/triage/llm/prompts.py`.

An empty file logs a warning and contributes an empty section rather than failing, so the scaffold
holds while these are being written. Nothing else validates the *content*: what a policy says is an
engineering judgement, and the code deliberately has no opinion on it.

## Front matter

Each file opens with a `---` block recording version, author and date. That is the record of how the
guidance has changed; it is stripped before the text reaches the model.
