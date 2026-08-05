"""Closed-loop reader — empty fact stores and unusable scores fail loudly."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from clickproof.closed_loop import (
    ClosedLoopError,
    GateOutcome,
    assert_usable_facts,
    gate_facts,
)
from clickproof.fact import FactObservation, UIFact
from clickproof.store import FactStore


def _fact(
    element: str = "export-csv-button",
    confidence: float = 0.9,
    app: str = "salesforce",
) -> UIFact:
    return UIFact(
        app_name=app,
        app_version="2025.11",
        element=element,
        action="click",
        outcome="opens-download-dialog",
        context="reports-page",
        confidence=confidence,
        recorded_at=time.time(),
    )


def test_empty_list_fails_loud() -> None:
    out = gate_facts([])
    assert isinstance(out, GateOutcome)
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert "empty" in out.reason.lower()


def test_empty_store_fails_loud(mem_store: FactStore) -> None:
    out = gate_facts(mem_store)
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert out.fact_count == 0


def test_missing_db_fails_loud(tmp_path: Path) -> None:
    out = gate_facts(tmp_path / "nope.db")
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert "not found" in out.reason.lower()


def test_usable_facts_pass(mem_store: FactStore) -> None:
    f = _fact(confidence=0.95)
    mem_store.add_fact(f)
    now = time.time()
    for i in range(3):
        mem_store.add_observation(
            FactObservation(fact_id=f.id, observed_at=now - i * 10, confirmed=True)
        )
    out = gate_facts(mem_store, min_score=0.3)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.exit_code == 0
    assert out.usable_count >= 1
    payload = out.to_dict()
    assert payload["ok"] is True


def test_sequence_high_confidence_passes() -> None:
    out = gate_facts([_fact(confidence=1.0)], min_score=0.4)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.fact_count == 1


def test_all_low_confidence_fails() -> None:
    # No observations + very old recorded_at → heavy staleness decay
    old = UIFact(
        app_name="legacy",
        app_version="0.1",
        element="gone-btn",
        action="click",
        outcome="error:not-found",
        confidence=0.05,
        recorded_at=time.time() - 86400 * 365,
    )
    out = gate_facts([old], min_score=0.5)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1
    assert out.usable_count == 0


def test_store_path_with_facts_passes(tmp_path: Path) -> None:
    db = tmp_path / "facts.db"
    store = FactStore(db)
    try:
        f = _fact()
        store.add_fact(f)
        store.add_observation(
            FactObservation(fact_id=f.id, observed_at=time.time(), confirmed=True)
        )
    finally:
        store.close()
    out = gate_facts(db, min_score=0.2)
    assert out.ok is True
    assert out.verdict == "PASS"


def test_assert_usable_facts_raises_on_empty() -> None:
    with pytest.raises(ClosedLoopError, match="FAIL_LOUD"):
        assert_usable_facts([])


def test_assert_usable_facts_ok() -> None:
    out = assert_usable_facts([_fact(confidence=1.0)], min_score=0.3)
    assert out.ok is True
