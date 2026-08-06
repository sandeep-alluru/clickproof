"""Closed-loop reader/gate for clickproof (Non-Ornament L1).

Who reads the output?
  Computer-use agents / CI / eagle-eyes: fact stores that must not be empty
  ornaments and must surface low-confidence / stale UI facts before action.

What outcome changes?
  Usable facts above min_score → PASS (exit 0).
  Facts present but all (or share) below min_score → FAIL (exit 1).
  Empty store, missing db, or zero facts → FAIL_LOUD (exit 2).

When NOT to use:
  Never treat an empty fact DB as a silent "no constraints" PASS.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from clickproof.fact import FactObservation, UIFact
from clickproof.scorer import FactScorer
from clickproof.store import FactStore


class ClosedLoopError(ValueError):
    """Raised when the gate refuses empty or unusable fact stores."""


@dataclass(frozen=True)
class GateOutcome:
    """Result of a closed-loop read of a clickproof fact store.

    Attributes:
        ok: True only when a pipeline may continue (PASS).
        verdict: ``PASS``, ``FAIL``, or ``FAIL_LOUD``.
        reason: Human-readable explanation (always non-empty).
        exit_code: 0 PASS, 1 FAIL (stale/low-confidence), 2 FAIL_LOUD (empty).
        fact_count: Number of facts examined.
        usable_count: Facts with score >= min_score.
        stale_count: Facts with score < min_score.
        min_score_seen: Lowest score among facts (None if empty).
    """

    ok: bool
    verdict: str
    reason: str
    exit_code: int
    fact_count: int = 0
    usable_count: int = 0
    stale_count: int = 0
    min_score_seen: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise for JSON reports (eagle-eyes dogfood, CI artifacts)."""
        return {
            "ok": self.ok,
            "verdict": self.verdict,
            "reason": self.reason,
            "exit_code": self.exit_code,
            "fact_count": self.fact_count,
            "usable_count": self.usable_count,
            "stale_count": self.stale_count,
            "min_score_seen": self.min_score_seen,
        }


def _fail_loud(
    reason: str,
    *,
    fact_count: int = 0,
    usable_count: int = 0,
    stale_count: int = 0,
    min_score_seen: float | None = None,
) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL_LOUD",
        reason=reason,
        exit_code=2,
        fact_count=fact_count,
        usable_count=usable_count,
        stale_count=stale_count,
        min_score_seen=min_score_seen,
    )


def gate_facts(
    source: FactStore | Sequence[UIFact] | str | Path,
    *,
    min_score: float = 0.5,
    app_name: str | None = None,
    require_usable: bool = True,
    scorer: FactScorer | None = None,
) -> GateOutcome:
    """Read UI facts and fail loudly when the store is empty or unusable.

    Args:
        source: Open :class:`FactStore`, path to a SQLite db, or a sequence of
            :class:`UIFact` (scores use fact.confidence when no store/obs).
        min_score: Score threshold; facts strictly below this count as stale.
        app_name: Optional filter when reading from a store.
        require_usable: If True, zero usable facts with some present is FAIL.
        scorer: Optional :class:`FactScorer`; defaults to a new instance.

    Returns:
        :class:`GateOutcome` — callers should ``sys.exit(outcome.exit_code)``.
    """
    scorer = scorer or FactScorer()
    owns = False
    store: FactStore | None = None
    try:
        scores: list[float] = []
        if isinstance(source, FactStore):
            store = source
            facts = store.list_facts(app_name=app_name)
            for fact in facts:
                obs = store.get_observations(fact.id)
                scores.append(scorer.score(fact, obs).score)
        elif isinstance(source, (str, Path)):
            path = Path(source)
            if str(source) != ":memory:" and not path.is_file():
                return _fail_loud(f"fact store not found: {path}")
            try:
                store = FactStore(path if str(source) != ":memory:" else ":memory:")
                owns = True
                facts = store.list_facts(app_name=app_name)
                for fact in facts:
                    obs = store.get_observations(fact.id)
                    scores.append(scorer.score(fact, obs).score)
            except Exception as exc:  # noqa: BLE001
                return _fail_loud(f"open fact store failed: {exc.__class__.__name__}: {exc}")
        else:
            facts = list(source)
            # Sequence path: no observations — score from fact.confidence via scorer
            for fact in facts:
                scores.append(scorer.score(fact, []).score)

        if len(facts) == 0:
            return _fail_loud(
                "empty facts — no load-bearing GUI behavioral facts to gate "
                "(write-only store is ornament)"
            )

        usable = sum(1 for s in scores if s >= min_score)
        stale = len(scores) - usable
        min_seen = min(scores) if scores else None

        if require_usable and usable == 0:
            return GateOutcome(
                ok=False,
                verdict="FAIL",
                reason=(
                    f"no usable facts above min_score={min_score}: "
                    f"fact_count={len(facts)} stale={stale} "
                    f"min_score_seen={min_seen}"
                ),
                exit_code=1,
                fact_count=len(facts),
                usable_count=0,
                stale_count=stale,
                min_score_seen=min_seen,
            )

        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason=(
                f"facts ok: count={len(facts)} usable={usable} stale={stale} "
                f"min_score={min_score} min_seen={min_seen}"
            ),
            exit_code=0,
            fact_count=len(facts),
            usable_count=usable,
            stale_count=stale,
            min_score_seen=min_seen,
        )
    finally:
        if owns and store is not None:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass


