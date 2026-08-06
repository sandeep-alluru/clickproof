"""clickproof — persistent GUI behavioral facts for computer-use agents."""

from __future__ import annotations

import importlib.metadata

from clickproof.analytics import DecayProjection, project_decay, stale_facts
from clickproof.bulk import export_bootstrap_pack, export_facts, import_facts
from clickproof.closed_loop import (
    ClickAttempt,
    ClickOutcomeResult,
    ClosedLoopError,
    GateOutcome,
    SessionMemory,
    apply_click_outcome,
    assert_click_ok,
    assert_session_bootstrapped,
    assert_usable_facts,
    gate_click_attempt,
    gate_facts,
    gate_session_memory,
    load_session_memory,
    store_usable_count,
)
from clickproof.fact import FactObservation, UIFact
from clickproof.report import to_markdown
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScore, FactScorer
from clickproof.store import FactStore

__version__ = importlib.metadata.version("clickproof")

__all__ = [
    "ClickAttempt",
    "ClickOutcomeResult",
    "ClosedLoopError",
    "DecayProjection",
    "FactObservation",
    "FactRetriever",
    "FactScore",
    "FactScorer",
    "FactStore",
    "GateOutcome",
    "SessionMemory",
    "UIFact",
    "__version__",
    "apply_click_outcome",
    "assert_click_ok",
    "assert_session_bootstrapped",
    "assert_usable_facts",
    "export_bootstrap_pack",
    "export_facts",
    "gate_click_attempt",
    "gate_facts",
    "gate_session_memory",
    "import_facts",
    "load_session_memory",
    "project_decay",
    "stale_facts",
    "store_usable_count",
    "to_markdown",
]
