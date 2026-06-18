"""Tests for FactRetriever query and bootstrap_context."""

from __future__ import annotations

import time

import pytest

from guiproof.fact import FactObservation, UIFact
from guiproof.retriever import FactRetriever
from guiproof.scorer import FactScorer
from guiproof.store import FactStore


@pytest.fixture
def store_with_facts() -> FactStore:
    store = FactStore(":memory:")
    facts = [
        UIFact(app_name="salesforce", app_version="2025.11",
               element="export-csv-button", action="click",
               outcome="opens-download-dialog", context="reports-page"),
        UIFact(app_name="salesforce", app_version="2025.11",
               element="new-record-button", action="click",
               outcome="opens-new-record-form"),
        UIFact(app_name="gmail", app_version="unknown",
               element="compose-button", action="click",
               outcome="opens-compose-window"),
    ]
    for f in facts:
        store.add_fact(f)
        # Add confirming observations for salesforce facts
        if f.app_name == "salesforce":
            now = time.time()
            for i in range(3):
                obs = FactObservation(
                    fact_id=f.id, observed_at=now - i * 10, confirmed=True
                )
                store.add_observation(obs)
    yield store
    store.close()


class TestFactRetriever:
    def test_query_filters_by_app_name(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        pairs = retriever.query(app_name="salesforce", min_score=0.0)
        assert len(pairs) == 2
        assert all(f.app_name == "salesforce" for f, _ in pairs)

    def test_query_filters_by_version(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        pairs = retriever.query(app_name="salesforce", app_version="2025.11", min_score=0.0)
        assert len(pairs) == 2

    def test_query_excludes_wrong_version(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        pairs = retriever.query(app_name="salesforce", app_version="2024.01", min_score=0.0)
        assert len(pairs) == 0

    def test_query_min_score_filters(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        all_pairs = retriever.query(app_name="salesforce", min_score=0.0)
        filtered_pairs = retriever.query(app_name="salesforce", min_score=0.99)
        # High min_score should return fewer results
        assert len(filtered_pairs) <= len(all_pairs)

    def test_query_sorted_by_score_descending(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        pairs = retriever.query(app_name="salesforce", min_score=0.0)
        scores = [s.score for _, s in pairs]
        assert scores == sorted(scores, reverse=True)

    def test_query_element_filter(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        pairs = retriever.query(app_name="salesforce", element="export", min_score=0.0)
        assert len(pairs) == 1
        assert pairs[0][0].element == "export-csv-button"

    def test_query_element_filter_case_insensitive(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        pairs = retriever.query(app_name="salesforce", element="EXPORT", min_score=0.0)
        assert len(pairs) == 1

    def test_query_empty_result(self, store_with_facts: FactStore) -> None:
        retriever = FactRetriever(store_with_facts)
        pairs = retriever.query(app_name="nonexistent_app", min_score=0.0)
        assert pairs == []

    def test_query_returns_tuples(self, store_with_facts: FactStore) -> None:
        retriever = FactRetriever(store_with_facts)
        pairs = retriever.query(app_name="salesforce", min_score=0.0)
        for item in pairs:
            fact, score = item
            assert isinstance(fact, UIFact)
            from guiproof.scorer import FactScore
            assert isinstance(score, FactScore)

    def test_bootstrap_context_contains_app(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        ctx = retriever.bootstrap_context("salesforce", "2025.11")
        assert "salesforce" in ctx

    def test_bootstrap_context_contains_facts(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        ctx = retriever.bootstrap_context("salesforce", "2025.11")
        assert "export-csv-button" in ctx

    def test_bootstrap_context_empty_store(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        ctx = retriever.bootstrap_context("unknown-app")
        assert "No known UI facts" in ctx or "unknown-app" in ctx

    def test_bootstrap_context_has_scores(
        self, store_with_facts: FactStore
    ) -> None:
        retriever = FactRetriever(store_with_facts)
        ctx = retriever.bootstrap_context("salesforce", "2025.11")
        # Should contain score indicators like [0.xx]
        import re
        assert re.search(r"\[\d+\.\d+\]", ctx)

    def test_retriever_uses_custom_scorer(
        self, store_with_facts: FactStore
    ) -> None:
        custom_scorer = FactScorer()
        retriever = FactRetriever(store_with_facts, scorer=custom_scorer)
        pairs = retriever.query(app_name="salesforce", min_score=0.0)
        assert len(pairs) > 0
