"""Decay analytics and projections for UIFacts."""

from __future__ import annotations

import math
from dataclasses import dataclass

from clickproof.fact import UIFact
from clickproof.scorer import FactScorer
from clickproof.store import FactStore


@dataclass
class DecayProjection:
    """Decay projection for a single UIFact.

    Attributes:
        fact_id: ID of the UIFact.
        element: Semantic element description.
        current_score: Score right now.
        score_in_7_days: Projected score 7 days from now.
        score_in_30_days: Projected score 30 days from now.
        days_until_threshold: Days until score drops below *min_score*
            (0.0 if already below threshold or if it can never reach threshold).
        recommendation: One of ``"ok"``, ``"re-validate"``, or ``"archive"``.
    """

    fact_id: str
    element: str
    current_score: float
    score_in_7_days: float
    score_in_30_days: float
    days_until_threshold: float
    recommendation: str


def _project_score(
    base_ratio: float,
    count_boost: float,
    staleness_days: float,
    delta_days: float,
) -> float:
    """Compute the projected score given a staleness delta.

    The staleness component of the scorer is:
        exp(-0.1 * days_since)
    so adding *delta_days* to the staleness multiplies the decay factor by
    exp(-0.1 * delta_days).
    """
    return base_ratio * math.exp(-0.1 * (staleness_days + delta_days)) * count_boost


def project_decay(
    store: FactStore,
    scorer: FactScorer,
    app_name: str,
    min_score: float = 0.5,
) -> list[DecayProjection]:
    """Return decay projections for all facts belonging to *app_name*.

    Args:
        store: An open FactStore to read from.
        scorer: A FactScorer used to compute the current score.
        app_name: Application name to project for.
        min_score: Threshold below which a fact is considered stale.

    Returns:
        List of :class:`DecayProjection` objects, one per fact.
    """
    facts = store.list_facts(app_name=app_name)
    projections: list[DecayProjection] = []

    for fact in facts:
        observations = store.get_observations(fact.id)
        fact_score = scorer.score(fact, observations)
        current_score = fact_score.score
        staleness_days = fact_score.staleness_days

        count = fact_score.observation_count

        if count == 0:
            # No observations — scorer uses fact.confidence as the base ratio
            base_ratio = fact.confidence
            count_boost = 1.0
        else:
            confirmed_count = fact_score.confirmed_count
            base_ratio = confirmed_count / count
            count_boost = min(1.0, 0.5 + 0.5 * math.log(1 + count) / math.log(11))

        score_in_7_days = max(
            0.0, _project_score(base_ratio, count_boost, staleness_days, 7.0)
        )
        score_in_30_days = max(
            0.0, _project_score(base_ratio, count_boost, staleness_days, 30.0)
        )

        # Solve: base_ratio * exp(-0.1 * (staleness + x)) * count_boost = min_score
        # => -0.1 * (staleness + x) = ln(min_score / (base_ratio * count_boost))
        # => staleness + x = -ln(min_score / (base_ratio * count_boost)) / 0.1
        # => x = -ln(min_score / (base_ratio * count_boost)) / 0.1 - staleness
        peak = base_ratio * count_boost
        if min_score <= 0.0:
            # Score never reaches 0 (asymptotic), so the threshold is effectively never crossed
            days_until_threshold = 9999.0
        elif peak <= min_score:
            # Score can never reach the threshold even at days_since=0
            days_until_threshold = 0.0
        elif current_score < min_score:
            days_until_threshold = 0.0
        else:
            days_until_threshold = max(
                0.0,
                (-math.log(min_score / peak) / 0.1) - staleness_days,
            )

        if current_score < min_score:
            recommendation = "archive"
        elif score_in_7_days < min_score:
            recommendation = "re-validate"
        else:
            recommendation = "ok"

        projections.append(
            DecayProjection(
                fact_id=fact.id,
                element=fact.element,
                current_score=round(current_score, 6),
                score_in_7_days=round(score_in_7_days, 6),
                score_in_30_days=round(score_in_30_days, 6),
                days_until_threshold=round(days_until_threshold, 2),
                recommendation=recommendation,
            )
        )

    return projections


def stale_facts(
    store: FactStore,
    scorer: FactScorer,
    app_name: str,
    min_score: float = 0.5,
) -> list[UIFact]:
    """Return facts whose current score is below *min_score*.

    Args:
        store: An open FactStore to read from.
        scorer: A FactScorer used to compute the current score.
        app_name: Application name to filter by.
        min_score: Score threshold; facts with score strictly below this are returned.

    Returns:
        List of :class:`UIFact` objects whose score < *min_score*.
    """
    facts = store.list_facts(app_name=app_name)
    stale: list[UIFact] = []

    for fact in facts:
        observations = store.get_observations(fact.id)
        fact_score = scorer.score(fact, observations)
        if fact_score.score < min_score:
            stale.append(fact)

    return stale
