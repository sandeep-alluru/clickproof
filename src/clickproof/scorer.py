"""FactScorer — computes a reliability score for a UIFact given its observations."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from clickproof.fact import FactObservation, UIFact


@dataclass
class FactScore:
    score: float
    confirmed_count: int
    observation_count: int
    last_seen_at: float


class FactScorer:
    """Score a UIFact based on its observation history.

    Formula
    -------
    base_ratio        = confirmed_count / max(1, total_count)
    staleness_decay   = exp(-0.1 * days_since_last_obs)
    count_boost       = min(1.2, 1 + log(1 + count) / 10)
    final_score       = base_ratio × staleness_decay × count_boost
    """

    def score(self, fact: UIFact, observations: list[FactObservation]) -> FactScore:
        total = len(observations)
        confirmed = sum(1 for o in observations if o.confirmed)

        if total == 0:
            last_seen_at = 0.0
        else:
            last_seen_at = max(o.observed_at for o in observations)

        now = time.time()
        days_since = (now - last_seen_at) / 86400.0 if last_seen_at > 0 else 9999.0

        base_ratio = confirmed / max(1, total)
        staleness_decay = math.exp(-0.1 * days_since)
        count_boost = min(1.2, 1 + math.log(1 + total) / 10)

        final = base_ratio * staleness_decay * count_boost

        return FactScore(
            score=round(final, 6),
            confirmed_count=confirmed,
            observation_count=total,
            last_seen_at=last_seen_at,
        )