def assert_usable_facts(
    source: FactStore | Sequence[UIFact] | str | Path,
    **kwargs: Any,
) -> GateOutcome:
    """Gate facts and raise :class:`ClosedLoopError` unless outcome is ok."""
    outcome = gate_facts(source, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome


# ── OVERLAY-CLICK: force:true / overlay intercept must invalidate ─────────────


@dataclass(frozen=True)
class ClickAttempt:
    """One computer-use click against a stored UIFact.

    Farm OVERLAY-CLICK: Playwright ``force=True`` can hit an overlay
    (e.g. X ``#layers``) and never throw — the agent thinks it clicked the
    target. Callers must report whether the *intended* element was hit.
    """

    fact_id: str
    target_element: str
    hit: bool
    force_used: bool = False
    overlay_intercepted: bool = False
    observed_effect: bool = True
    agent_run_id: str = ""
    notes: str = ""

    @property
    def is_miss(self) -> bool:
        """True when the intended target did not receive a real click."""
        if self.overlay_intercepted:
            return True
        if not self.hit:
            return True
        if self.force_used and not self.observed_effect:
            # force:true silent success without effect — classic overlay mask
            return True
        return False

    @property
    def miss_kind(self) -> str | None:
        if not self.is_miss:
            return None
        if self.overlay_intercepted:
            return "overlay_intercept"
        if self.force_used and not self.observed_effect:
            return "force_silent_no_effect"
        if not self.hit:
            return "target_miss"
        return "miss"


@dataclass(frozen=True)
class ClickOutcomeResult:
    """Result of recording a click attempt against a fact."""

    ok: bool
    invalidated: bool
    miss_kind: str | None
    score_before: float
    score_after: float
    confidence_after: float
    observation_confirmed: bool
    fact_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "invalidated": self.invalidated,
            "miss_kind": self.miss_kind,
            "score_before": self.score_before,
            "score_after": self.score_after,
            "confidence_after": self.confidence_after,
            "observation_confirmed": self.observation_confirmed,
            "fact_id": self.fact_id,
            "reason": self.reason,
        }


def apply_click_outcome(
    store: FactStore,
    attempt: ClickAttempt,
    *,
    scorer: FactScorer | None = None,
    miss_confidence_factor: float = 0.25,
    invalidate_confidence: float = 0.05,
) -> ClickOutcomeResult:
    """Record click result: confirm on hit, refute + decay confidence on miss.

    OVERLAY-CLICK product control:
      * hit + effect → confirmed observation (confidence preserved)
      * miss / overlay / force-without-effect → refuted observation and
        hard confidence decay (``miss_confidence_factor`` or floor at
        ``invalidate_confidence``)

    Returns:
        :class:`ClickOutcomeResult` with before/after scores.
    """
    scorer = scorer or FactScorer()
    fact = store.get_fact(attempt.fact_id)
    if fact is None:
        return ClickOutcomeResult(
            ok=False,
            invalidated=False,
            miss_kind="unknown_fact",
            score_before=0.0,
            score_after=0.0,
            confidence_after=0.0,
            observation_confirmed=False,
            fact_id=attempt.fact_id,
            reason=f"fact not found: {attempt.fact_id}",
        )

    obs_before = store.get_observations(fact.id)
    score_before = scorer.score(fact, obs_before).score

    if not attempt.is_miss:
        store.add_observation(
            FactObservation(
                fact_id=fact.id,
                observed_at=time.time(),
                confirmed=True,
                agent_run_id=attempt.agent_run_id or "click",
            )
        )
        score_after = scorer.score(fact, store.get_observations(fact.id)).score
        return ClickOutcomeResult(
            ok=True,
            invalidated=False,
            miss_kind=None,
            score_before=score_before,
            score_after=score_after,
            confidence_after=fact.confidence,
            observation_confirmed=True,
            fact_id=fact.id,
            reason="click hit target; observation confirmed",
        )

    # Miss path — refute and decay
    kind = attempt.miss_kind or "miss"
    store.add_observation(
        FactObservation(
            fact_id=fact.id,
            observed_at=time.time(),
            confirmed=False,
            agent_run_id=attempt.agent_run_id or f"miss:{kind}",
        )
    )
    new_conf = max(invalidate_confidence, fact.confidence * miss_confidence_factor)
    store.set_confidence(fact.id, new_conf)
    updated = store.get_fact(fact.id) or fact
    updated.confidence = new_conf
    score_after = scorer.score(updated, store.get_observations(fact.id)).score

    return ClickOutcomeResult(
        ok=False,
        invalidated=True,
        miss_kind=kind,
        score_before=score_before,
        score_after=score_after,
        confidence_after=new_conf,
        observation_confirmed=False,
        fact_id=fact.id,
        reason=(
            f"OVERLAY-CLICK miss kind={kind}: force_used={attempt.force_used} "
            f"overlay={attempt.overlay_intercepted} hit={attempt.hit} "
            f"effect={attempt.observed_effect}; confidence {fact.confidence:.3f}→{new_conf:.3f} "
            f"score {score_before:.3f}→{score_after:.3f}"
        ),
    )


