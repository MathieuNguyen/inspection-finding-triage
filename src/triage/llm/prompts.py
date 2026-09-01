"""Assemble the text sent to the model.

Two directories of markdown, one function that puts them together:

* ``src/triage/policies`` — the triage guidance, one file per dimension. This is
  the maintained record of how findings are judged; editing it needs no code
  change.
* ``src/triage/prompts`` — the prompt templates, with a ``{placeholder}`` slot
  per policy they compose in. The finding's own data does not go here: it
  reaches the model as ``user_input``, which keeps the instructions identical
  across a batch and therefore cacheable.

:func:`build_prompt` fills a template with whatever the caller passes it.

Placeholders are filled with :meth:`str.format`, so a literal brace in prompt
text must be doubled — ``{{`` and ``}}``.

Files in both directories carry ``---`` front matter recording version, author
and date. That is for whoever maintains the file, so it is stripped before the
text reaches the model.
"""

from __future__ import annotations

import logging
from functools import cache
from importlib.resources import files

from triage.llm.exceptions import PolicyError, PromptError

logger = logging.getLogger(__name__)

_PACKAGE = "triage"
_POLICIES = "policies"
_PROMPTS = "prompts"


def _read(directory: str, name: str) -> str:
    """The text of ``<directory>/<name>.md``."""
    resource = files(_PACKAGE).joinpath(directory, f"{name}.md")
    return resource.read_text(encoding="utf-8")


def _strip_front_matter(text: str) -> str:
    """Drop a leading ``---`` block. It is maintenance metadata, not guidance."""
    if text.startswith("---\n"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    return text.strip()


@cache
def load_policy(name: str) -> str:
    """The triage guidance for one dimension, front matter removed.

    Cached, so a batch is scored against one reading of the file rather than
    re-reading it per finding.
    """
    try:
        text = _strip_front_matter(_read(_POLICIES, name))
    except (FileNotFoundError, OSError) as exc:
        raise PolicyError(f"no policy at {_POLICIES}/{name}.md") from exc

    if not text:
        logger.warning("Policy %r is empty.", name)
    return text


@cache
def load_prompt(name: str) -> str:
    """One prompt template, unfilled and with its front matter removed."""
    try:
        return _strip_front_matter(_read(_PROMPTS, name))
    except (FileNotFoundError, OSError) as exc:
        raise PromptError(f"no prompt at {_PROMPTS}/{name}.md") from exc


def build_prompt(name: str, /, **values: object) -> str:
    """The named prompt with ``values`` substituted in.

    A missing or misspelt placeholder raises rather than reaching the model as
    literal ``{name}`` text.
    """
    template = load_prompt(name)
    if not template:
        raise PromptError(f"prompt {name!r} is empty; write {_PROMPTS}/{name}.md")
    try:
        return template.format(**values)
    except KeyError as exc:
        raise PromptError(f"prompt {name!r} needs a value for {exc}") from exc


__all__ = ["build_prompt", "load_policy", "load_prompt"]
