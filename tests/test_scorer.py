"""Tests for FactScorer and FactScore."""

from __future__ import annotations

import time

import pytest

from guiproof.fact import FactObservation, UIFact
from guiproof.scorer import FactScorer


@pytest.fixture
def scorer() -> FactScorer:
    return FactScorer()


@pytest.fixture
def fact() -> UIFact:
    return UIFact(
        app_name="app", app_version="1.0",
        element="button", action="click", outcome="ok",
    )


def _obs(fact_id: str, confirmed: bool, seconds_ago: float = 10.0) -> FactObservation:
    return FactObservation(
        fact_id=fact_id,
        observed_at=time.time() - seconds_ago,
        confirmed=confirmed,
    )


class TestFactScorer:
    def test_no_observations_uses_initial_confidence(
        self, scorer: FactScorer, fact: UIFact
    ) -> None:
        fact.confidence = 0.8
        fs = scorer.score(fact, [])
        # Score should be near 0.8 (just recorded, minimal staleness)
        assert 0.6 <= fs.score <= 0.9

    def test_no_observations_zero_confidence(self, scorer: FactScorer) -> None:
        fact = UIFact(app_name="app", app_version="1.0",
                      element="btn", action="click", outcome="ok", confidence=0.0)
        fs = scorer.score(fact, [])
        assert fs.score == 0.0

    def test_all_confirmed_gives_high_score(
        self, scorer: FactScorer, fact: UIFact
    ) -> None:
        obs = [_obs(fact.id, confirmed=True, seconds_ago=i * 10) for i in range(5)]
        fs = scorer.score(fact, obs)
        assert fs.score > 0.5

    def test_all_refuted_gives_low_score(
        self, scorer: FactScorer, fact: UIFact
    ) -> None:
        obs = [_obs(fact.id, confirmed=False, seconds_ago=i * 10) for i in range(5)]
        fs = scorer.score(fact, obs)
        assert fs.score == 0.0

    def test_mixed_observations_intermediate(
        self, scorer: FactScorer, fact: UIFact
    ) -> None:
        obs = [
            _obs(fact.id, confirmed=True, seconds_ago=30),
            _obs(fact.id, confirmed=False, seconds_ago=20),
        ]
        fs = scorer.score(fact, obs)
        assert 0.0 < fs.score < 1.0

    def test_confirmed_count_correct(self, scorer: FactScorer, fact: UIFact) -> None:
        obs = [
            _obs(fact.id, confirmed=True),
            _obs(fact.id, confirmed=True),
            _obs(fact.id, confirmed=False),
        ]
        fs = scorer.score(fact, obs)
        assert fs.confirmed_count == 2
        assert fs.observation_count == 3

    def test_staleness_applies(self, scorer: FactScorer, fact: UIFact) -> None:
        """Older observations should produce lower score than recent ones."""
        recent_obs = [_obs(fact.id, confirmed=True, seconds_ago=10)]
        old_obs = [_obs(fact.id, confirmed=True, seconds_ago=60 * 60 * 24 * 30)]  # 30 days
        recent_score = scorer.score(fact, recent_obs)
        old_score = scorer.score(fact, old_obs)
        assert recent_score.score > old_score.score

    def test_more_observations_boost_score(
        self, scorer: FactScorer, fact: UIFact
    ) -> None:
        one_obs = [_obs(fact.id, confirmed=True, seconds_ago=5)]
        ten_obs = [_obs(fact.id, confirmed=True, seconds_ago=5 + i) for i in range(10)]
        score_one = scorer.score(fact, one_obs).score
        score_ten = scorer.score(fact, ten_obs).score
        assert score_ten > score_one

    def test_score_clipped_to_unit_interval(
        self, scorer: FactScorer, fact: UIFact
    ) -> None:
        obs = [_obs(fact.id, confirmed=True, seconds_ago=1) for _ in range(100)]
        fs = scorer.score(fact, obs)
        assert 0.0 <= fs.score <= 1.0

    def test_fact_score_to_dict(self, scorer: FactScorer, fact: UIFact) -> None:
        fs = scorer.score(fact, [])
        d = fs.to_dict()
        assert "fact_id" in d
        assert "score" in d
        assert "observation_count" in d
        assert "staleness_days" in d

    def test_batch_score_returns_all(self, scorer: FactScorer) -> None:
        from guiproof.store import FactStore
        with FactStore(":memory:") as store:
            facts = [
                UIFact(app_name="app", app_version="1.0",
                       element=f"btn-{i}", action="click", outcome="ok")
                for i in range(5)
            ]
            for f in facts:
                store.add_fact(f)
            scores = scorer.batch_score(facts, store)
        assert len(scores) == 5

    def test_staleness_days_near_zero_for_fresh(
        self, scorer: FactScorer, fact: UIFact
    ) -> None:
        obs = [_obs(fact.id, confirmed=True, seconds_ago=1)]
        fs = scorer.score(fact, obs)
        assert fs.staleness_days < 0.01
