# inspection-finding-triage

Takes offshore inspection findings, enriches them with the equipment registry, and produces a
structured triage ticket per finding: likelihood, impact and urgency (each 1–10 with a rationale), a
summary, a recommended action, and a human-review flag.

## Status

Work in progress. In place: the Pydantic model layer, the registry layer (CSV loading, the
findings-to-equipment join, the batch redundancy index), the LLM layer — the async structured
call, run configuration, and the loaders that assemble prompts from the policy files — the four
policies and five prompts themselves, the urgency derivation, and the triage layer that runs the
five passes over a batch and assembles the tickets.

The CLI is not built, so there is no end-to-end run command yet: `triage_batch` returns the
`TicketDocument` a caller writes out.

## Setup

The project uses [uv](https://docs.astral.sh/uv/). No manual virtualenv step is needed — `uv run`
creates and syncs `.venv` from `uv.lock` on demand.

```bash
uv sync
```

Then copy the environment template and add a key:

```bash
cp .env.example .env
```

`.env` is gitignored. `.env.example` documents every setting: the model, the two reasoning
budgets, the concurrency ceiling and the two retry budgets.

## Tests

```bash
uv run pytest
```

## Layout

```
src/triage/
  models/
    fields.py      # shared primitives: ID patterns, score range, text limits, closed vocabularies
    inputs.py      # Finding, Equipment — one model per CSV row
    redundancy.py  # Redundancy — structure parsed from a free-text registry column
    outputs.py     # ScoreBlock, Ticket, TicketDocument — the shape of tickets.json
  registry.py      # load + validate the CSVs, join findings to equipment, index the batch
  urgency.py       # derive the urgency range a likelihood and an impact imply
  triage.py        # the five passes, the ticket assembly, the review flag
  llm/
    settings.py    # LlmSettings, Effort — model, reasoning budgets, limits, all from the env
    exceptions.py  # what the layer raises; a batch reports every failure together
    client.py      # TriageClient.structured, map_bounded — the only network calls
    prompts.py     # load the policy and prompt markdown, assemble one into the other
  policies/        # likelihood, impact, urgency, errors — the only rules the model sees
  prompts/         # summary, scoring_likelihood/impact/urgency, actions
tests/
  models/          # mirrors src/triage/models/
  llm/             # mirrors src/triage/llm/
data/              # read-only inputs
reference/         # read-only: domain knowledge notes, example ticket
```

`OPENAI_API_KEY` is read from the environment or a gitignored `.env`.

## Triage rules

How findings are scored lives in `src/triage/policies/` as markdown — one file per dimension, no
scoring rule in Python. Changing a judgement is a text edit by whoever owns it, with no code
change and no release. See `src/triage/policies/README.md`.
