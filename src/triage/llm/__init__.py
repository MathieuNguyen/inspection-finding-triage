"""The layer that talks to the model, and the text it puts in front of it.

* :mod:`triage.llm.settings` — :class:`LlmSettings` and :class:`Effort`. Which
  model, how hard it thinks, how many calls at once. All from the environment.
* :mod:`triage.llm.prompts` — loads the policy and prompt markdown and assembles
  one into the other.
* :mod:`triage.llm.client` — :class:`TriageClient` and :func:`map_bounded`, the
  only code in the project that makes a network call.
* :mod:`triage.llm.exceptions` — what the layer raises.

Everything public is re-exported here: import from ``triage.llm``, not from the
submodules.

**No triage rule is written in Python.** The rules live in the markdown under
``src/triage/policies``, one file per dimension, loaded into the prompt that
needs them. ``reference/domain_knowledge.md`` is the read-only source those files
were derived from and is not read at run time.
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
from triage.llm.prompts import build_prompt, load_policy, load_prompt
from triage.llm.settings import Effort, EffortLevel, LlmSettings

__all__ = [
    "BatchError",
    "Effort",
    "EffortLevel",
    "EmptyResponseError",
    "IncompleteResponseError",
    "ItemFailure",
    "LlmError",
    "LlmSettings",
    "OutputValidationError",
    "PolicyError",
    "PromptError",
    "RefusalError",
    "TriageClient",
    "build_client",
    "build_prompt",
    "load_policy",
    "load_prompt",
    "map_bounded",
]
