"""The layer that talks to the model, and the text it puts in front of it.

Four concerns, one module each:

* :mod:`triage.llm.settings` — :class:`LlmSettings` and :class:`Effort`. Which
  model, how hard it thinks, how many calls at once. All from the environment.
* :mod:`triage.llm.policies` — the triage guidance, loaded from the markdown in
  ``src/triage/policies``.
* :mod:`triage.llm.prompts` — the templates, and the checks that keep each one
  honest about the variables it takes.
* :mod:`triage.llm.client` — :class:`TriageClient` and :func:`map_bounded`, the
  only code in the project that makes a network call.

:mod:`triage.llm.exceptions` holds what the layer raises. It is named
``exceptions`` rather than ``errors`` because ``policies/errors.md`` is something
else entirely — the recurring *assessment* mistakes the triage notes warn about.

Everything public is re-exported here: import from ``triage.llm``, not from the
submodules.

**No triage rule is written in Python.** The rules live in the policy markdown,
which is loaded into model context at runtime. ``reference/domain_knowledge.md``
is the read-only source those files were derived from and is not read at run
time; keeping one authoritative copy per dimension is the point. What this
package guarantees is mechanical, not editorial: that the declared text is
present, that a prompt's placeholders and its spec agree, and that the exact
wording behind a run can be identified afterwards from
:func:`policy_fingerprint`.
"""

from triage.llm.client import TriageClient, build_client, map_bounded
from triage.llm.exceptions import (
    BatchError,
    EmptyResponseError,
    IncompleteResponseError,
    ItemFailure,
    LlmError,
    OutputValidationError,
    PolicyError,
    PromptError,
    RefusalError,
)
from triage.llm.policies import (
    Policy,
    load_policy,
    policy_bundle,
    policy_fingerprint,
)
from triage.llm.prompts import (
    PROMPTS,
    PromptName,
    PromptSpec,
    check_placeholders,
    check_prompt,
    placeholders,
    render_prompt,
)
from triage.llm.settings import Effort, EffortLevel, LlmSettings

__all__ = [
    "PROMPTS",
    "BatchError",
    "Effort",
    "EffortLevel",
    "EmptyResponseError",
    "IncompleteResponseError",
    "ItemFailure",
    "LlmError",
    "LlmSettings",
    "OutputValidationError",
    "Policy",
    "PolicyError",
    "PromptError",
    "PromptName",
    "PromptSpec",
    "RefusalError",
    "TriageClient",
    "build_client",
    "check_placeholders",
    "check_prompt",
    "load_policy",
    "map_bounded",
    "placeholders",
    "policy_bundle",
    "policy_fingerprint",
    "render_prompt",
]
