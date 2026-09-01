"""Load prompt templates and fill them in.

A prompt is a markdown file in ``src/triage/prompts`` plus a :class:`PromptSpec`
declaring three things about it: which policies it injects, which variables it
expects, and how hard the model should think when running it. The spec is the
contract; the markdown is the wording. Rewording is a text edit, and changing the
contract is a deliberate edit in two places that the checks below insist agree.

**Placeholders are ``$name``, not ``{name}``.** Prompt text carries JSON examples
and brace-heavy structure, and :meth:`str.format` would choke on every brace. A
literal ``$`` in prose must be written ``$$``.

``$policies`` is reserved. A prompt writes it where the triage guidance belongs
and the bundle is assembled automatically from :attr:`PromptSpec.policies`; there
is nothing to wire up at the call site.

The two prompts ship empty, so the checks are staged. A spec naming a missing
file fails at import. A spec whose variables disagree with its markdown fails as
soon as the markdown has any text in it. An empty prompt imports and tests
cleanly but refuses to render, because sending a blank instruction to the model
is never what was meant.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum
from importlib.resources import files
from string import Template
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from triage.llm.exceptions import PromptError
from triage.llm.policies import Policy, policy_bundle
from triage.llm.settings import Effort

logger = logging.getLogger(__name__)

_PACKAGE = "triage"
_DIRECTORY = "prompts"

RESERVED_VARIABLE = "policies"
"""Filled from the spec's policies, never passed by a caller."""


class PromptName(StrEnum):
    """One prompt template. The value is the filename stem."""

    EXTRACTION = "extraction"
    """Pull structured facts out of ``finding_description``."""

    SCORING = "scoring"
    """Turn an enriched finding into a scored ticket."""


class PromptSpec(BaseModel):
    """What a prompt file is allowed to contain and how it is run.

    Frozen and ``extra="forbid"`` for the same reason the registry models are:
    this is a declaration, and a typo in it should fail loudly at import rather
    than quietly at the first call.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: PromptName
    policies: tuple[Policy, ...] = ()
    variables: frozenset[str] = frozenset()
    effort: Effort

    @model_validator(mode="after")
    def _file_exists(self) -> Self:
        if not self.resource().is_file():
            raise PromptError(
                f"prompt {self.name.value!r} has no file at "
                f"{_DIRECTORY}/{self.name.value}.md"
            )
        if RESERVED_VARIABLE in self.variables:
            raise PromptError(
                f"prompt {self.name.value!r} declares the reserved variable "
                f"${RESERVED_VARIABLE}, which is filled from its policies"
            )
        return self

    def resource(self):  # noqa: ANN201 - importlib.resources.abc.Traversable
        """The markdown file backing this prompt."""
        return files(_PACKAGE).joinpath(_DIRECTORY, f"{self.name.value}.md")

    def text(self) -> str:
        """The raw template text."""
        return self.resource().read_text(encoding="utf-8").strip()

    @property
    def expected_variables(self) -> frozenset[str]:
        """Every placeholder the markdown is allowed to use.

        The declared variables, plus ``$policies`` when the spec injects any.
        """
        if self.policies:
            return self.variables | {RESERVED_VARIABLE}
        return self.variables


PROMPTS: Mapping[PromptName, PromptSpec] = {
    PromptName.EXTRACTION: PromptSpec(
        name=PromptName.EXTRACTION,
        policies=(Policy.LIKELIHOOD, Policy.IMPACT),
        variables=frozenset({"finding"}),
        effort=Effort.WRITING,
    ),
    PromptName.SCORING: PromptSpec(
        name=PromptName.SCORING,
        policies=(Policy.LIKELIHOOD, Policy.IMPACT, Policy.URGENCY, Policy.ERRORS),
        variables=frozenset({"finding", "equipment", "redundancy"}),
        effort=Effort.JUDGING,
    ),
}
"""The declared prompts.

Extraction reads the likelihood and impact policies because they are what say
which details in a finding matter — a measurement, a repeat, how it was
detected. Scoring reads all four.
"""


def placeholders(text: str, *, label: str = "prompt") -> frozenset[str]:
    """Every ``$name`` the text uses.

    Takes the text rather than a spec so the rule can be exercised directly,
    without a file on disk to carry the example.
    """
    template = Template(text)
    if not template.is_valid():
        raise PromptError(
            f"{label} contains a malformed placeholder; "
            "write a literal dollar sign as '$$'"
        )
    return frozenset(template.get_identifiers())


def check_placeholders(
    text: str, expected: frozenset[str], *, label: str = "prompt"
) -> None:
    """Raise unless the text uses exactly the placeholders ``expected`` names.

    Both directions matter. A placeholder nobody declared is never filled and
    reaches the model as a literal ``$name``. A declared variable the text never
    uses is a value assembled at the call site and silently dropped — the failure
    where a prompt looks right and quietly ignores half its input.
    """
    used = placeholders(text, label=label)
    if used == expected:
        return

    problems = []
    if undeclared := sorted(used - expected):
        problems.append(f"uses undeclared {', '.join('$' + v for v in undeclared)}")
    if unused := sorted(expected - used):
        problems.append(f"declares unused {', '.join('$' + v for v in unused)}")
    raise PromptError(f"{label} {' and '.join(problems)}")


def check_prompt(spec: PromptSpec) -> None:
    """Check a declared prompt against its markdown.

    An unwritten prompt is skipped rather than failed, so the scaffold holds
    until the text is authored. From the first word onwards it is enforced.
    """
    text = spec.text()
    if not text:
        logger.warning("Prompt %r is empty; it cannot be rendered yet.", spec.name.value)
        return
    check_placeholders(text, spec.expected_variables, label=f"prompt {spec.name.value!r}")


def render_prompt(name: PromptName, /, **values: str) -> str:
    """The prompt with its policies and values substituted in.

    ``$policies`` is filled from the spec. Every other placeholder must be
    supplied here, and supplying one the spec does not declare is an error rather
    than something quietly ignored.
    """
    spec = PROMPTS[name]
    text = spec.text()
    if not text:
        raise PromptError(
            f"prompt {name.value!r} is empty; write {_DIRECTORY}/{name.value}.md "
            "before running it"
        )
    check_prompt(spec)

    supplied = frozenset(values)
    if missing := sorted(spec.variables - supplied):
        raise PromptError(
            f"prompt {name.value!r} is missing "
            f"{', '.join('$' + v for v in missing)}"
        )
    if unknown := sorted(supplied - spec.variables):
        raise PromptError(
            f"prompt {name.value!r} does not take {', '.join(unknown)}"
        )

    substitutions = dict(values)
    if spec.policies:
        substitutions[RESERVED_VARIABLE] = policy_bundle(*spec.policies)
    return Template(text).substitute(substitutions)


__all__ = [
    "PROMPTS",
    "RESERVED_VARIABLE",
    "PromptName",
    "PromptSpec",
    "check_placeholders",
    "check_prompt",
    "placeholders",
    "render_prompt",
]
