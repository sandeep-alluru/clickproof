"""clickproof — persistent GUI behavioral facts for computer-use agents."""

from __future__ import annotations

import importlib.metadata

from clickproof.analytics import DecayProjection, project_decay, stale_facts
from clickproof.bulk import export_bootstrap_pack, export_facts, import_facts
from clickproof.closed_loop import (
    DEFAULT_HIGH_RISK_CUA_ACTIONS,
    ClickAttempt,
    ClickOutcomeResult,
    ClosedLoopError,
    GateOutcome,
    SessionMemory,
    apply_click_outcome,
    assert_click_ok,
    assert_session_bootstrapped,
    assert_task_aligned,
    assert_usable_facts,
    gate_click_attempt,
    gate_facts,
    gate_session_memory,
    gate_task_alignment,
    infer_allowlist_from_task,
    is_high_risk_cua_action,
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
    "DEFAULT_HIGH_RISK_CUA_ACTIONS",
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
    "assert_task_aligned",
    "assert_usable_facts",
    "export_bootstrap_pack",
    "export_facts",
    "gate_click_attempt",
    "gate_facts",
    "gate_session_memory",
    "gate_task_alignment",
    "import_facts",
    "infer_allowlist_from_task",
    "is_high_risk_cua_action",
    "load_session_memory",
    "project_decay",
    "stale_facts",
    "store_usable_count",
    "to_markdown",
]