def gate_click_attempt(
    store: FactStore,
    attempt: ClickAttempt,
    *,
    scorer: FactScorer | None = None,
    min_score_after: float = 0.5,
    apply: bool = True,
    miss_confidence_factor: float = 0.25,
) -> GateOutcome:
    """Gate a click: OVERLAY-CLICK misses FAIL and invalidate the fact.

    Args:
        store: Fact store containing the target fact.
        attempt: Click report from the computer-use runtime.
        min_score_after: After a hit, require score >= this for PASS.
        apply: If True, write refute/confirm + confidence decay to the store.
        miss_confidence_factor: Multiplier applied to confidence on miss.

    Returns:
        FAIL_LOUD if fact missing; FAIL on miss or post-hit unusable score;
        PASS only on verified hit with usable score.
    """
    if apply:
        result = apply_click_outcome(
            store,
            attempt,
            scorer=scorer,
            miss_confidence_factor=miss_confidence_factor,
        )
    else:
        # Dry-run classification only
        fact = store.get_fact(attempt.fact_id)
        if fact is None:
            return _fail_loud(f"fact not found: {attempt.fact_id}")
        scorer = scorer or FactScorer()
        score = scorer.score(fact, store.get_observations(fact.id)).score
        if attempt.is_miss:
            return GateOutcome(
                ok=False,
                verdict="FAIL",
                reason=f"OVERLAY-CLICK miss (dry-run) kind={attempt.miss_kind}",
                exit_code=1,
                fact_count=1,
                usable_count=0,
                stale_count=1,
                min_score_seen=score,
            )
        usable = 1 if score >= min_score_after else 0
        return GateOutcome(
            ok=usable == 1,
            verdict="PASS" if usable else "FAIL",
            reason=f"dry-run hit score={score}",
            exit_code=0 if usable else 1,
            fact_count=1,
            usable_count=usable,
            stale_count=1 - usable,
            min_score_seen=score,
        )

    if result.miss_kind == "unknown_fact":
        return _fail_loud(result.reason)

    if result.invalidated or not result.ok:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=result.reason,
            exit_code=1,
            fact_count=1,
            usable_count=0,
            stale_count=1,
            min_score_seen=result.score_after,
        )

    usable = 1 if result.score_after >= min_score_after else 0
    if usable == 0:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"click hit but score_after={result.score_after:.3f} "
                f"< min_score_after={min_score_after}"
            ),
            exit_code=1,
            fact_count=1,
            usable_count=0,
            stale_count=1,
            min_score_seen=result.score_after,
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=result.reason,
        exit_code=0,
        fact_count=1,
        usable_count=1,
        stale_count=0,
        min_score_seen=result.score_after,
    )


def assert_click_ok(
    store: FactStore,
    attempt: ClickAttempt,
    **kwargs: Any,
) -> GateOutcome:
    """Apply gate_click_attempt and raise :class:`ClosedLoopError` unless ok."""
    outcome = gate_click_attempt(store, attempt, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome


# ── GUI-MEMORY: load known facts at session start (no cold re-discover) ───────

import secrets as _secrets

from clickproof.retriever import FactRetriever


@dataclass(frozen=True)
class SessionMemory:
    """Facts loaded for one computer-use agent session.

    GUI-MEMORY: sessions that skip load while the store already holds usable
    facts for the app re-discover the UI every run — the farm failure mode.
    """

    session_id: str
    app_name: str
    app_version: str | None
    loaded_fact_ids: tuple[str, ...]
    bootstrap_text: str
    loaded_at: float
    usable_count: int
    min_score: float

    @property
    def is_empty(self) -> bool:
        return self.usable_count == 0 or len(self.loaded_fact_ids) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "loaded_fact_ids": list(self.loaded_fact_ids),
            "bootstrap_text": self.bootstrap_text,
            "loaded_at": self.loaded_at,
            "usable_count": self.usable_count,
            "min_score": self.min_score,
            "is_empty": self.is_empty,
        }


