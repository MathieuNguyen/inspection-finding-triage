# inspection-finding-triage

Takes offshore inspection findings, enriches them with the equipment registry, and produces a
structured triage ticket per finding: likelihood, impact and urgency (each 1–10 with a rationale), a
summary, a recommended action, and a human-review flag.

## Status

Work in progress. The Pydantic model layer is in place; the registry join, extraction, scoring pass
and CLI are not yet built, so there is no end-to-end run command yet.

## Setup

The project uses [uv](https://docs.astral.sh/uv/). No manual virtualenv step is needed — `uv run`
creates and syncs `.venv` from `uv.lock` on demand.

```bash
uv sync
```

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
tests/
  models/          # mirrors src/triage/models/
data/              # read-only inputs
reference/         # read-only: domain knowledge notes, example ticket
```

`OPENAI_API_KEY` is read from the environment or a gitignored `.env`.
