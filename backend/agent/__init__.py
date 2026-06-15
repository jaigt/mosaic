"""Agentic orchestration for the analyst loop.

The two standout behaviours that lift this above a plain RAG chatbot live here:

  * **Corpus autonomy** (``plan_auto_ingest``): if the user asks about a filing
    the corpus does not contain, the system fetches it from SEC EDGAR on the fly
    and re-searches, instead of dead-ending on "ingest a filing first".

  * **Grounded self-verification** (``verify_answer``): after synthesis, a critic
    pass checks the answer's claims/numbers against the retrieved sources and
    surfaces caveats — the one thing finance can't tolerate is invented numbers.

Decision helpers are pure and unit-tested; the LLM-backed ``verify_answer`` is a
thin wrapper with an injectable model function and a graceful fallback.
"""
from backend.agent.planner import (
    IngestPlan,
    VerificationResult,
    plan_auto_ingest,
    build_verification_prompt,
    parse_verification,
    verify_answer,
)
from backend.agent.react import (
    Action,
    GatherResult,
    ReactAgent,
    build_system_prompt,
    parse_action,
)

__all__ = [
    "IngestPlan",
    "VerificationResult",
    "plan_auto_ingest",
    "build_verification_prompt",
    "parse_verification",
    "verify_answer",
    # ReAct multi-tool loop
    "Action",
    "GatherResult",
    "ReactAgent",
    "build_system_prompt",
    "parse_action",
]
