# inspection-finding-triage

Takes offshore inspection findings, enriches them with the equipment registry, and produces a
structured triage ticket per finding: likelihood, impact and urgency (each 1–10 with a rationale), a
summary, a recommended action, and a human-review flag.

## Status

Runnable end to end. In place: the Pydantic model layer, the registry layer (CSV loading, the
findings-to-equipment join, the batch redundancy index), the LLM layer — the async structured
call, run configuration, and the loaders that assemble prompts from the policy files — the four
policies and five prompts themselves, the urgency derivation, the triage layer that runs the five
passes over a batch and assembles the tickets, and the CLI that ties them together.

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

## Run

Two CSVs in, one ticket document out:

```bash
uv run triage data/inspection_findings.csv data/equipment_registry.csv
```

The paths are arguments rather than defaults — the files under `data/` are two inputs the system
can be run against, not the system's subject. Output goes to `tickets.json`; `--out PATH` sends it
elsewhere and `--out -` sends it to stdout.

Before the first real run, rehearse it for free:

```bash
uv run triage data/inspection_findings.csv data/equipment_registry.csv --dry-run
```

`--dry-run` resolves the settings, loads both files and joins them, reports what it would triage —
and returns without building a client. It proves the `.env`, the CSVs and the registry join at no
cost.

A finding costs five model calls, so `--limit N` bounds what a run spends while the output is still
being looked at. `-v` logs each request, `-vv` adds token usage. A failure — a malformed CSV, a
finding with no registry row, a batch with failures in it — prints one message naming everything
that went wrong and exits 1.

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
  cli.py           # entry point: CSVs in, tickets out
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
