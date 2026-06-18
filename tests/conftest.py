"""Shared pytest fixtures for guiproof tests."""

from __future__ import annotations

import time

import pytest

from guiproof.fact import FactObservation, UIFact
from guiproof.store import FactStore


@pytest.fixture
def mem_store() -> FactStore:
    """In-memory FactStore for isolated tests."""
    store = FactStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def sample_fact() -> UIFact:
    """A typical UIFact for reuse across tests."""
    return UIFact(
        app_name="salesforce",
        app_version="2025.11",
        element="export-csv-button",
        action="click",
        outcome="opens-download-dialog",
        context="reports-page",
        confidence=0.9,
    )


@pytest.fixture
def recent_confirmations(sample_fact: UIFact) -> list[FactObservation]:
    """Three recent confirming observations."""
    now = time.time()
    return [
        FactObservation(fact_id=sample_fact.id, observed_at=now - 60, confirmed=True),
        FactObservation(fact_id=sample_fact.id, observed_at=now - 30, confirmed=True),
        FactObservation(fact_id=sample_fact.id, observed_at=now - 10, confirmed=True),
    ]
