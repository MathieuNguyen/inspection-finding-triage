"""Load the triage policies and compose them into prompt context.

The policies live as markdown in ``src/triage/policies``, one file per dimension.
They are the *only* triage text that reaches the model: no rule is stated in
Python, and ``reference/domain_knowledge.md`` is not read at runtime. It is the
read-only source these files were derived from, kept for provenance.

That is the whole point of the arrangement. Changing how impact is judged is an
edit to ``impact.md`` by whoever owns the judgement, with no code change, no
release, and one authoritative copy of the text.

A file that is missing is a packaging fault and raises. A file that is *empty*
only warns: the four ship empty, and the layer has to import, test and run
before a word of policy is written.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from functools import cache
from hashlib import sha256
from importlib.resources import files

from triage.llm.exceptions import PolicyError

logger = logging.getLogger(__name__)

_PACKAGE = "triage"
_DIRECTORY = "policies"
FINGERPRINT_LENGTH = 12


class Policy(StrEnum):
    """One policy document. The value is the filename stem."""

    LIKELIHOOD = "likelihood"
    """How likely the item is to stop performing its function."""

    IMPACT = "impact"
    """What happens if it does."""

    URGENCY = "urgency"
    """How soon a human must act, including the overrides."""

    ERRORS = "errors"
    """The recurring assessment mistakes, stated so they can be avoided."""

    @property
    def title(self) -> str:
        """The heading this policy is filed under in a bundle."""
        return self.value.capitalize()


@cache
def load_policy(policy: Policy) -> str:
    """The text of one policy file, trailing whitespace stripped.

    Cached: the text is read once per process and reused across every finding in
    a batch. A file edited mid-run is not picked up, which is the behaviour you
    want — a batch is scored against one version of the policy.
    """
    resource = files(_PACKAGE).joinpath(_DIRECTORY, f"{policy.value}.md")
    try:
        text = resource.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError) as exc:
        raise PolicyError(f"policy file for {policy.value!r} is unreadable: {exc}") from exc

    if not text:
        logger.warning(
            "Policy %r is empty; the model will be given no guidance on it.", policy.value
        )
    return text


def policy_bundle(*policies: Policy) -> str:
    """The named policies concatenated under stable headings, in the order given.

    The order is the caller's, not the enum's, so a prompt controls the sequence
    the model reads. Empty policies still contribute their heading: a visibly
    blank section is easier to notice than a silently absent one.
    """
    return "\n\n".join(f"## {p.title}\n\n{load_policy(p)}".rstrip() for p in policies)


def policy_fingerprint(*policies: Policy) -> str:
    """A short digest of the exact policy text behind a run.

    Log this once per run and a ticket can be traced to the wording that produced
    it. The notes name "the same finding scored differently on different days" as
    a leading cause of lost confidence in a triage output; without a fingerprint,
    a scoring change and a policy edit are indistinguishable after the fact.
    """
    digest = sha256(policy_bundle(*policies).encode("utf-8"))
    return digest.hexdigest()[:FINGERPRINT_LENGTH]


__all__ = [
    "FINGERPRINT_LENGTH",
    "Policy",
    "load_policy",
    "policy_bundle",
    "policy_fingerprint",
]
