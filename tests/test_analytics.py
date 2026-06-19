"""Tests for decay analytics and projections."""

from __future__ import annotations

import time

from clickproof.analytics import DecayProjection, project_decay, stale_facts
from clickproof.fact import FactObservation, UIFact
from clickproof.scorer import FactScorer
from clickproof.store import FactStore


def make_fact(
    app_name: str = "myapp",
    app_version: str = "1.0",
    element: str = "save-button",
    confidence: float = 1.0,
) -> UIFact:
    return UIFact(
        app_name=app_name,
        app_version=app_version,
        element=element,
        action="click",
        outcome="saves-document",
        confidence=confidence,
    )


def make_obs(fact: UIFact, confirmed: bool = True, age_seconds: float = 10.0) -> FactObservation:
    return FactObservation(
        fact_id=fact.id,
        observed_at=time.time() - age_seconds,
        confirmed=confirmed,
    )


class TestProjectDecay:
    def test_returns_list_of_decay_projections(self) -> None:
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            obs = make_obs(fact)
            store.add_observation(obs)
            scorer = FactScorer()
            result = project_decay(store, scorer, app_name="myapp")

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], DecayProjection)

    def test_empty_store_returns_empty_list(self) -> None:
        with FactStore(":memory:") as store:
            scorer = FactScorer()
            result = project_decay(store, scorer, app_name="myapp")

        assert result == []

    def test_score_in_7_days_less_than_or_equal_current(self) -> None:
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            obs1 = make_obs(fact, confirmed=True, age_seconds=100)
            obs2 = make_obs(fact, confirmed=True, age_seconds=50)
            store.add_observation(obs1)
            store.add_observation(obs2)
            scorer = FactScorer()
            result = project_decay(store, scorer, app_name="myapp")

        proj = result[0]
        assert proj.score_in_7_days <= proj.current_score
        assert proj.score_in_30_days <= proj.score_in_7_days

    def test_projection_fields_present(self) -> None:
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            obs = make_obs(fact)
            store.add_observation(obs)
            scorer = FactScorer()
            result = project_decay(store, scorer, app_name="myapp")

        proj = result[0]
        assert proj.fact_id == fact.id
        assert proj.element == fact.element
        assert isinstance(proj.current_score, float)
        assert isinstance(proj.score_in_7_days, float)
        assert isinstance(proj.score_in_30_days, float)
        assert isinstance(proj.days_until_threshold, float)
        assert proj.recommendation in {"ok", "re-validate", "archive"}

    def test_recommendation_ok_for_high_score(self) -> None:
        now = time.time()
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            # Many recent confirmations → high score
            for _ in range(5):
                obs = FactObservation(
                    fact_id=fact.id,
                    observed_at=now - 60,
                    confirmed=True,
                )
                store.add_observation(obs)
            scorer = FactScorer()
            result = project_decay(store, scorer, app_name="myapp", min_score=0.1)

        proj = result[0]
        # With min_score=0.1, a recently confirmed fact should be "ok"
        assert proj.recommendation == "ok"

    def test_recommendation_archive_when_current_below_threshold(self) -> None:
        """A fact recorded 100 days ago with no observations scores very low."""
        old_recorded = time.time() - (86400 * 100)
        with FactStore(":memory:") as store:
            fact = UIFact(
                app_name="myapp",
                app_version="1.0",
                element="old-btn",
                action="click",
                outcome="ok",
                confidence=1.0,
                recorded_at=old_recorded,
            )
            store.add_fact(fact)
            scorer = FactScorer()
            result = project_decay(store, scorer, app_name="myapp", min_score=0.5)

        proj = result[0]
        # Score decays to near 0 at 100 days
        assert proj.current_score < 0.5
        assert proj.recommendation == "archive"

    def test_recommendation_revalidate_when_7d_below_threshold(self) -> None:
        """A fact with score just above min_score but decaying fast → re-validate."""
        # Set up a fact with score just at 0.5 (will be below 0.5 in 7 days)
        now = time.time()
        # score = 1.0 * exp(-0.1 * days) → at days=6.93 score=0.5
        # So at days=6.0 score > 0.5 but at 6+7=13 days score < 0.5
        days_since = 6.0
        last_obs_at = now - days_since * 86400

        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            obs = FactObservation(
                fact_id=fact.id,
                observed_at=last_obs_at,
                confirmed=True,
            )
            store.add_observation(obs)
            scorer = FactScorer()
            result = project_decay(store, scorer, app_name="myapp", min_score=0.5)

        proj = result[0]
        if proj.current_score >= 0.5 and proj.score_in_7_days < 0.5:
            assert proj.recommendation == "re-validate"

    def test_no_observations_fact(self) -> None:
        """Project decay for a fact with no observations."""
        with FactStore(":memory:") as store:
            fact = make_fact(confidence=1.0)
            store.add_fact(fact)
            scorer = FactScorer()
            result = project_decay(store, scorer, app_name="myapp")

        assert len(result) == 1
        proj = result[0]
        assert proj.score_in_7_days <= proj.current_score

    def test_days_until_threshold_positive_for_good_fact(self) -> None:
        now = time.time()
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            obs = FactObservation(
                fact_id=fact.id,
                observed_at=now - 10,
                confirmed=True,
            )
            store.add_observation(obs)
            scorer = FactScorer()
            result = project_decay(store, scorer, app_name="myapp", min_score=0.3)

        proj = result[0]
        if proj.current_score >= 0.3:
            assert proj.days_until_threshold >= 0.0

    def test_only_returns_facts_for_given_app(self) -> None:
        with FactStore(":memory:") as store:
            fact_a = make_fact(app_name="alpha")
            fact_b = UIFact(
                app_name="beta",
                app_version="1.0",
                element="btn",
                action="click",
                outcome="ok",
            )
            store.add_fact(fact_a)
            store.add_fact(fact_b)
            scorer = FactScorer()
            result = project_decay(store, scorer, app_name="alpha")

        assert len(result) == 1
        assert result[0].fact_id == fact_a.id


