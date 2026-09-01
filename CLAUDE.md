# inspection-finding-triage

Takes offshore inspection findings, enriches them with the equipment registry, and produces a
structured triage ticket per finding: likelihood, impact, urgency (each 1–10 with a rationale), a
summary, a recommended action, and a human-review flag.

## Stack

- **Python 3.13** — pinned via `.python-version`, matching the system interpreter (3.13.6).
- **uv** for everything: `uv sync`, `uv run <cmd>`, `uv add <pkg>`. Deps live in `pyproject.toml`,
  locked in `uv.lock`. No `pip install`, no `requirements.txt`.
- **Pydantic v2** (latest) and **openai** (latest) — currently 2.13.x and 3.6.x. Do not write v1
  Pydantic (`@validator`, `.dict()`, `class Config`) or legacy OpenAI calls.
- **pydantic-settings** holds run configuration. Everything tunable is a field on `LlmSettings`,
  read from the environment with a `TRIAGE_` prefix; `.env.example` documents the full set.
- `OPENAI_API_KEY` comes from the environment / a gitignored `.env`. Never hard-code or print it.
  It is a `SecretStr`, so it stays out of reprs and log lines.
- The LLM layer is **async throughout** — `AsyncOpenAI`, and a batch runs under a concurrency
  ceiling rather than one finding at a time.

### OpenAI usage

- Use the **Responses API** with structured outputs: `client.responses.parse(model=..., input=[...],
  text_format=MyModel)` and read `response.output_parsed`. `chat.completions` and
  `beta.chat.completions.parse` are legacy — don't reach for them.
- Structured-output schemas are a strict JSON Schema subset. **Numeric bounds are not enforced**:
  `Field(ge=1, le=10)` will not constrain the model. Express ranges in the field description and
  validate them with a Pydantic `@field_validator` after parsing.
- Every field must be required. Use explicit `X | None` unions rather than optional fields, and put
  the scoring guidance in `Field(description=...)` — the model reads it.

## Layout

```
src/triage/
  models/        # Pydantic models: Finding, Equipment, Ticket + score/rationale blocks
  registry.py    # load + validate the CSVs, join findings to equipment, index the batch
  llm/           # settings, exceptions, the structured call, prompt + policy loading
  policies/      # the triage guidance as markdown — the only rules the model sees
  prompts/       # prompt templates, {placeholder} slots
  extraction.py  # structured extraction from finding_description        — not built
  triage.py      # scoring pass, cross-finding checks, review-flag logic — not built
  cli.py         # entry point: CSVs in, tickets out                     — not built
tests/
  models/        # mirrors src/triage/models/
  llm/           # mirrors src/triage/llm/
```

`registry.py` reports facts, never interpretations. `EnrichedFinding.partners_with_findings` names
the redundancy partners that also carry a finding in this batch; `unresolved_partners` names tags
with no registry row. What either means for a score is `triage.py`'s call. A malformed CSV raises
one `CsvValidationError` listing every bad line rather than failing on the first. Where
`Finding.equipment_type` disagrees with the registry the registry wins and the mismatch is logged,
not fatal.

`llm/` is the only code that makes a network call. `TriageClient.structured` is the single entry
point; `map_bounded` runs it across a batch and raises one `BatchError` naming every failure, the
same contract as `CsvValidationError`. Two retry budgets, kept apart: transport failures are the
SDK's `max_retries`, while `max_output_attempts` re-asks when a response fails *our* validation —
a score outside 1–10 is well-formed JSON that `ScoreBlock` rejects. Reasoning effort is chosen by
kind of work, `Effort.WRITING` or `Effort.JUDGING`, never by naming a level at a call site.

`prompts.py` is the whole of the prompt layer: load a policy, load a template, `.format` one into
the other. Braces in prompt text must be doubled. Policy front matter is stripped before the text
reaches the model.

## Read-only inputs — schema only, never content

`data/` and `reference/` are **read-only**. Nothing in the codebase writes to them.

- `data/inspection_findings.csv`, `data/equipment_registry.csv` — use the **column names and types**
  to shape the Pydantic models and the extraction schema. The **row content is off limits** as a
  source of logic: no hard-coded equipment IDs, no rules reverse-engineered from specific rows, no
  test fixtures copied from them. They are two sample inputs for running the system, nothing more.
- `reference/example_ticket.json` — defines the **output structure and the expected depth of the
  rationale fields**. Its scores and wording are one defensible assessment, not a reference answer;
  never encode them or assert against them.

Anything that would make the system score these 21 findings well but a 22nd finding badly is a bug.

## Domain knowledge

**Decided:** the notes are encoded as **markdown policy files in model context**, one per
dimension, in `src/triage/policies/` — `likelihood.md`, `impact.md`, `urgency.md`, `errors.md`.
Those four files are the only triage guidance that reaches the model, and no scoring rule is
written in Python.

`reference/domain_knowledge.md` is the read-only source they were derived from and is **not read
at run time**. One authoritative copy per dimension is the whole point: where the two differ, the
policy files are what the system does. Never retype either into source.

Editing a policy is a markdown edit — no code change, no schema change. Each file carries `---`
front matter recording version, author and date; that is where a change of guidance is recorded.

Non-negotiable, and the policy text must carry all four:

- `reliability_score` is inverted relative to likelihood (10 = highly reliable). Getting this
  backwards is the single most common failure.
- The two urgency overrides — an impaired protection layer without a recorded deviation, and reduced
  evacuation capacity below POB — force immediate urgency, whatever the derived score says.
- Redundancy is a claim to check, not a fact to credit. Findings against both legs of a pair in one
  batch means the pair is not redundant, so findings cannot be scored purely in isolation.
- Uncertainty is stated in the rationale, never resolved by picking a mid-range score. Uniform
  mid-range output across findings is a failure mode, not a safe default.

## Tests

`uv run pytest`. Unit tests use synthetic rows only: the factory fixtures in `tests/conftest.py`
(`finding_row`, `equipment_row`, `csv_file`) return callables taking `**overrides`, so a test states
just the field it exercises. `tests/test_schema_conformance.py` is the one place that reads `data/`
and `reference/`, and it asserts structure only — rows validate, the join is total, the example
ticket round-trips. Never assert on a score, an equipment ID, or a row count.

The suite is offline and needs no API key: `tests/llm/conftest.py` supplies hand-written stubs
(`stub_client`, `response`, `invalid_output`) and a `settings` factory that never reads the
environment or a `.env`. No mocking library — a stub records what was sent, because the outgoing
request is part of the contract. Async tests need no marker; `asyncio_mode = "auto"`.

Nothing asserts on what a policy *says*. That text is going to be rewritten as the judgement
behind it changes, and a test pinning its wording would be friction the file-based arrangement
exists to remove.
