"""StepJack multi-step indirect prompt injection gate (arXiv 2608.06477).

Public case: *StepJack: Benchmarking Computer-Use Agent Safety Against
Multi-Step Indirect Prompt Injection*. Adversarial goals are decomposed into
innocuous-looking sub-steps and distributed across a chain of pages along the
CUA navigation path. Single-step ``gate_task_alignment`` (INVISIBLE-INK) only
sees one action; it misses cumulative / cross-page injection chains.

Product role in clickproof:
  Analyze and gate navigation+action chains so agents refuse when:
  - pages inject off-task instructions
  - off-domain hosts appear on the path
  - multi-step composition yields high-risk outcomes without any single
    step looking high-risk alone

Non-Ornament:
  Call ``gate_multi_step_chain`` before accepting a multi-page CUA trajectory
  as task-complete. Pair with ``gate_task_alignment`` per step.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from clickproof.closed_loop import (
    DEFAULT_HIGH_RISK_CUA_ACTIONS,
    ClosedLoopError,
    GateOutcome,
    infer_allowlist_from_task,
    is_high_risk_cua_action,
)

# Phrases commonly planted in page content for indirect injection.
DEFAULT_INJECTION_PHRASES: frozenset[str] = frozenset(
    {
        "ignore previous instructions",
        "ignore all previous",
        "disregard previous",
        "instead of the task",
        "do the following instead",
        "also execute",
        "also send",
        "send credentials",
        "exfiltrate",
        "paste your password",
        "enter your api key",
        "download and run",
        "open a new tab and",
        "navigate away and",
        "transfer funds",
        "wire money",
        "delete all",
        "rm -rf",
        "grant admin",
        "disable security",
        "bypass approval",
    }
)

# Action pairs / sequences that compose to high risk even if each step is soft.
DEFAULT_CUMULATIVE_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("copy", "paste"),
    ("copy", "submit"),
    ("download", "run"),
    ("download", "execute"),
    ("download", "open"),
    ("fill", "submit"),
    ("type", "submit"),
    ("grant", "approve"),
    ("enable", "confirm"),
    ("export", "send"),
    ("export", "upload"),
    ("screenshot", "upload"),
    ("read", "post"),
    ("read", "send"),
)


@dataclass(frozen=True)
class NavStep:
    """One step on a CUA navigation / action chain.

    Attributes:
        step_id: Stable id for the step.
        action: Proposed CUA action (click, type, navigate, download, …).
        page_url: URL or page id where the action occurs.
        target: Optional UI target / selector / label.
        page_snippet: Visible text / HTML snippet (injection surface).
        host: Optional explicit host (overrides parse of page_url).
    """

    step_id: str
    action: str
    page_url: str = ""
    target: str = ""
    page_snippet: str = ""
    host: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "page_url": self.page_url,
            "target": self.target,
            "page_snippet": self.page_snippet,
            "host": self.host,
        }


@dataclass(frozen=True)
class StepJackReport:
    """Analysis of a multi-step chain for StepJack-class injection."""

    step_count: int
    high_risk_steps: tuple[str, ...]
    injection_steps: tuple[str, ...]
    off_domain_hosts: tuple[str, ...]
    cumulative_hits: tuple[str, ...]
    decomposition_depth: int
    task: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_count": self.step_count,
            "high_risk_steps": list(self.high_risk_steps),
            "injection_steps": list(self.injection_steps),
            "off_domain_hosts": list(self.off_domain_hosts),
            "cumulative_hits": list(self.cumulative_hits),
            "decomposition_depth": self.decomposition_depth,
            "task": self.task,
            "details": dict(self.details),
        }


def _canon_action(action: str) -> str:
    return (action or "").strip().lower().replace(" ", "_").replace("-", "_")


def _host_of(step: NavStep) -> str:
    if step.host:
        return step.host.strip().lower()
    url = (step.page_url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        # bare host or path
        if "/" not in url and "." in url:
            return url.lower()
        return ""
    try:
        parsed = urlparse(url)
        return (parsed.hostname or "").lower()
    except Exception:
        return ""


def _as_step(item: Any) -> NavStep:
    if isinstance(item, NavStep):
        return item
    if isinstance(item, dict):
        sid = str(item.get("step_id") or item.get("id") or "").strip()
        action = str(item.get("action") or "").strip()
        if not sid:
            # synthesize from index-like fields
            sid = str(item.get("page_url") or item.get("url") or action or "step")
        return NavStep(
            step_id=sid,
            action=action,
            page_url=str(item.get("page_url") or item.get("url") or ""),
            target=str(item.get("target") or ""),
            page_snippet=str(
                item.get("page_snippet")
                or item.get("snippet")
                or item.get("page_text")
                or item.get("content")
                or ""
            ),
            host=str(item.get("host") or ""),
        )
    raise TypeError(f"unsupported step type: {type(item)!r}")


def detect_injection_phrases(
    text: str,
    *,
    phrases: Iterable[str] | None = None,
) -> list[str]:
    """Return injection phrases found in *text* (case-insensitive)."""
    blob = (text or "").lower()
    if not blob:
        return []
    found: list[str] = []
    for p in phrases if phrases is not None else DEFAULT_INJECTION_PHRASES:
        pl = p.lower()
        if pl and pl in blob:
            found.append(p)
    return found


def hosts_from_task(task: str) -> set[str]:
    """Extract likely allowed hosts mentioned in the task string.

    Hosts come from ``urlparse(...).hostname`` only (CodeQL-safe).
    """
    task = task or ""
    hosts: set[str] = set()
    for m in re.finditer(r"https?://[^\s]+", task, flags=re.I):
        try:
            host = urlparse(m.group(0)).hostname
        except Exception:
            host = None
        if host:
            hosts.add(host.lower())
    for m in re.finditer(
        r"\b([a-z0-9][-a-z0-9]*\.(?:com|org|net|io|dev|app|gov|edu)(?:\.[a-z]{2})?)\b",
        task,
        flags=re.I,
    ):
        try:
            host = urlparse("https://" + m.group(1)).hostname
        except Exception:
            host = None
        if not host:
            continue
        host_l = host.lower()
        if any(h == host_l or h.endswith("." + host_l) for h in hosts):
            continue
        hosts.add(host_l)
    return hosts


def analyze_multi_step_chain(
    steps: Sequence[Any] | None,
    task: str,
    *,
    allowed_hosts: Sequence[str] | None = None,
    injection_phrases: Iterable[str] | None = None,
    cumulative_patterns: Sequence[Sequence[str]] | None = None,
    extra_high_risk: Iterable[str] | None = None,
) -> StepJackReport:
    """Summarize multi-step CUA chain for StepJack-class threats (no gate)."""
    parsed = [_as_step(s) for s in (steps or [])]
    task_s = task or ""
    allow = set(infer_allowlist_from_task(task_s))
    allowed_host_set = {
        str(h).strip().lower() for h in (allowed_hosts or []) if h and str(h).strip()
    }
    if not allowed_host_set:
        allowed_host_set = hosts_from_task(task_s)

    high_risk: list[str] = []
    injections: list[str] = []
    off_domain: list[str] = []
    actions_canon: list[str] = []

    for st in parsed:
        act = _canon_action(st.action)
        actions_canon.append(act)
        if (
            act
            and is_high_risk_cua_action(act, extra=extra_high_risk)
            and act not in allow
            and act.split(":", 1)[0] not in allow
        ):
            # high-risk action not covered by task allowlist
            high_risk.append(st.step_id)
        phrases = detect_injection_phrases(st.page_snippet, phrases=injection_phrases)
        if phrases:
            injections.append(st.step_id)
        host = _host_of(st)
        if (
            host
            and allowed_host_set
            and host not in allowed_host_set
            and not any(host == a or host.endswith("." + a) for a in allowed_host_set)
        ):
            # host outside allowlist (including subdomains of allowed)
            off_domain.append(host)

    patterns = (
        cumulative_patterns if cumulative_patterns is not None else DEFAULT_CUMULATIVE_PATTERNS
    )
    cum_hits: list[str] = []
    for pat in patterns:
        pat_c = [_canon_action(x) for x in pat]
        # subsequence match in order
        i = 0
        for a in actions_canon:
            if i < len(pat_c) and (a == pat_c[i] or a.startswith(pat_c[i] + "_")):
                i += 1
        if i >= len(pat_c) and pat_c:
            cum_hits.append("→".join(pat_c))

    # decomposition depth: number of distinct pages/hosts in chain
    pages = {st.page_url or _host_of(st) or st.step_id for st in parsed}
    depth = len(pages)

    return StepJackReport(
        step_count=len(parsed),
        high_risk_steps=tuple(high_risk),
        injection_steps=tuple(injections),
        off_domain_hosts=tuple(dict.fromkeys(off_domain)),
        cumulative_hits=tuple(cum_hits),
        decomposition_depth=depth,
        task=task_s,
        details={
            "actions": actions_canon,
            "allowed_hosts": sorted(allowed_host_set),
            "task_allowlist": sorted(allow),
        },
    )


def gate_multi_step_chain(
    steps: Sequence[Any] | None,
    task: str,
    *,
    allowed_hosts: Sequence[str] | None = None,
    claim_task_complete: bool = False,
    max_decomposition_depth: int | None = None,
    refuse_injection_phrases: bool = True,
    refuse_off_domain: bool = True,
    refuse_cumulative: bool = True,
    refuse_high_risk_steps: bool = True,
    require_steps: bool = True,
    injection_phrases: Iterable[str] | None = None,
    cumulative_patterns: Sequence[Sequence[str]] | None = None,
    extra_high_risk: Iterable[str] | None = None,
) -> GateOutcome:
    """Refuse multi-step CUA chains with StepJack-class injection.

    Public case: arXiv 2608.06477 StepJack — multi-step indirect prompt
    injection distributes an adversarial goal across innocuous sub-steps on
    a navigation path. Single-step task alignment misses the chain.

    Rules:

    1. Empty task → **FAIL_LOUD**
    2. ``claim_task_complete`` with zero steps → **FAIL_LOUD**
    3. High-risk step action not authorized by task → **FAIL**
    4. Page snippet contains injection phrases → **FAIL**
    5. Host on chain outside allowed/task hosts → **FAIL**
    6. Cumulative soft-action pattern (copy→paste, download→run, …) → **FAIL**
       when not authorized by task allowlist for the terminal risk
    7. ``decomposition_depth`` > ``max_decomposition_depth`` when set → **FAIL**
    8. Clean in-domain chain → **PASS**

    Args:
        steps: Navigation/action steps (:class:`NavStep` or dicts).
        task: Declared user task.
        allowed_hosts: Host allowlist (default: hosts mentioned in task).
        claim_task_complete: Trajectory claimed as finished task.
        max_decomposition_depth: Optional cap on distinct pages/hosts.
        refuse_high_risk_steps: Refuse high-risk actions not in task allowlist.
        refuse_injection_phrases: Refuse page snippets with injection phrases.
        refuse_off_domain: Refuse hosts outside allowed/task hosts.
        refuse_cumulative: Refuse cumulative multi-step risk patterns.
    """
    task_s = (task or "").strip()
    if not task_s:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=(
                "STEPJACK: empty task - cannot gate multi-step CUA chain "
                "(arXiv 2608.06477 multi-step indirect prompt injection)"
            ),
            exit_code=2,
            human_required=True,
            task=None,
            risk="high_risk",
        )

    try:
        report = analyze_multi_step_chain(
            steps,
            task_s,
            allowed_hosts=allowed_hosts,
            injection_phrases=injection_phrases,
            cumulative_patterns=cumulative_patterns,
            extra_high_risk=extra_high_risk,
        )
    except (TypeError, ValueError) as exc:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=f"STEPJACK: invalid step payload: {exc}",
            exit_code=2,
            human_required=True,
            task=task_s,
            risk="high_risk",
        )

    n = report.step_count
    if require_steps and claim_task_complete and n == 0:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=(
                "STEPJACK: claim_task_complete with zero steps - phantom "
                "multi-step trajectory (arXiv 2608.06477)"
            ),
            exit_code=2,
            human_required=True,
            task=task_s,
            fact_count=0,
            risk="high_risk",
        )

    if require_steps and n == 0 and not claim_task_complete:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason="STEPJACK: empty step chain - nothing to gate",
            exit_code=2,
            human_required=True,
            task=task_s,
            risk="high_risk",
        )

    if refuse_high_risk_steps and report.high_risk_steps:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"STEPJACK: high-risk actions on steps {list(report.high_risk_steps)} "
                f"not authorized by task allowlist - refuse multi-step injection "
                f"or Invisible-Ink twin (arXiv 2608.06477 / 2608.02018)"
            ),
            exit_code=1,
            human_required=True,
            task=task_s,
            fact_count=n,
            stale_count=len(report.high_risk_steps),
            action=report.high_risk_steps[0],
            risk="high_risk",
        )

    if refuse_injection_phrases and report.injection_steps:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"STEPJACK: injection phrases in page content on steps "
                f"{list(report.injection_steps)} - multi-step indirect prompt "
                f"injection along navigation path (arXiv 2608.06477)"
            ),
            exit_code=1,
            human_required=True,
            task=task_s,
            fact_count=n,
            stale_count=len(report.injection_steps),
            risk="high_risk",
        )

    if refuse_off_domain and report.off_domain_hosts:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"STEPJACK: off-domain hosts on chain {list(report.off_domain_hosts)} "
                f"outside task/allowlist {report.details.get('allowed_hosts')} - "
                f"refuse cross-page injection path"
            ),
            exit_code=1,
            human_required=True,
            task=task_s,
            fact_count=n,
            stale_count=len(report.off_domain_hosts),
            risk="high_risk",
        )

    if refuse_cumulative and report.cumulative_hits:
        # Allow cumulative if task allowlist covers terminal high-risk of pattern
        allow = set(report.details.get("task_allowlist") or [])
        residual = []
        for hit in report.cumulative_hits:
            terminal = hit.split("→")[-1] if "→" in hit else hit
            # if task explicitly allows export/send/etc terminal, skip
            if terminal in allow:
                continue
            residual.append(hit)
        if residual:
            return GateOutcome(
                ok=False,
                verdict="FAIL",
                reason=(
                    f"STEPJACK: cumulative multi-step risk patterns {residual} "
                    f"across innocuous sub-steps - refuse decomposed adversarial "
                    f"goal (arXiv 2608.06477)"
                ),
                exit_code=1,
                human_required=True,
                task=task_s,
                fact_count=n,
                stale_count=len(residual),
                risk="high_risk",
            )

    if max_decomposition_depth is not None and report.decomposition_depth > max_decomposition_depth:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"STEPJACK: decomposition_depth={report.decomposition_depth} "
                f"exceeds max={max_decomposition_depth} - refuse deep multi-page "
                f"injection surface"
            ),
            exit_code=1,
            human_required=True,
            task=task_s,
            fact_count=n,
            risk="high_risk",
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"STEPJACK ok: steps={n} depth={report.decomposition_depth} "
            f"injections=0 off_domain=0 cumulative=0"
        ),
        exit_code=0,
        fact_count=n,
        usable_count=n,
        human_required=False,
        task=task_s,
        risk="safe",
    )


def assert_multi_step_ok(
    steps: Sequence[Any] | None,
    task: str,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_multi_step_chain` is ok."""
    outcome = gate_multi_step_chain(steps, task, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome


# Re-export high-risk set reference for callers
HIGH_RISK_CUA_ACTIONS = DEFAULT_HIGH_RISK_CUA_ACTIONS
