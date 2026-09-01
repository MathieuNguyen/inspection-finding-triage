# Prompt templates

One file per pass. Each is the system-level instruction for a single call: what the pass
is for, what it will be handed, and what a good answer looks like. The scoring *rules* are
not here — they live in `src/triage/policies` and are composed in through a placeholder.

| File | Placeholders | Output model | Effort |
| --- | --- | --- | --- |
| `summary.md` | — | `TicketTextBlock` | `Effort.WRITING` |
| `scoring_likelihood.md` | `{likelihood_policy}` | `ScoreBlock` | `Effort.JUDGING` |
| `scoring_impact.md` | `{impact_policy}`, `{errors_policy}` | `ScoreBlock` | `Effort.JUDGING` |
| `actions.md` | `{urgency_policy}` | `TicketTextBlock` | `Effort.WRITING` |
| `scoring_urgency.md` | not yet written | `ScoreBlock` | `Effort.JUDGING` |

## Templates take policies; findings arrive separately

The only thing interpolated into a template is a policy. A finding's own data goes to the
model as `user_input`, which is why each prompt *names* the fields it will receive rather
than carrying slots for them. That split keeps `instructions` byte-identical for every
finding in a run, so `prompt_cache_key` has something stable to cache.

## Braces

Filling is `str.format`, so **every brace in a prompt is read as a placeholder**. A
literal one must be doubled — `{{` and `}}` — and a bare `{}` raises an `IndexError` that
`build_prompt` does not catch. There is no reason to write a JSON example here in any
case: the output schema comes from `text_format`.

## Front matter

Each file opens with a `---` block recording version, author and date, the same convention
as the policies and stripped the same way before the text reaches the model. A change of
wording is a version bump, not a code change.
