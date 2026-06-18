"""clickproof — persistent GUI behavioral facts for computer-use agents."""

from __future__ import annotations

import importlib.metadata

from clickproof.fact import FactObservation, UIFact
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScore, FactScorer
from clickproof.store import FactStore

__version__ = importlib.metadata.version("clickproof")

__all__ = [
    "FactObservation",
    "FactRetriever",
    "FactScore",
    "FactScorer",
    "FactStore",
    "UIFact",
    "__version__",
]
