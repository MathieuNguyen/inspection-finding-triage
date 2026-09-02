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
- Structured-output schemas are a strict JSON Schema subset and **bounds are not enforced** —
  neither `Field(ge=1, le=10)` nor a `max_length` string constraint constrains the model. State the
  bound in the field description, which the model reads, and enforce it in a `@field_validator`
  after parsing, so an overrun is something `max_output_attempts` can re-ask on. `ScoreBlock.score`
  and `TicketTextBlock.text` are both built this way.
- Every field must be required. Use explicit `X | None` unions rather than optional fields, and put
  the scoring guidance in `Field(description=...)` — the model reads it.

## Layout

```
src/triage/
  models/        # Pydantic models: Finding, Equipment, Ticket + the blocks each pass authors
  registry.py    # load + validate the CSVs, join findings to equipment, index the batch
  urgency.py     # derive the urgency range a likelihood and an impact imply
  llm/           # settings, exceptions, the structured call, prompt + policy loading
  policies/      # the triage guidance as markdown — the scoring rules the model reads
  prompts/       # prompt templates, one {placeholder} per policy they compose in
  triage.py      # the five passes, the ticket assembly, the review flag
  cli.py         # entry point: CSVs in, tickets out
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
the other. Braces in prompt text must be doubled. Front matter is stripped from both directories
before the text reaches the model.

A template's only placeholders are policy slots. A finding's own data goes to the model as
`user_input`, so a prompt *names* the fields it will be handed rather than interpolating them —
that keeps `instructions` byte-identical across a batch, which is what `prompt_cache_key` needs to
be worth passing. Prompts frame, policies judge: a prompt states the task, names its inputs and
states the output contract, and never restates a rule a policy already carries.
`src/triage/prompts/README.md` holds the per-file placeholder table.

`triage.py` is the layer that calls all of the above. Five passes in three stages: summary,
likelihood and impact go out together; urgency waits for both scores and the range `urgency.py`
derives from them; the recommended action waits for the urgency it is scheduling against. One
`user_input` builder per pass, each mirroring the field list its prompt names — a builder that
gains a field the prompt does not mention is the failure `tests/test_triage.py` exists to catch.
`_POLICY_SLOTS` states the prompt-to-policy table once instead of at five call sites, and the
cache key names the pass and nothing else, because the prefix worth caching is the policy text
every finding in the run shares.

`cli.py` composes and does not decide. It reads argv, resolves `LlmSettings`, calls the registry
loaders and `triage_batch`, and serialises the result — no scoring rule, and no default path into
`data/`, because those two files are inputs the system can be run against rather than its subject.
`--limit` slices **after** the join, so a bounded run still has the whole batch's redundancy index
behind it. `--dry-run` resolves the settings and does the loading and the join, then returns before
a client is built, which is what makes the wiring checkable for free. The SDK client arrives
through `main`'s `build` seam for the same reason `TriageClient` takes rather than makes one. Every
error the layers below raise already names everything that went wrong, so `main` prints it and
returns 1 rather than rewording it or letting a traceback out; `PolicyError` and `PromptError` are
`ValueError` rather than `LlmError` and have to be caught by name.

`triage_batch` runs `map_bounded` over the enriched findings and returns a `TicketDocument`, whose
validators are the batch-scope checks — the count, and no duplicated ticket or finding id. The
ceiling counts **findings, not requests**: a finding's three-way fan-out sits inside one slot, so
requests in flight can reach three times `max_concurrency` at that step. `ticket_id` mirrors the
finding number (`F-1005` becomes `TKT-1005`), so rerunning a subset does not renumber tickets that
did not change. `Ticket.urgency` is narrowed from `UrgencyBlock` to a plain `ScoreBlock`
explicitly, rather than left to serialisation to drop the override.

**Review is unconditional for now**: every ticket carries `review_required=True`, because none of
them reaches the work queue without a human approving it. `review_reason` is not a constant,
though — it opens with the standing rule and then names whatever is worth looking at first on that
ticket: an override that fired, a score that left its derived range, a redundancy claim this batch
contradicts, a partner with no registry row, a Safety Critical Element. Those notes are facts about
how the ticket was produced, not scoring rules; the reasoning behind each stays in the policy that
produced it.

## Read-only inputs — schema only, never content

`data/` and `reference/` are **read-only**. Nothing in the codebase writes to them.

- `data/inspection_findings.csv`, `data/equipment_registry.csv` — use the **column names and types**
  to shape the Pydantic models and the prompts' field lists. The **row content is off limits** as a
  source of logic: no hard-coded equipment IDs, no rules reverse-engineered from specific rows, no
  test fixtures copied from them. They are two sample inputs for running the system, nothing more.
- `reference/example_ticket.json` — defines the **output structure and the expected depth of the
  rationale fields**. Its scores and wording are one defensible assessment, not a reference answer;
  never encode them or assert against them.

Anything that would make the system score these 21 findings well but a 22nd finding badly is a bug.

## Domain knowledge

**Decided:** the notes are encoded as **markdown policy files in model context**, one per
dimension, in `src/triage/policies/` — `likelihood.md`, `impact.md`, `urgency.md`, `errors.md`.
Those four files are the only triage guidance that reaches the model.

`reference/domain_knowledge.md` is the read-only source they were derived from and is **not read
at run time**. One authoritative copy per dimension is the whole point: where the two differ, the
policy files are what the system does. Never retype either into source.

Editing a policy is a markdown edit — no code change, no schema change. Each file carries `---`
front matter recording version, author and date; that is where a change of guidance is recorded.

**Urgency is the one dimension with arithmetic behind it.** `urgency.py` turns a likelihood and an
impact into the *range* they imply — impact anchors, likelihood moves it, three limits bound the
result — and the model scores inside that range, writes the rationale and applies the overrides.
The numbers live in `urgency.py`; the reasoning for them lives in `urgency.md`. Neither restates the
other, so there is still one authoritative copy of each. The range is advisory: `UrgencyBounds.contains`
says whether the model stayed inside it, and a departure is a review flag rather than a rejection.
`UrgencyBlock.override` names which override condition fired, and a validator holds an override to
`URGENCY_OVERRIDE_FLOOR`. `Ticket.urgency` stays a plain `ScoreBlock` — which override fired is how
the number was reached, not part of the delivered shape.

Non-negotiable, and all four must reach the model. The policy text carries the first three; the
fourth is an output requirement rather than a scoring rule, so `scoring_likelihood.md` and
`scoring_impact.md` state it and no policy file does:

- `reliability_score` is inverted relative to likelihood (10 = highly reliable). Getting this
  backwards is the single most common failure.
- The two urgency overrides — an impaired protection layer without a recorded deviation, and reduced
  evacuation capacity below POB — force immediate urgency, whatever the derived score says. Neither
  is confirmable from the inputs — there is no deviation register and no POB figure — so `urgency.md`
  says what to do about that rather than leaving the model to guess differently each run. A protection
  layer can be impaired while still functioning, which is why one dead head in a 2oo3 group fires the
  override even though it is a degradation rather than a defeat for impact.
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

The suite is offline and needs no API key: `tests/conftest.py` supplies hand-written stubs
(`stub_client`, `keyed_client`, `response`, `invalid_output`) and a `settings` factory that never
reads the environment or a `.env`. No mocking library — a stub records what was sent, because the
outgoing request is part of the contract. `stub_client` answers in call order, which is right for
one call and unusable for three that go out together; `keyed_client` answers by
`prompt_cache_key`, so a triage test says what each pass replies rather than what order the passes
happened to run in. The `enriched` factory builds `EnrichedFinding`s from the same synthetic rows
through the real `registry.join`. Async tests need no marker; `asyncio_mode = "auto"`.

`tests/test_cli.py` keeps the entry point offline the same way: the stub goes in through `main`'s
`build` argument, and an autouse fixture moves the run into `tmp_path` and sets a synthetic key, so
`LlmSettings` finds no `.env` and a developer's own key is never what the suite runs against. Its
one local stub, `ClosingStub`, wraps a shared one to add the `close` that `main` calls — the shared
stubs have no reason to carry it.

`tests/test_urgency.py` departs from the synthetic-rows pattern only in having no rows: the
derivation is pure arithmetic over 200 combinations, so it asserts invariants across the whole grid
— ordering, monotonicity in both dimensions, and each of the three limits — rather than picking
examples.

Nothing asserts on what a policy *says*. That text is going to be rewritten as the judgement
behind it changes, and a test pinning its wording would be friction the file-based arrangement
exists to remove.
