"""CVE — Contextual Variable Overestimation (arXiv 2608.04504 GeoReward).

Public case: Vision-language / multimodal agents overestimate dominant
visual-textual cues while underestimating sparse but decision-critical
contextual variables (market, region, locale, segment). High-volume signals
collapse decisions to a constant output across contexts that should differ.

Product role in clickproof (GUI fact twin):
  Gate CUA / multimodal choices so sparse context keys are present, attended,
  and actually change the decision — refuse dominant-cue collapse.

Non-Ornament:
  Call ``gate_context_variables`` before accepting a market/locale-sensitive
  UI or creative choice. Pair with ``gate_click_attempt`` and
  ``gate_task_alignment``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from clickproof.closed_loop import ClosedLoopError, GateOutcome

# Default sparse contextual variable names (GeoReward market/region class).
DEFAULT_SPARSE_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "market",
        "region",
        "country",
        "locale",
        "geo",
        "segment",
        "audience",
        "timezone",
        "currency",
        "language",
        "tier",
        "cohort",
    }
)

# Dominant high-volume cue keys that often swamp sparse context.
DEFAULT_DOMINANT_KEYS: frozenset[str] = frozenset(
    {
        "product",
        "brand",
        "image",
        "color",
        "title",
        "price",
        "sku",
        "visual",
        "embedding",
        "patch",
        "caption",
    }
)


@dataclass(frozen=True)
class ContextDecision:
    """One multimodal / GUI decision with context inventory.

    Attributes:
        decision_id: Stable id for the choice.
        choice: Selected option label (e.g. creative id, button path).
        sparse_context: Sparse decision-critical vars (market, locale, …).
        dominant_cues: High-volume product/visual signals.
        attended_keys: Context keys the model claims to have used.
        choice_by_context: Optional map context fingerprint → choice
            (for cross-context collapse detection across a batch).
    """

    decision_id: str
    choice: str
    sparse_context: dict[str, Any] = field(default_factory=dict)
    dominant_cues: dict[str, Any] = field(default_factory=dict)
    attended_keys: tuple[str, ...] = ()
    choice_by_context: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "choice": self.choice,
            "sparse_context": dict(self.sparse_context),
            "dominant_cues": dict(self.dominant_cues),
            "attended_keys": list(self.attended_keys),
            "choice_by_context": dict(self.choice_by_context),
        }


@dataclass(frozen=True)
class CVEReport:
    """Analysis of contextual variable overestimation risk."""

    sparse_keys_present: tuple[str, ...]
    sparse_keys_missing: tuple[str, ...]
    attended_sparse: tuple[str, ...]
    ignored_sparse: tuple[str, ...]
    dominant_only: bool
    cross_context_collapse: bool
    collapsed_contexts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sparse_keys_present": list(self.sparse_keys_present),
            "sparse_keys_missing": list(self.sparse_keys_missing),
            "attended_sparse": list(self.attended_sparse),
            "ignored_sparse": list(self.ignored_sparse),
            "dominant_only": self.dominant_only,
            "cross_context_collapse": self.cross_context_collapse,
            "collapsed_contexts": list(self.collapsed_contexts),
        }


def _norm_key(k: str) -> str:
    return (k or "").strip().lower().replace("-", "_").replace(" ", "_")


def _as_decision(item: ContextDecision | dict[str, Any]) -> ContextDecision:
    if isinstance(item, ContextDecision):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"decision must be ContextDecision or dict, got {type(item)!r}")
    did = str(item.get("decision_id") or item.get("id") or "").strip()
    if not did:
        raise ValueError("decision missing decision_id")
    choice = str(item.get("choice") or item.get("selected") or item.get("output") or "")
    sparse = item.get("sparse_context") or item.get("context") or item.get("sparse") or {}
    dominant = item.get("dominant_cues") or item.get("dominant") or item.get("cues") or {}
    if not isinstance(sparse, dict):
        sparse = {"_raw": sparse}
    if not isinstance(dominant, dict):
        dominant = {"_raw": dominant}
    attended = item.get("attended_keys") or item.get("attended") or ()
    if isinstance(attended, str):
        attended_t: tuple[str, ...] = (attended,) if attended.strip() else ()
    else:
        attended_t = tuple(str(x) for x in attended)
    by_ctx = item.get("choice_by_context") or item.get("by_context") or {}
    if not isinstance(by_ctx, Mapping):
        by_ctx = {}
    return ContextDecision(
        decision_id=did,
        choice=choice,
        sparse_context={str(k): v for k, v in sparse.items()},
        dominant_cues={str(k): v for k, v in dominant.items()},
        attended_keys=attended_t,
        choice_by_context={str(k): str(v) for k, v in by_ctx.items()},
    )


def is_sparse_context_key(
    key: str,
    *,
    extra: Iterable[str] | None = None,
) -> bool:
    """True if key is a sparse decision-critical context variable."""
    k = _norm_key(key)
    if not k:
        return False
    keys = set(DEFAULT_SPARSE_CONTEXT_KEYS)
    if extra:
        keys |= {_norm_key(x) for x in extra}
    if k in keys:
        return True
    return any(k.startswith(s + "_") or k.endswith("_" + s) for s in keys)


def context_fingerprint(sparse: Mapping[str, Any]) -> str:
    """Stable fingerprint of sparse context for cross-context collapse checks."""
    parts = []
    for k in sorted(sparse, key=lambda x: _norm_key(str(x))):
        v = sparse[k]
        if v is None or v == "":
            continue
        parts.append(f"{_norm_key(str(k))}={v}")
    return "|".join(parts) if parts else ""


def analyze_cve(
    decision: ContextDecision | dict[str, Any],
    *,
    required_sparse_keys: Iterable[str] | None = None,
    extra_sparse_keys: Iterable[str] | None = None,
    batch: Sequence[ContextDecision | dict[str, Any]] | None = None,
) -> CVEReport:
    """Analyse one decision (and optional batch) for CVE failure modes."""
    d = _as_decision(decision)
    required = [_norm_key(x) for x in (required_sparse_keys or ()) if str(x).strip()]
    sparse_keys = {
        _norm_key(k) for k in d.sparse_context if d.sparse_context.get(k) not in (None, "")
    }
    # also count keys that match sparse taxonomy even if empty later
    present = tuple(
        sorted(
            k
            for k in sparse_keys
            if is_sparse_context_key(k, extra=extra_sparse_keys) or k in required
        )
    )
    missing_list: list[str] = []
    for req in required:
        found = False
        for sk, sv in d.sparse_context.items():
            if _norm_key(sk) == req and sv not in (None, ""):
                found = True
                break
        if not found:
            missing_list.append(req)
    missing = tuple(missing_list)

    attended_norm = {_norm_key(a) for a in d.attended_keys}
    attended_sparse = tuple(sorted(k for k in present if k in attended_norm))
    ignored = tuple(sorted(k for k in present if k not in attended_norm))

    dominant_vals = {_norm_key(k): v for k, v in d.dominant_cues.items() if v not in (None, "")}
    dominant_only = bool(dominant_vals) and (len(present) == 0 or len(attended_sparse) == 0)

    # Cross-context collapse: multiple distinct sparse fingerprints map to same choice
    collapsed: list[str] = []
    by_ctx = dict(d.choice_by_context)
    if batch:
        for item in batch:
            bd = _as_decision(item)
            fp = context_fingerprint(bd.sparse_context)
            if fp:
                by_ctx[fp] = bd.choice
    if len(by_ctx) >= 2:
        # group by choice
        from collections import defaultdict

        groups: dict[str, list[str]] = defaultdict(list)
        for fp, ch in by_ctx.items():
            groups[str(ch)].append(fp)
        for _ch, fps in groups.items():
            if len(fps) >= 2:
                collapsed.extend(fps)

    return CVEReport(
        sparse_keys_present=present,
        sparse_keys_missing=missing,
        attended_sparse=attended_sparse,
        ignored_sparse=ignored,
        dominant_only=dominant_only,
        cross_context_collapse=bool(collapsed),
        collapsed_contexts=tuple(collapsed[:20]),
    )


def gate_context_variables(
    decision: ContextDecision | dict[str, Any] | None = None,
    *,
    required_sparse_keys: Iterable[str] | None = None,
    extra_sparse_keys: Iterable[str] | None = None,
    batch: Sequence[ContextDecision | dict[str, Any]] | None = None,
    require_sparse_inventory: bool = True,
    require_attended: bool = True,
    refuse_dominant_only: bool = True,
    refuse_cross_context_collapse: bool = True,
) -> GateOutcome:
    """Refuse decisions that ignore sparse context (CVE / GeoReward class).

    Rules:

    * No decision when inventory required → **FAIL_LOUD**
    * Required sparse keys missing/empty → **FAIL_LOUD**
    * Sparse present but none attended → **FAIL** (overestimation of dominant cues)
    * Dominant-only decision (dominant cues, no sparse attend) → **FAIL**
    * Cross-context collapse (same choice across distinct markets) → **FAIL**
    * Sparse attended, no collapse → **PASS**
    """
    if decision is None and not batch:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=(
                "CVE/GeoReward: no decision payload — cannot gate contextual "
                "variables without a choice inventory (arXiv 2608.04504)"
            ),
            exit_code=2,
            human_required=True,
        )

    try:
        primary = decision
        if primary is None and batch:
            primary = batch[0]
        assert primary is not None
        d = _as_decision(primary)
        report = analyze_cve(
            d,
            required_sparse_keys=required_sparse_keys,
            extra_sparse_keys=extra_sparse_keys,
            batch=batch,
        )
    except (TypeError, ValueError) as exc:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=f"CVE/GeoReward: invalid decision payload: {exc}",
            exit_code=2,
            human_required=True,
        )

    if require_sparse_inventory:
        has_sparse = bool(report.sparse_keys_present) or bool(
            d.sparse_context and any(v not in (None, "") for v in d.sparse_context.values())
        )
        if required_sparse_keys:
            if report.sparse_keys_missing:
                return GateOutcome(
                    ok=False,
                    verdict="FAIL_LOUD",
                    reason=(
                        f"CVE/GeoReward: required sparse context missing/empty "
                        f"keys={list(report.sparse_keys_missing)[:8]} — "
                        "refuse market/locale decision without context inventory"
                    ),
                    exit_code=2,
                    human_required=True,
                    action=d.choice or d.decision_id,
                )
        elif not has_sparse:
            return GateOutcome(
                ok=False,
                verdict="FAIL_LOUD",
                reason=(
                    "CVE/GeoReward: sparse_context empty — decision-critical "
                    "variables (market/region/locale) not supplied; dominant "
                    "cues alone are not load-bearing"
                ),
                exit_code=2,
                human_required=True,
                action=d.choice or d.decision_id,
            )

    if refuse_cross_context_collapse and report.cross_context_collapse:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"CVE/GeoReward: cross-context collapse — same choice across "
                f"distinct sparse contexts count={len(report.collapsed_contexts)} "
                f"fps={list(report.collapsed_contexts)[:4]} — sparse variables "
                "underestimated (arXiv 2608.04504)"
            ),
            exit_code=1,
            human_required=True,
            action=d.choice or d.decision_id,
        )

    if refuse_dominant_only and report.dominant_only:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"CVE/GeoReward: dominant-cue overestimation decision_id={d.decision_id} "
                f"attended_sparse={list(report.attended_sparse)} "
                f"ignored={list(report.ignored_sparse)[:6]} — refuse collapse to "
                "product/visual-only signal"
            ),
            exit_code=1,
            human_required=True,
            action=d.choice or d.decision_id,
        )

    if require_attended and report.sparse_keys_present and not report.attended_sparse:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"CVE/GeoReward: sparse keys present {list(report.sparse_keys_present)[:6]} "
                f"but none in attended_keys — model ignored decision-critical context"
            ),
            exit_code=1,
            human_required=True,
            action=d.choice or d.decision_id,
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"CVE/GeoReward ok: decision={d.decision_id} "
            f"sparse={list(report.sparse_keys_present)} "
            f"attended={list(report.attended_sparse)} collapse=false"
        ),
        exit_code=0,
        human_required=False,
        action=d.choice or d.decision_id,
    )


def assert_context_variables_ok(
    decision: ContextDecision | dict[str, Any] | None = None,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_context_variables` is ok."""
    outcome = gate_context_variables(decision, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
