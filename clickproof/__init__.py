"""clickproof — persistent GUI behavioral facts for computer-use agents."""

from __future__ import annotations

import importlib.metadata

from clickproof.analytics import DecayProjection, project_decay, stale_facts
from clickproof.bulk import export_bootstrap_pack, export_facts, import_facts
from clickproof.fact import FactObservation, UIFact
from clickproof.report import to_markdown
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScore, FactScorer
from clickproof.store import FactStore

__version__ = importlib.metadata.version("clickproof")

__all__ = [
    "DecayProjection",
    "FactObservation",
    "FactRetriever",
    "FactScore",
    "FactScorer",
    "FactStore",
    "UIFact",
    "__version__",
    "export_bootstrap_pack",
    "export_facts",
    "import_facts",
    "project_decay",
    "stale_facts",
    "to_markdown",
]
