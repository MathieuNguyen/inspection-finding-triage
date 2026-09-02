"""Run configuration: which model, how hard it thinks, how many calls at once.

Everything here comes from the environment or a gitignored ``.env``, so a
deployment is retuned without a code change. The defaults in this file are the
intended production values, not placeholders.

The reasoning budget is chosen per *kind of work* rather than per call site.
:class:`Effort` names the two kinds; :attr:`LlmSettings.writing_effort` and
:attr:`LlmSettings.judging_effort` say what each one costs. A pass asks for
``Effort.JUDGING`` and never mentions ``"high"``, so raising the scoring budget
is one environment variable rather than a search through the call sites.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

EffortLevel = Literal["minimal", "low", "medium", "high", "xhigh"]
"""The reasoning efforts this project uses.

The SDK also accepts ``"none"`` and ``"max"``. Neither is offered here: ``none``
disables the reasoning these passes depend on, and ``max`` is not worth its cost
on work this narrow.
"""


class Effort(StrEnum):
    """Which reasoning budget a call gets.

    The distinction is what the model is being asked to do, not which pass is
    calling. Writing prose from established facts is cheaper than deciding what
    a finding means.
    """

    WRITING = "writing"
    """Summaries and recommended actions. Reading and rephrasing."""

    JUDGING = "judging"
    """Scoring. Weighing evidence to reach a defensible number."""


class LlmSettings(BaseSettings):
    """Everything the LLM layer needs to run, resolved from the environment.

    Every field except the API key is read with a ``TRIAGE_`` prefix, so the
    project's own configuration is distinguishable from the provider's at a
    glance in a shell or a container spec.
    """

    model_config = SettingsConfigDict(
        env_prefix="TRIAGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    openai_api_key: SecretStr = Field(
        validation_alias="OPENAI_API_KEY",
        min_length=1,
        description=(
            "Read unprefixed, under the name the OpenAI SDK itself uses. Rejected "
            "when blank: .env.example ships it empty, and a copied-but-unfilled "
            "key should fail here rather than as an opaque 401 mid-run."
        ),
    )
    model: str = Field(
        default="gpt-5.6-luna",
        description="The flagship model for every pass. Cheap enough to use throughout.",
    )
    writing_effort: EffortLevel = Field(
        default="medium", description="Reasoning budget for Effort.WRITING."
    )
    judging_effort: EffortLevel = Field(
        default="high", description="Reasoning budget for Effort.JUDGING."
    )
    max_concurrency: int = Field(
        default=6,
        ge=1,
        description=(
            "How many findings are assessed at once. Counts findings rather than "
            "requests: a finding's three concurrent passes sit inside one slot."
        ),
    )
    request_timeout: float = Field(
        default=120.0, gt=0, description="Seconds before a single request is abandoned."
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description=(
            "Transport retries, applied by the SDK on 429s, 5xx and dropped "
            "connections. Not the same budget as max_output_attempts."
        ),
    )
    max_output_attempts: int = Field(
        default=3,
        ge=1,
        description=(
            "Total attempts at a usable answer, counting the first. Each later "
            "attempt re-asks with the validation errors from the one before."
        ),
    )

    def effort_for(self, effort: Effort) -> EffortLevel:
        """The reasoning level configured for this kind of work."""
        match effort:
            case Effort.WRITING:
                return self.writing_effort
            case Effort.JUDGING:
                return self.judging_effort


__all__ = ["Effort", "EffortLevel", "LlmSettings"]
