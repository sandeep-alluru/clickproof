"""guiproof — persistent GUI behavioral facts for computer-use agents."""

from __future__ import annotations

import importlib.metadata

from guiproof.fact import FactObservation, UIFact
from guiproof.retriever import FactRetriever
from guiproof.scorer import FactScore, FactScorer
from guiproof.store import FactStore

__version__ = importlib.metadata.version("guiproof")

__all__ = [
    "FactObservation",
    "FactRetriever",
    "FactScore",
    "FactScorer",
    "FactStore",
    "UIFact",
    "__version__",
]
