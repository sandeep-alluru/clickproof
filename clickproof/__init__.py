"""clickproof - persistent GUI behavioral facts for computer-use agents."""

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
from clickproof.context_vars import (
    DEFAULT_DOMINANT_KEYS,
    DEFAULT_SPARSE_CONTEXT_KEYS,
    ContextDecision,
    CVEReport,
    analyze_cve,
    assert_context_variables_ok,
    context_fingerprint,
    gate_context_variables,
    is_sparse_context_key,
)
from clickproof.fact import FactObservation, UIFact
from clickproof.report import to_markdown
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScore, FactScorer
from clickproof.stepjack import (
    DEFAULT_CUMULATIVE_PATTERNS,
    DEFAULT_INJECTION_PHRASES,
    NavStep,
    StepJackReport,
    analyze_multi_step_chain,
    assert_multi_step_ok,
    detect_injection_phrases,
    gate_multi_step_chain,
    hosts_from_task,
)
from clickproof.store import FactStore
from clickproof.synchain import (
    ArtifactIntegrityReport,
    PersistentArtifact,
    analyze_artifact_integrity,
    artifact_content_fingerprint,
    assert_artifacts_ok,
    gate_artifact_integrity,
)

__version__ = importlib.metadata.version("clickproof")

__all__ = [
    "DEFAULT_CUMULATIVE_PATTERNS",
    "DEFAULT_DOMINANT_KEYS",
    "DEFAULT_HIGH_RISK_CUA_ACTIONS",
    "DEFAULT_INJECTION_PHRASES",
    "DEFAULT_SPARSE_CONTEXT_KEYS",
    "ArtifactIntegrityReport",
    "CVEReport",
    "ClickAttempt",
    "ClickOutcomeResult",
    "ClosedLoopError",
    "ContextDecision",
    "DecayProjection",
    "FactObservation",
    "FactRetriever",
    "FactScore",
    "FactScorer",
    "FactStore",
    "GateOutcome",
    "NavStep",
    "PersistentArtifact",
    "SessionMemory",
    "StepJackReport",
    "UIFact",
    "__version__",
    "analyze_artifact_integrity",
    "analyze_cve",
    "analyze_multi_step_chain",
    "apply_click_outcome",
    "artifact_content_fingerprint",
    "assert_artifacts_ok",
    "assert_click_ok",
    "assert_context_variables_ok",
    "assert_multi_step_ok",
    "assert_session_bootstrapped",
    "assert_task_aligned",
    "assert_usable_facts",
    "context_fingerprint",
    "detect_injection_phrases",
    "export_bootstrap_pack",
    "export_facts",
    "gate_artifact_integrity",
    "gate_click_attempt",
    "gate_context_variables",
    "gate_facts",
    "gate_multi_step_chain",
    "gate_session_memory",
    "gate_task_alignment",
    "hosts_from_task",
    "import_facts",
    "infer_allowlist_from_task",
    "is_high_risk_cua_action",
    "is_sparse_context_key",
    "load_session_memory",
    "project_decay",
    "stale_facts",
    "store_usable_count",
    "to_markdown",
]
