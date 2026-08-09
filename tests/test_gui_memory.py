"""GUI-MEMORY - load known UI facts at session start; refuse cold re-discover.

Farm queue: re-discover UI every session.
Public: long-horizon computer-use agents (ABSeeker / hierarchical memory papers).
"""

from __future__ import annotations

import time

import pytest

from clickproof.closed_loop import (
    ClosedLoopError,
    assert_session_bootstrapped,
    gate_session_memory,
    load_session_memory,
    store_usable_count,
)
from clickproof.fact import FactObservation, UIFact
from clickproof.store import FactStore


def _seed(store: FactStore, app: str = "x.com", n: int = 2) -> list[UIFact]:
    facts = []
    now = time.time()
    for i in range(n):
        f = UIFact(
            app_name=app,
            app_version="2026.08",
            element=f"btn-{i}",
            action="click",
            outcome="ok",
            confidence=0.95,
            recorded_at=now,
        )
        store.add_fact(f)
        store.add_observation(FactObservation(fact_id=f.id, observed_at=now, confirmed=True))
        facts.append(f)
    return facts


def test_load_session_memory_loads_usable(mem_store: FactStore) -> None:
    _seed(mem_store, "salesforce")
    mem = load_session_memory(mem_store, "salesforce", min_score=0.3)
    assert mem.usable_count >= 1
    assert len(mem.loaded_fact_ids) == mem.usable_count
    assert mem.app_name == "salesforce"
    assert "salesforce" in mem.bootstrap_text.lower() or "fact" in mem.bootstrap_text.lower()
    assert mem.is_empty is False


def test_store_usable_count(mem_store: FactStore) -> None:
    assert store_usable_count(mem_store, "none") == 0
    _seed(mem_store, "gmail")
    assert store_usable_count(mem_store, "gmail", min_score=0.3) >= 1


def test_gate_fails_when_session_skipped_but_store_known(mem_store: FactStore) -> None:
    """GUI-MEMORY load-bearing: skip bootstrap with known facts → FAIL."""
    _seed(mem_store, "x.com")
    out = gate_session_memory(mem_store, None, app_name="x.com", min_score=0.3)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1
    assert "GUI-MEMORY" in out.reason
    assert "load_session_memory" in out.reason or "re-discover" in out.reason.lower()


def test_gate_fails_loud_when_store_empty(mem_store: FactStore) -> None:
    out = gate_session_memory(mem_store, None, app_name="unknown-app")
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2


def test_gate_pass_when_session_loaded(mem_store: FactStore) -> None:
    _seed(mem_store, "notion")
    mem = load_session_memory(mem_store, "notion", min_score=0.3)
    out = gate_session_memory(mem_store, mem, app_name="notion", min_score=0.3)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.usable_count >= 1


def test_gate_app_mismatch_fails(mem_store: FactStore) -> None:
    _seed(mem_store, "a")
    _seed(mem_store, "b")
    mem = load_session_memory(mem_store, "a", min_score=0.3)
    out = gate_session_memory(mem_store, mem, app_name="b", min_score=0.3)
    assert out.ok is False
    assert out.verdict == "FAIL"


def test_assert_session_bootstrapped_raises(mem_store: FactStore) -> None:
    _seed(mem_store, "x")
    with pytest.raises(ClosedLoopError, match=r"GUI-MEMORY|FAIL"):
        assert_session_bootstrapped(mem_store, None, app_name="x", min_score=0.3)


def test_assert_session_bootstrapped_ok(mem_store: FactStore) -> None:
    _seed(mem_store, "y")
    mem = load_session_memory(mem_store, "y", min_score=0.3)
    out = assert_session_bootstrapped(mem_store, mem, app_name="y", min_score=0.3)
    assert out.ok is True


def test_session_memory_to_dict(mem_store: FactStore) -> None:
    _seed(mem_store, "z")
    mem = load_session_memory(mem_store, "z", session_id="sess1", min_score=0.3)
    d = mem.to_dict()
    assert d["session_id"] == "sess1"
    assert d["usable_count"] >= 1
    assert d["is_empty"] is False
