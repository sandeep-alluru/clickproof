"""FactScorer — computes confidence scores from observation history."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from clickproof.fact import FactObservation, UIFact

if TYPE_CHECKING:
    from clickproof.store import FactStore


@dataclass
class FactScore:
    """Confidence score for a UIFact given its observation history.

    Attributes:
        fact_id: ID of the scored UIFact.
        app_name: Application identifier.
        app_version: Version string.
        element: Semantic element description.
        score: Current confidence in [0.0, 1.0].
        observation_count: Total number of observations.
        confirmed_count: Number of confirming observations.
        last_observed: Unix timestamp of the most recent observation.
        staleness_days: Days since the last observation.
    """

    fact_id: str
    app_name: str
    app_version: str
    element: str
    score: float
    observation_count: int
    confirmed_count: int
    last_observed: float
    staleness_days: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "fact_id": self.fact_id,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "element": self.element,
            "score": round(self.score, 4),
            "observation_count": self.observation_count,
            "confirmed_count": self.confirmed_count,
            "last_observed": self.last_observed,
            "staleness_days": round(self.staleness_days, 2),
        }


def _count_boost(count: int) -> float:
    """Compute the observation-count boost factor.

    Returns a value in [0.5, 1.0] that grows logarithmically with *count*.
    Ten or more confirming observations saturates the boost at 1.0.
    """
    return min(1.0, 0.5 + 0.5 * math.log(1 + count) / math.log(11))


class FactScorer:
    """Computes confidence scores from observation history.

    Algorithm:
        1. Base: ratio of confirmed / total observations (uses initial confidence if no obs).
        2. Decay: multiply by staleness factor: e^(-0.1 * staleness_days).
        3. Boost: scale up with observation count (more observations = more confident).
           Final score = base_ratio * staleness_decay * _count_boost(count)
    """

    def score(self, fact: UIFact, observations: list[FactObservation]) -> FactScore:
        """Compute a FactScore for a single UIFact given its observations."""
        now = time.time()
        count = len(observations)

        if count == 0:
            # No observations — use the initial confidence, apply mild staleness from recorded_at
            staleness_days = (now - fact.recorded_at) / 86400.0
            decay = math.exp(-0.1 * staleness_days)
            score = fact.confidence * decay
            return FactScore(
                fact_id=fact.id,
                app_name=fact.app_name,
                app_version=fact.app_version,
                element=fact.element,
                score=max(0.0, min(1.0, score)),
                observation_count=0,
                confirmed_count=0,
                last_observed=fact.recorded_at,
                staleness_days=staleness_days,
            )

        confirmed_count = sum(1 for o in observations if o.confirmed)
        last_observed = max(o.observed_at for o in observations)

        base_ratio = confirmed_count / count
        staleness_days = (now - last_observed) / 86400.0
        staleness_decay = math.exp(-0.1 * staleness_days)
        count_boost = _count_boost(count)

        score = base_ratio * staleness_decay * count_boost

        return FactScore(
            fact_id=fact.id,
            app_name=fact.app_name,
            app_version=fact.app_version,
            element=fact.element,
            score=max(0.0, min(1.0, score)),
            observation_count=count,
            confirmed_count=confirmed_count,
            last_observed=last_observed,
            staleness_days=staleness_days,
        )

    def batch_score(self, facts: list[UIFact], store: FactStore) -> list[FactScore]:
        """Score all facts using observations from the store."""
        results = []
        for fact in facts:
            observations = store.get_observations(fact.id)
            results.append(self.score(fact, observations))
        return results