class TestStaleFacts:
    def test_returns_facts_below_min_score(self) -> None:
        old_recorded = time.time() - (86400 * 100)
        with FactStore(":memory:") as store:
            old_fact = UIFact(
                app_name="myapp",
                app_version="1.0",
                element="old-btn",
                action="click",
                outcome="ok",
                confidence=1.0,
                recorded_at=old_recorded,
            )
            store.add_fact(old_fact)
            scorer = FactScorer()
            result = stale_facts(store, scorer, app_name="myapp", min_score=0.5)

        assert len(result) == 1
        assert result[0].id == old_fact.id

    def test_excludes_high_score_facts(self) -> None:
        now = time.time()
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            # Add many recent confirming observations
            for i in range(5):
                obs = FactObservation(
                    fact_id=fact.id,
                    observed_at=now - i * 60,
                    confirmed=True,
                )
                store.add_observation(obs)
            scorer = FactScorer()
            result = stale_facts(store, scorer, app_name="myapp", min_score=0.5)

        # A recently confirmed fact should NOT be stale
        assert len(result) == 0

    def test_empty_store_returns_empty(self) -> None:
        with FactStore(":memory:") as store:
            scorer = FactScorer()
            result = stale_facts(store, scorer, app_name="myapp")

        assert result == []

    def test_returns_uifact_objects(self) -> None:
        old_recorded = time.time() - (86400 * 100)
        with FactStore(":memory:") as store:
            fact = UIFact(
                app_name="myapp",
                app_version="1.0",
                element="btn",
                action="click",
                outcome="ok",
                recorded_at=old_recorded,
            )
            store.add_fact(fact)
            scorer = FactScorer()
            result = stale_facts(store, scorer, app_name="myapp")

        assert all(isinstance(f, UIFact) for f in result)

    def test_mixed_facts_correct_partition(self) -> None:
        now = time.time()
        old_recorded = now - (86400 * 100)
        with FactStore(":memory:") as store:
            # Good (fresh) fact
            fresh_fact = make_fact(element="fresh-btn")
            store.add_fact(fresh_fact)
            for _ in range(3):
                obs = FactObservation(
                    fact_id=fresh_fact.id,
                    observed_at=now - 60,
                    confirmed=True,
                )
                store.add_observation(obs)

            # Stale fact
            stale_fact = UIFact(
                app_name="myapp",
                app_version="1.0",
                element="old-btn",
                action="click",
                outcome="ok",
                recorded_at=old_recorded,
            )
            store.add_fact(stale_fact)

            scorer = FactScorer()
            result = stale_facts(store, scorer, app_name="myapp", min_score=0.5)

        stale_ids = {f.id for f in result}
        assert stale_fact.id in stale_ids
        assert fresh_fact.id not in stale_ids
