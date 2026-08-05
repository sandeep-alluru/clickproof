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

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from clickproof.fact import UIFact
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
