"""clickproof — Persistent GUI behavioral facts for computer-use agents"""

from __future__ import annotations

from importlib.metadata import version as _version

__version__ = _version("clickproof")

from clickproof.fact import FactObservation, UIFact
from clickproof.scorer import FactScore, FactScorer
from clickproof.store import FactStore
from clickproof.retriever import FactRetriever

__all__ = [
    "UIFact",
    "FactObservation",
    "FactStore",
    "FactScorer",
    "FactScore",
    "FactRetriever",
]
