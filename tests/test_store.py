"""Tests for FactStore CRUD operations."""

from __future__ import annotations

import time

import pytest

from clickproof.fact import FactObservation, UIFact
from clickproof.store import FactStore


class TestFactStoreFacts:
    def test_add_and_get_fact(self, mem_store: FactStore, sample_fact: UIFact) -> None:
        mem_store.add_fact(sample_fact)
        retrieved = mem_store.get_fact(sample_fact.id)
        assert retrieved is not None
        assert retrieved.id == sample_fact.id
        assert retrieved.app_name == sample_fact.app_name

    def test_get_nonexistent_fact_returns_none(self, mem_store: FactStore) -> None:
        result = mem_store.get_fact("nonexistent_id")
        assert result is None

    def test_add_duplicate_fact_is_idempotent(
        self, mem_store: FactStore, sample_fact: UIFact
    ) -> None:
        mem_store.add_fact(sample_fact)
        mem_store.add_fact(sample_fact)  # should not raise
        facts = mem_store.list_facts()
        assert len(facts) == 1

    def test_list_facts_returns_all(self, mem_store: FactStore) -> None:
        facts = [
            UIFact(app_name="app", app_version="1.0",
                   element=f"btn-{i}", action="click", outcome="ok")
            for i in range(3)
        ]
        for f in facts:
            mem_store.add_fact(f)
        result = mem_store.list_facts()
        assert len(result) == 3

    def test_list_facts_filtered_by_app_name(self, mem_store: FactStore) -> None:
        f1 = UIFact(app_name="salesforce", app_version="1.0",
                    element="btn", action="click", outcome="ok")
        f2 = UIFact(app_name="gmail", app_version="1.0",
                    element="btn", action="click", outcome="ok")
        mem_store.add_fact(f1)
        mem_store.add_fact(f2)
        result = mem_store.list_facts(app_name="salesforce")
        assert len(result) == 1
        assert result[0].app_name == "salesforce"

    def test_list_facts_filtered_by_version(self, mem_store: FactStore) -> None:
        f1 = UIFact(app_name="app", app_version="1.0",
                    element="btn", action="click", outcome="ok")
        f2 = UIFact(app_name="app", app_version="2.0",
                    element="btn", action="click", outcome="ok")
        mem_store.add_fact(f1)
        mem_store.add_fact(f2)
        result = mem_store.list_facts(app_version="1.0")
        assert len(result) == 1
        assert result[0].app_version == "1.0"

    def test_list_facts_filter_both_app_and_version(self, mem_store: FactStore) -> None:
        facts = [
            UIFact(app_name="app", app_version="1.0",
                   element="btn-a", action="click", outcome="ok"),
            UIFact(app_name="app", app_version="2.0",
                   element="btn-b", action="click", outcome="ok"),
            UIFact(app_name="other", app_version="1.0",
                   element="btn-c", action="click", outcome="ok"),
        ]
        for f in facts:
            mem_store.add_fact(f)
        result = mem_store.list_facts(app_name="app", app_version="1.0")
        assert len(result) == 1
        assert result[0].element == "btn-a"

    def test_retrieved_fact_preserves_fields(
        self, mem_store: FactStore, sample_fact: UIFact
    ) -> None:
        mem_store.add_fact(sample_fact)
        retrieved = mem_store.get_fact(sample_fact.id)
        assert retrieved is not None
        assert retrieved.outcome == sample_fact.outcome
        assert retrieved.context == sample_fact.context
        assert retrieved.confidence == sample_fact.confidence

    def test_list_empty_store(self, mem_store: FactStore) -> None:
        assert mem_store.list_facts() == []


class TestFactStoreObservations:
    def test_add_and_get_observations(
        self, mem_store: FactStore, sample_fact: UIFact
    ) -> None:
        mem_store.add_fact(sample_fact)
        obs = FactObservation(
            fact_id=sample_fact.id, observed_at=time.time(), confirmed=True
        )
        mem_store.add_observation(obs)
        result = mem_store.get_observations(sample_fact.id)
        assert len(result) == 1
        assert result[0].confirmed is True

    def test_get_observations_empty(
        self, mem_store: FactStore, sample_fact: UIFact
    ) -> None:
        mem_store.add_fact(sample_fact)
        result = mem_store.get_observations(sample_fact.id)
        assert result == []

    def test_multiple_observations_ordered(
        self, mem_store: FactStore, sample_fact: UIFact
    ) -> None:
        mem_store.add_fact(sample_fact)
        now = time.time()
        for i in range(5):
            obs = FactObservation(
                fact_id=sample_fact.id, observed_at=now + i, confirmed=i % 2 == 0
            )
            mem_store.add_observation(obs)
        result = mem_store.get_observations(sample_fact.id)
        assert len(result) == 5
        # Should be sorted by observed_at
        timestamps = [o.observed_at for o in result]
        assert timestamps == sorted(timestamps)

    def test_add_duplicate_observation_is_idempotent(
        self, mem_store: FactStore, sample_fact: UIFact
    ) -> None:
        mem_store.add_fact(sample_fact)
        obs = FactObservation(
            fact_id=sample_fact.id, observed_at=time.time(), confirmed=True
        )
        mem_store.add_observation(obs)
        mem_store.add_observation(obs)  # same id, should not raise
        result = mem_store.get_observations(sample_fact.id)
        assert len(result) == 1

    def test_context_manager(self, tmp_path: pytest.TempPathFactory) -> None:
        db = str(tmp_path / "test.db")
        with FactStore(db) as store:
            fact = UIFact(app_name="app", app_version="1.0",
                          element="btn", action="click", outcome="ok")
            store.add_fact(fact)
            assert store.get_fact(fact.id) is not None
        # After __exit__, store is closed; re-open and verify persistence
        with FactStore(db) as store2:
            assert store2.get_fact(fact.id) is not None