def load_session_memory(
    store: FactStore,
    app_name: str,
    *,
    app_version: str | None = None,
    session_id: str | None = None,
    min_score: float = 0.5,
    scorer: FactScorer | None = None,
) -> SessionMemory:
    """Load known UI facts into a session (bootstrap for computer-use agents).

    This is the load-bearing *writer→reader* path for GUI-MEMORY: call at
    session start so the agent does not re-discover controls every run.
    """
    retriever = FactRetriever(store, scorer=scorer)
    pairs = retriever.query(
        app_name=app_name,
        app_version=app_version,
        min_score=min_score,
    )
    # bootstrap_context uses min_score=0.0 for text; we still only *count* usable
    text = retriever.bootstrap_context(
        app_name=app_name,
        app_version=app_version or "unknown",
    )
    ids = tuple(f.id for f, _ in pairs)
    return SessionMemory(
        session_id=session_id or _secrets.token_hex(4),
        app_name=app_name,
        app_version=app_version,
        loaded_fact_ids=ids,
        bootstrap_text=text,
        loaded_at=time.time(),
        usable_count=len(pairs),
        min_score=min_score,
    )


def store_usable_count(
    store: FactStore,
    app_name: str,
    *,
    app_version: str | None = None,
    min_score: float = 0.5,
    scorer: FactScorer | None = None,
) -> int:
    """Count usable facts in the store for *app_name* (no session load)."""
    retriever = FactRetriever(store, scorer=scorer)
    return len(
        retriever.query(app_name=app_name, app_version=app_version, min_score=min_score)
    )


def gate_session_memory(
    store: FactStore,
    session: SessionMemory | None,
    *,
    app_name: str,
    app_version: str | None = None,
    min_score: float = 0.5,
    require_load_when_known: bool = True,
    scorer: FactScorer | None = None,
) -> GateOutcome:
    """Gate session bootstrap against the durable fact store (GUI-MEMORY).

    * Store has usable facts for app, session is ``None`` or empty load →
      **FAIL** (re-discover trap — known UI not injected).
    * Store empty for app → **FAIL_LOUD** (nothing to remember; cold discover
      is expected but not a silent pass of "memory ok").
    * Session loaded usable facts matching store → **PASS**.

    Args:
        store: Durable :class:`FactStore`.
        session: Result of :func:`load_session_memory`, or None if agent skipped.
        app_name: Application under automation.
        require_load_when_known: If True (default), skip-load with known facts fails.
    """
    known = store_usable_count(
        store,
        app_name,
        app_version=app_version,
        min_score=min_score,
        scorer=scorer,
    )

    if known == 0:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=(
                f"GUI-MEMORY: no usable facts for app {app_name!r} "
                f"(min_score={min_score}) — store empty; cold re-discover only, "
                f"not a memory pass"
            ),
            exit_code=2,
            fact_count=0,
            usable_count=0,
            stale_count=0,
            min_score_seen=None,
        )

    if session is None:
        if require_load_when_known:
            return GateOutcome(
                ok=False,
                verdict="FAIL",
                reason=(
                    f"GUI-MEMORY: store has {known} usable fact(s) for {app_name!r} "
                    f"but session never called load_session_memory — refusing "
                    f"cold re-discover"
                ),
                exit_code=1,
                fact_count=known,
                usable_count=0,
                stale_count=known,
                min_score_seen=None,
            )
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason="session is None",
            exit_code=1,
            fact_count=known,
            usable_count=0,
            stale_count=known,
        )

    if session.app_name != app_name:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"GUI-MEMORY: session app {session.app_name!r} != gate app {app_name!r}"
            ),
            exit_code=1,
            fact_count=known,
            usable_count=session.usable_count,
            stale_count=max(0, known - session.usable_count),
        )

    if session.is_empty and require_load_when_known:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"GUI-MEMORY: session {session.session_id!r} loaded 0 usable facts "
                f"but store has {known} for {app_name!r} — incomplete bootstrap"
            ),
            exit_code=1,
            fact_count=known,
            usable_count=0,
            stale_count=known,
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"GUI-MEMORY ok: session {session.session_id!r} loaded "
            f"{session.usable_count}/{known} usable fact(s) for {app_name!r}"
        ),
        exit_code=0,
        fact_count=known,
        usable_count=session.usable_count,
        stale_count=max(0, known - session.usable_count),
        min_score_seen=None,
    )


def assert_session_bootstrapped(
    store: FactStore,
    session: SessionMemory | None,
    *,
    app_name: str,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless session memory gate passes."""
    outcome = gate_session_memory(store, session, app_name=app_name, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
