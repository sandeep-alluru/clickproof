"""SYNCHAIN — self-synthesized poisoned CUA artifacts (arXiv 2608.06862).

Public case: *SynChain: Inducing Computer-Use Agent Systems to Construct Their
Own Attack Chains*. CUAs persist skills and memory entries; compromise can
propagate **internally** via autonomously synthesized artifacts that look
benign, survive state updates, and bypass one-shot vetting.

Product role in clickproof (STEPJACK / GUI-MEMORY twin):
  Gate loading/reuse of persistent artifacts (skills, memory, workflows) so
  agents refuse unvetted auto-synth payloads, fingerprint mismatches, and
  high-risk action templates hidden in "benign" skill text.

Non-Ornament:
  Call ``gate_artifact_integrity`` before loading skill/memory artifacts into
  a CUA session. Pair with ``gate_session_memory`` and ``gate_multi_step_chain``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from clickproof.closed_loop import (
    DEFAULT_HIGH_RISK_CUA_ACTIONS,
    ClosedLoopError,
    GateOutcome,
    is_high_risk_cua_action,
)
from clickproof.stepjack import DEFAULT_INJECTION_PHRASES, detect_injection_phrases

ARTIFACT_KINDS: frozenset[str] = frozenset(
    {
        "skill",
        "memory",
        "memory_entry",
        "workflow",
        "macro",
        "procedure",
        "playbook",
    }
)

# Benign-looking labels that often wrap poisoned content (paper: structural redundancy).
BENIGN_LABELS: frozenset[str] = frozenset(
    {
        "helper",
        "utility",
        "cleanup",
        "normalize",
        "format",
        "retry",
        "warmup",
        "bootstrap",
        "safe_default",
    }
)


@dataclass(frozen=True)
class PersistentArtifact:
    """A skill, memory entry, or workflow stored for CUA reuse."""

    artifact_id: str
    kind: str = "skill"
    content: str = ""
    label: str = ""
    content_fp: str = ""  # claimed integrity fingerprint (sha256 hex prefix ok)
    vetted: bool = False
    auto_synthesized: bool = False
    source: str = "agent"  # agent | user | external
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "content": self.content,
            "label": self.label,
            "content_fp": self.content_fp,
            "vetted": self.vetted,
            "auto_synthesized": self.auto_synthesized,
            "source": self.source,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class ArtifactIntegrityReport:
    """Analysis of persistent CUA artifacts for SynChain-class poison."""

    artifact_count: int
    unvetted_synth: tuple[str, ...]
    fp_mismatches: tuple[str, ...]
    poison_hits: tuple[str, ...]
    high_risk_templates: tuple[str, ...]
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_count": self.artifact_count,
            "unvetted_synth": list(self.unvetted_synth),
            "fp_mismatches": list(self.fp_mismatches),
            "poison_hits": list(self.poison_hits),
            "high_risk_templates": list(self.high_risk_templates),
            "details": dict(self.details),
        }


def artifact_content_fingerprint(content: str) -> str:
    """SHA-256 hex digest of artifact content (full hex)."""
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _canon(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_").replace("-", "_")


def _as_artifact(item: Any, index: int = 0) -> PersistentArtifact:
    if isinstance(item, PersistentArtifact):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"artifact must be PersistentArtifact or dict, got {type(item)!r}")
    aid = str(item.get("artifact_id") or item.get("id") or item.get("name") or f"art_{index}").strip()
    content = str(item.get("content") or item.get("body") or item.get("text") or "")
    fp = str(item.get("content_fp") or item.get("fingerprint") or item.get("hash") or "")
    return PersistentArtifact(
        artifact_id=aid,
        kind=_canon(str(item.get("kind") or item.get("type") or "skill")),
        content=content,
        label=str(item.get("label") or item.get("title") or aid),
        content_fp=fp,
        vetted=bool(item.get("vetted") or item.get("approved") or False),
        auto_synthesized=bool(
            item.get("auto_synthesized")
            or item.get("self_synthesized")
            or item.get("autonomous")
            or False
        ),
        source=str(item.get("source") or "agent"),
        meta=dict(item.get("meta") or {}) if isinstance(item.get("meta"), dict) else {},
    )


def _extract_action_tokens(content: str) -> list[str]:
    """Pull action-like tokens from skill/procedure text."""
    text = (content or "").lower()
    # verbs after common skill DSL cues
    tokens = re.findall(
        r"\b(?:action|step|do|call|run|invoke)[:\s]+([a-z_][a-z0-9_]*)",
        text,
    )
    # bare high-risk verbs
    for risk in DEFAULT_HIGH_RISK_CUA_ACTIONS:
        if re.search(rf"\b{re.escape(risk)}\b", text):
            tokens.append(risk)
    return tokens


def analyze_artifact_integrity(
    artifacts: Sequence[Any] | None,
    *,
    injection_phrases: Iterable[str] | None = None,
    extra_high_risk: Iterable[str] | None = None,
) -> ArtifactIntegrityReport:
    """Detect unvetted auto-synth, fingerprint drift, and embedded poison."""
    parsed = [_as_artifact(a, i) for i, a in enumerate(artifacts or [])]
    unvetted: list[str] = []
    fp_bad: list[str] = []
    poison: list[str] = []
    hr: list[str] = []

    for art in parsed:
        if art.auto_synthesized and not art.vetted:
            unvetted.append(art.artifact_id)
        if art.content_fp:
            actual = artifact_content_fingerprint(art.content)
            claimed = art.content_fp.strip().lower()
            # full match or claimed is a prefix of actual (short digests)
            matched = (
                actual == claimed
                or (len(claimed) >= 8 and actual.startswith(claimed))
                or (len(claimed) >= 16 and claimed.startswith(actual[:16]))
            )
            if not matched:
                fp_bad.append(art.artifact_id)

        phrases = detect_injection_phrases(
            art.content,
            phrases=injection_phrases if injection_phrases is not None else DEFAULT_INJECTION_PHRASES,
        )
        if phrases:
            poison.append(art.artifact_id)

        actions = _extract_action_tokens(art.content)
        for act in actions:
            if is_high_risk_cua_action(act, extra=extra_high_risk):
                # high-risk template inside benign-labeled auto skill is SynChain class
                label_c = _canon(art.label)
                benign_wrap = any(b in label_c for b in BENIGN_LABELS) or art.auto_synthesized
                if benign_wrap or not art.vetted:
                    hr.append(f"{art.artifact_id}:{act}")
                    break

    return ArtifactIntegrityReport(
        artifact_count=len(parsed),
        unvetted_synth=tuple(dict.fromkeys(unvetted)),
        fp_mismatches=tuple(dict.fromkeys(fp_bad)),
        poison_hits=tuple(dict.fromkeys(poison)),
        high_risk_templates=tuple(dict.fromkeys(hr)),
        details={"kinds": sorted({a.kind for a in parsed})},
    )


def gate_artifact_integrity(
    artifacts: Sequence[Any] | None,
    *,
    claim_loaded: bool = False,
    require_artifacts: bool = True,
    refuse_unvetted_synth: bool = True,
    refuse_fp_mismatch: bool = True,
    refuse_poison: bool = True,
    refuse_high_risk_templates: bool = True,
    injection_phrases: Iterable[str] | None = None,
    extra_high_risk: Iterable[str] | None = None,
) -> GateOutcome:
    """Refuse loading self-synthesized or poisoned persistent CUA artifacts.

    Public case: arXiv 2608.06862 SynChain — attack chains embedded in
    agent-synthesized skills/memory that survive internal state updates.

    Rules:

    1. ``claim_loaded`` with zero artifacts → **FAIL_LOUD**
    2. Empty inventory when required → **FAIL_LOUD**
    3. Auto-synthesized + not vetted → **FAIL**
    4. Claimed content fingerprint mismatch → **FAIL**
    5. Injection phrases in artifact body → **FAIL**
    6. High-risk action templates in unvetted/benign-wrapped skills → **FAIL**
    7. Vetted clean artifacts → **PASS**
    """
    if not artifacts:
        if claim_loaded or require_artifacts:
            return GateOutcome(
                ok=False,
                verdict="FAIL_LOUD",
                reason=(
                    "SYNCHAIN: empty artifact inventory — cannot claim loaded "
                    f"skills/memory without persistent artifacts "
                    f"(claim_loaded={claim_loaded}; arXiv 2608.06862)"
                ),
                exit_code=2,
                human_required=True,
                risk="high_risk",
            )
        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason="SYNCHAIN: no artifacts required",
            exit_code=0,
            risk="safe",
        )

    try:
        report = analyze_artifact_integrity(
            artifacts,
            injection_phrases=injection_phrases,
            extra_high_risk=extra_high_risk,
        )
    except (TypeError, ValueError) as exc:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=f"SYNCHAIN: invalid artifact payload: {exc}",
            exit_code=2,
            human_required=True,
            risk="high_risk",
        )

    n = report.artifact_count

    if refuse_unvetted_synth and report.unvetted_synth:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"SYNCHAIN: {len(report.unvetted_synth)} auto-synthesized artifact(s) "
                f"not vetted {list(report.unvetted_synth)[:8]} — refuse self-built "
                f"attack-chain carriers (arXiv 2608.06862)"
            ),
            exit_code=1,
            human_required=True,
            fact_count=n,
            stale_count=len(report.unvetted_synth),
            risk="high_risk",
        )

    if refuse_fp_mismatch and report.fp_mismatches:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"SYNCHAIN: content fingerprint mismatch on "
                f"{list(report.fp_mismatches)[:8]} — refuse tampered or "
                f"post-update poison that drifted from claimed integrity"
            ),
            exit_code=1,
            human_required=True,
            fact_count=n,
            stale_count=len(report.fp_mismatches),
            risk="high_risk",
        )

    if refuse_poison and report.poison_hits:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"SYNCHAIN: injection/poison phrases in artifacts "
                f"{list(report.poison_hits)[:8]} — refuse persistent "
                f"self-synthesized attack content"
            ),
            exit_code=1,
            human_required=True,
            fact_count=n,
            stale_count=len(report.poison_hits),
            risk="high_risk",
        )

    if refuse_high_risk_templates and report.high_risk_templates:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"SYNCHAIN: high-risk action templates embedded in "
                f"unvetted/benign-labeled artifacts "
                f"{list(report.high_risk_templates)[:8]} — refuse covert "
                f"attack-chain skills (arXiv 2608.06862)"
            ),
            exit_code=1,
            human_required=True,
            fact_count=n,
            stale_count=len(report.high_risk_templates),
            risk="high_risk",
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"SYNCHAIN ok: artifacts={n} unvetted_synth=0 fp_ok poison=0 "
            f"claim_loaded={claim_loaded}"
        ),
        exit_code=0,
        fact_count=n,
        usable_count=n,
        human_required=False,
        risk="safe",
    )


def assert_artifacts_ok(
    artifacts: Sequence[Any] | None,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_artifact_integrity` is ok."""
    outcome = gate_artifact_integrity(artifacts, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
