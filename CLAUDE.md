# inspection-finding-triage

Takes offshore inspection findings, enriches them with the equipment registry, and produces a
structured triage ticket per finding: likelihood, impact, urgency (each 1–10 with a rationale), a
summary, a recommended action, and a human-review flag.

## Stack

- **Python 3.13** — pinned via `.python-version`, matching the system interpreter (3.13.6).
- **uv** for everything: `uv sync`, `uv run <cmd>`, `uv add <pkg>`. Deps live in `pyproject.toml`,
  locked in `uv.lock`. No `pip install`, no `requirements.txt`.
- **Pydantic v2** (latest) and **openai** (latest) — currently 2.12.x and 2.21.x. Do not write v1
  Pydantic (`@validator`, `.dict()`, `class Config`) or legacy OpenAI calls.
- `OPENAI_API_KEY` comes from the environment / a gitignored `.env`. Never hard-code or print it.

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
  extraction.py  # structured extraction from finding_description        — not built
  triage.py      # scoring pass, cross-finding checks, review-flag logic — not built
  cli.py         # entry point: CSVs in, tickets out                     — not built
tests/
  models/        # mirrors src/triage/models/
```

`registry.py` reports facts, never interpretations. `EnrichedFinding.partners_with_findings` names
the redundancy partners that also carry a finding in this batch; `unresolved_partners` names tags
with no registry row. What either means for a score is `triage.py`'s call. A malformed CSV raises
one `CsvValidationError` listing every bad line rather than failing on the first. Where
`Finding.equipment_type` disagrees with the registry the registry wins and the mismatch is logged,
not fatal.

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

`reference/domain_knowledge.md` is the only written record of how triage is done, and it must be
meaningfully encoded — not paraphrased away. Load it from the file; don't retype it into source.
**How** it is encoded (model context vs. deterministic Python) is still an open design decision —
raise it before implementing the scoring pass.

Non-negotiable regardless of mechanism:

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
