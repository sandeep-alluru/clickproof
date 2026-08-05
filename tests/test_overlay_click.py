"""OVERLAY-CLICK — force:true / overlay intercept must invalidate facts.

Farm (Qdrant salluru-dev): #layers overlay intercepts Playwright clicks;
force:true hits overlay silently and never throws.
Public: CUADebug / Qwen-CUA / Screenshots-or-Tools computer-use failures.
"""

from __future__ import annotations

import time

import pytest

from clickproof.closed_loop import (
    ClickAttempt,
    ClosedLoopError,
    apply_click_outcome,
    assert_click_ok,
    gate_click_attempt,
    gate_facts,
)
from clickproof.fact import FactObservation, UIFact
from clickproof.scorer import FactScorer
from clickproof.store import FactStore


def _fact(
    element: str = "app-bar-close",
    confidence: float = 0.95,
    app: str = "x.com",
) -> UIFact:
    return UIFact(
        app_name=app,
        app_version="2026.07",
        element=element,
        action="click",
        outcome="closes-sheet",
        context="compose-dialog",
        confidence=confidence,
        recorded_at=time.time(),
    )


def _seed(store: FactStore, fact: UIFact, confirms: int = 3) -> None:
    store.add_fact(fact)
    now = time.time()
    for i in range(confirms):
        store.add_observation(
            FactObservation(fact_id=fact.id, observed_at=now - i, confirmed=True)
        )


def test_click_attempt_overlay_is_miss() -> None:
    a = ClickAttempt(
        fact_id="x",
        target_element="app-bar-close",
        hit=False,
        force_used=True,
        overlay_intercepted=True,
    )
    assert a.is_miss is True
    assert a.miss_kind == "overlay_intercept"


def test_force_without_effect_is_miss() -> None:
    a = ClickAttempt(
        fact_id="x",
        target_element="confirm",
        hit=True,  # agent *thinks* it hit
        force_used=True,
        observed_effect=False,  # sheet still open
    )
    assert a.is_miss is True
    assert a.miss_kind == "force_silent_no_effect"


def test_clean_hit_not_miss() -> None:
    a = ClickAttempt(fact_id="x", target_element="btn", hit=True, observed_effect=True)
    assert a.is_miss is False
    assert a.miss_kind is None


def test_overlay_miss_decays_confidence_and_score(mem_store: FactStore) -> None:
    f = _fact()
    _seed(mem_store, f)
    scorer = FactScorer()
    before = scorer.score(f, mem_store.get_observations(f.id)).score

    attempt = ClickAttempt(
        fact_id=f.id,
        target_element=f.element,
        hit=False,
        force_used=True,
        overlay_intercepted=True,
        agent_run_id="x-publish-1",
    )
    result = apply_click_outcome(mem_store, attempt, scorer=scorer)
    assert result.ok is False
    assert result.invalidated is True
    assert result.miss_kind == "overlay_intercept"
    assert result.score_after < before
    assert result.confidence_after < f.confidence
    # Store confidence updated
    stored = mem_store.get_fact(f.id)
    assert stored is not None
    assert stored.confidence == result.confidence_after
    # Refute observation written
    obs = mem_store.get_observations(f.id)
    assert any(not o.confirmed for o in obs)


def test_gate_click_attempt_fails_on_overlay(mem_store: FactStore) -> None:
    f = _fact()
    _seed(mem_store, f)
    out = gate_click_attempt(
        mem_store,
        ClickAttempt(
            fact_id=f.id,
            target_element=f.element,
            hit=False,
            force_used=True,
            overlay_intercepted=True,
        ),
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1
    assert "OVERLAY-CLICK" in out.reason


def test_gate_click_hit_passes(mem_store: FactStore) -> None:
    f = _fact()
    _seed(mem_store, f)
    out = gate_click_attempt(
        mem_store,
        ClickAttempt(
            fact_id=f.id,
            target_element=f.element,
            hit=True,
            force_used=False,
            observed_effect=True,
        ),
        min_score_after=0.2,
    )
    assert out.ok is True
    assert out.verdict == "PASS"


def test_force_silent_no_effect_invalidates(mem_store: FactStore) -> None:
    """Classic force:true hits overlay: no throw, no UI effect."""
    f = _fact(element="publish-confirm")
    _seed(mem_store, f, confirms=5)
    result = apply_click_outcome(
        mem_store,
        ClickAttempt(
            fact_id=f.id,
            target_element=f.element,
            hit=True,
            force_used=True,
            overlay_intercepted=False,
            observed_effect=False,
        ),
    )
    assert result.invalidated is True
    assert result.miss_kind == "force_silent_no_effect"


def test_unknown_fact_fails_loud(mem_store: FactStore) -> None:
    out = gate_click_attempt(
        mem_store,
        ClickAttempt(fact_id="missing", target_element="x", hit=True),
    )
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2


def test_assert_click_ok_raises_on_miss(mem_store: FactStore) -> None:
    f = _fact()
    _seed(mem_store, f)
    with pytest.raises(ClosedLoopError, match="OVERLAY-CLICK|FAIL"):
        assert_click_ok(
            mem_store,
            ClickAttempt(
                fact_id=f.id,
                target_element=f.element,
                hit=False,
                overlay_intercepted=True,
            ),
        )


def test_after_invalidation_gate_facts_may_fail(mem_store: FactStore) -> None:
    """Miss should drive score down so subsequent gate_facts can fail."""
    f = _fact(confidence=0.4)
    mem_store.add_fact(f)
    # Several refutes via overlay misses
    for _ in range(3):
        apply_click_outcome(
            mem_store,
            ClickAttempt(
                fact_id=f.id,
                target_element=f.element,
                hit=False,
                force_used=True,
                overlay_intercepted=True,
            ),
            miss_confidence_factor=0.2,
            invalidate_confidence=0.01,
        )
    out = gate_facts(mem_store, min_score=0.5)
    assert out.ok is False
    assert out.verdict in {"FAIL", "FAIL_LOUD"}
