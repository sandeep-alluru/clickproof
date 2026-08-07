"""Closed-loop reader/gate for clickproof (L1 + OVERLAY + GUI-MEMORY + INVISIBLE-INK).

Who reads the output?
  Computer-use agents / CI / eagle-eyes: fact stores that must not be empty
  ornaments and must surface low-confidence / stale UI facts before action;
  task-alignment gates that refuse adversarial goals behind legitimate tasks.

What outcome changes?
  Usable facts above min_score → PASS (exit 0).
  Facts present but all (or share) below min_score → FAIL (exit 1).
  Empty store, missing db, or zero facts → FAIL_LOUD (exit 2).
  Proposed CUA action outside declared task allowlist → FAIL / FAIL_LOUD
  (Invisible Ink adversarial-goal class).

When NOT to use:
  Never treat an empty fact DB as a silent "no constraints" PASS.
  Never execute high-risk UI actions without :func:`gate_task_alignment`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from clickproof.fact import FactObservation, UIFact
from clickproof.scorer import FactScorer
from clickproof.store import FactStore

# High-risk CUA actions that must be explicitly allowed by the task (Invisible Ink).
DEFAULT_HIGH_RISK_CUA_ACTIONS: frozenset[str] = frozenset(
    {
        "delete",
        "remove",
        "rm",
        "wipe",
        "download",
        "export",
        "transfer",
        "send_email",
        "share",
        "paste_credentials",
        "enter_password",
        "grant_permission",
        "allow_access",
        "install",
        "run_shell",
        "exfiltrate",
        "change_password",
        "disable_2fa",
        "export_data",
        "copy_secrets",
        "authorize_oauth",
        "wire_transfer",
        "pay",
        "purchase",
    }
)

# Benign navigation / observation actions (default allow when task is narrow).
DEFAULT_SAFE_CUA_ACTIONS: frozenset[str] = frozenset(
    {
        "click",
        "type",
        "scroll",
        "hover",
        "read",
        "screenshot",
        "wait",
        "focus",
        "close",
        "dismiss",
        "open",
        "navigate",
        "select",
        "confirm",
        "cancel",
        "back",
        "refresh",
    }
)


class ClosedLoopError(ValueError):
    """Raised when the gate refuses empty or unusable fact stores."""


@dataclass(frozen=True)
class GateOutcome:
    """Result of a closed-loop read of a clickproof fact store or task gate.

    Attributes:
        ok: True only when a pipeline may continue (PASS).
        verdict: ``PASS``, ``FAIL``, or ``FAIL_LOUD``.
        reason: Human-readable explanation (always non-empty).
        exit_code: 0 PASS, 1 FAIL (stale/low-confidence), 2 FAIL_LOUD (empty).
        fact_count: Number of facts examined.
        usable_count: Facts with score >= min_score.
        stale_count: Facts with score < min_score.
        min_score_seen: Lowest score among facts (None if empty).
        human_required: True when adversarial/out-of-scope needs human review.
        action: Proposed action when task-alignment gated.
        task: Declared task when task-alignment gated.
        risk: ``safe`` / ``high_risk`` when classified.
    """

    ok: bool
    verdict: str
    reason: str
    exit_code: int
    fact_count: int = 0
    usable_count: int = 0
    stale_count: int = 0
    min_score_seen: float | None = None
    human_required: bool = False
    action: str | None = None
    task: str | None = None
    risk: str | None = None

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
            "human_required": self.human_required,
            "action": self.action,
            "task": self.task,
            "risk": self.risk,
        }


def _fail_loud(
    reason: str,
    *,
    fact_count: int = 0,
    usable_count: int = 0,
    stale_count: int = 0,
    min_score_seen: float | None = None,
    human_required: bool = False,
    action: str | None = None,
    task: str | None = None,
    risk: str | None = None,
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
        human_required=human_required,
        action=action,
        task=task,
        risk=risk,
    )


def _fail(
    reason: str,
    *,
    fact_count: int = 0,
    usable_count: int = 0,
    stale_count: int = 0,
    min_score_seen: float | None = None,
    human_required: bool = True,
    action: str | None = None,
    task: str | None = None,
    risk: str | None = None,
) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL",
        reason=reason,
        exit_code=1,
        fact_count=fact_count,
        usable_count=usable_count,
        stale_count=stale_count,
        min_score_seen=min_score_seen,
        human_required=human_required,
        action=action,
        task=task,
        risk=risk,
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


# ---------------------------------------------------------------------------
# INVISIBLE-INK — adversarial goals behind legitimate CUA tasks
# ---------------------------------------------------------------------------


def _canonical_action(action: str) -> str:
    return (action or "").strip().lower().replace("-", "_").replace(" ", "_")


def is_high_risk_cua_action(
    action: str,
    *,
    extra: Iterable[str] | None = None,
) -> bool:
    """True if *action* is high-risk for computer-use (delete/export/auth/…)."""
    a = _canonical_action(action)
    if not a:
        return True  # empty never safe
    banned = set(DEFAULT_HIGH_RISK_CUA_ACTIONS)
    if extra:
        banned |= {_canonical_action(x) for x in extra}
    head = a.split(":", 1)[0]
    return a in banned or head in banned


def normalize_allowlist(actions: Iterable[str] | None) -> frozenset[str]:
    """Canonicalise an allowlist of action names."""
    if not actions:
        return frozenset()
    return frozenset(_canonical_action(a) for a in actions if str(a).strip())


def infer_allowlist_from_task(task: str) -> frozenset[str]:
    """Heuristic allowlist from declared task text (no LLM).

    Extracts simple verbs that appear as whole words and always includes a
    base set of safe navigation actions. High-risk verbs only enter the
    allowlist if the task text literally mentions them.
    """
    text = (task or "").lower()
    tokens = set(re.findall(r"[a-z_][a-z0-9_]*", text))
    allowed: set[str] = set(DEFAULT_SAFE_CUA_ACTIONS)
    for risk in DEFAULT_HIGH_RISK_CUA_ACTIONS:
        if risk in tokens or risk.replace("_", " ") in text:
            allowed.add(risk)
    # Common synonyms in task phrasing
    if "close" in tokens or "dismiss" in tokens:
        allowed |= {"close", "dismiss", "click", "cancel"}
    if "open" in tokens or "navigate" in tokens:
        allowed |= {"open", "navigate", "click"}
    if "fill" in tokens or "type" in tokens or "enter" in tokens:
        allowed |= {"type", "click", "select", "focus"}
        # "enter password" is high-risk — only if password mentioned
        if "password" in tokens or "credential" in tokens:
            allowed.add("enter_password")
    return frozenset(allowed)


def gate_task_alignment(
    declared_task: str,
    proposed_action: str,
    *,
    allowed_actions: Sequence[str] | None = None,
    target: str | None = None,
    allowed_targets: Sequence[str] | None = None,
    refuse_high_risk_outside_allowlist: bool = True,
    infer_from_task: bool = True,
) -> GateOutcome:
    """Block adversarial CUA actions behind a legitimate task (Invisible Ink).

    Public case (arXiv 2608.02018): *Invisible Ink Threats — Adversarial Goals
    Behind Legitimate Tasks in Computer-Use Agents*. The user/task text is
    benign; UI injection or model drift proposes delete/export/auth that was
    never authorized by the task.

    Rules:

    1. Empty task or empty action → **FAIL_LOUD**
    2. Build allowlist from ``allowed_actions`` and/or ``infer_allowlist_from_task``
    3. High-risk proposed action not in allowlist → **FAIL** (``human_required``)
    4. Any proposed action not in allowlist when allowlist non-empty → **FAIL**
    5. ``target`` not in ``allowed_targets`` when both set → **FAIL**
    6. In-scope action → **PASS**

    Args:
        declared_task: User/task description for this CUA step/session.
        proposed_action: Tool/click/verb the agent wants to run.
        allowed_actions: Explicit allowlist (overrides pure inference if set;
            merged with inference when ``infer_from_task`` is True).
        target: Optional UI target / path / element id.
        allowed_targets: Optional target allowlist.
        refuse_high_risk_outside_allowlist: High-risk out-of-scope → FAIL.
        infer_from_task: Merge heuristic verbs from task text into allowlist.
    """
    task = (declared_task or "").strip()
    action = _canonical_action(proposed_action)
    task_preview = task[:80] if task else None

    if not task:
        return _fail_loud(
            "INVISIBLE-INK: empty declared_task — cannot align actions to a "
            "phantom goal (adversarial free-run)",
            human_required=True,
            action=action or None,
            task=None,
            risk="high_risk",
        )
    if not action:
        return _fail_loud(
            "INVISIBLE-INK: empty proposed_action — cannot gate phantom CUA step",
            human_required=True,
            action=None,
            task=task_preview,
            risk="high_risk",
        )

    allow = set(normalize_allowlist(allowed_actions))
    if infer_from_task:
        allow |= set(infer_allowlist_from_task(task))
    # Explicit allowlist alone is enough even if empty inference
    if allowed_actions is not None and not infer_from_task:
        allow = set(normalize_allowlist(allowed_actions))

    risk = "high_risk" if is_high_risk_cua_action(action) else "safe"
    head = action.split(":", 1)[0]
    in_allow = action in allow or head in allow

    if risk == "high_risk" and refuse_high_risk_outside_allowlist and not in_allow:
        return _fail(
            f"INVISIBLE-INK: high-risk action {action!r} not authorized by task "
            f"{task_preview!r} allowlist={sorted(allow)[:12]} — "
            f"adversarial goal behind legitimate task (arXiv 2608.02018)",
            human_required=True,
            action=action,
            task=task_preview,
            risk=risk,
        )

    if allow and not in_allow:
        return _fail(
            f"INVISIBLE-INK: action {action!r} outside task allowlist "
            f"{sorted(allow)[:12]} for task {task_preview!r}",
            human_required=True,
            action=action,
            task=task_preview,
            risk=risk,
        )

    if target is not None and allowed_targets is not None:
        targets = {str(t).strip() for t in allowed_targets if str(t).strip()}
        t = str(target).strip()
        if targets and t not in targets:
            return _fail(
                f"INVISIBLE-INK: target {t!r} not in allowed_targets "
                f"(task={task_preview!r}) — possible UI injection detour",
                human_required=True,
                action=action,
                task=task_preview,
                risk=risk,
            )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"INVISIBLE-INK ok: action={action!r} risk={risk} "
            f"task={task_preview!r} allowlist_size={len(allow)}"
        ),
        exit_code=0,
        human_required=False,
        action=action,
        task=task_preview,
        risk=risk,
    )


def assert_task_aligned(
    declared_task: str,
    proposed_action: str,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_task_alignment` is ok."""
    outcome = gate_task_alignment(declared_task, proposed_action, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
