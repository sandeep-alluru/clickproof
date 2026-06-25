"""behavioral_fraud_pipeline.py — behavioral biometrics for ad click fraud detection.

Simulates a full ad campaign click stream with:
  - 3 real human users with realistic behavioral telemetry
  - 1 IP-rotation bot: rotates IPs per click, invisible to blacklists,
    detectable via sub-10ms click intervals and zero pixel variance
  - 1 residential-proxy bot: residential IPs, detectable via perfectly
    linear mouse trajectories (linearity > 0.95)
  - 1 whitelisted computer-use agent (legitimate QA synthetic monitor)
    that generates bot-like patterns but must NOT be flagged

Demonstrates that IP blacklisting catches 0 of the 2 bot types while
clickproof behavioral scoring catches both, and passes the whitelisted agent.

Run:
    python examples/behavioral_fraud_pipeline.py
"""

from __future__ import annotations

import math
import tempfile
import time

from clickproof.fact import FactObservation, UIFact
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer
from clickproof.store import FactStore

# ---------------------------------------------------------------------------
# Campaign configuration
# ---------------------------------------------------------------------------

CAMPAIGN = "summer-sale-2025"
APP = "ad-click"
NOW = time.time()

# IP ranges that would be on a typical blacklist (data center CIDRs)
BLACKLISTED_IP_PREFIXES = ("10.0.", "192.168.", "172.16.")

# Fraud classification threshold — sessions below this score are flagged
FRAUD_THRESHOLD = 0.6

# Whitelisted agent run IDs — legitimate automation, must not be blocked
AGENT_WHITELIST = {"performedge-synthetic-monitor", "qa-smoke-test-bot"}

# ---------------------------------------------------------------------------
# Simulated click sources
# Columns: session_id, ip_address, inter_click_ms, trajectory_linearity,
#          pixel_variance, dwell_ms, agent_run_id, label
# ---------------------------------------------------------------------------

CLICK_SESSIONS = [
    # Real humans — natural inter-click timing, Brownian trajectories, spread clicks
    ("sess-human-alice",  "203.0.113.42",  1_850.0, 0.21, 4.7, 12_400.0, "",                        "human"),
    ("sess-human-bob",    "198.51.100.17", 3_200.0, 0.34, 5.1,  8_900.0, "",                        "human"),
    ("sess-human-carol",  "93.184.216.34",   975.0, 0.18, 3.9, 22_100.0, "",                        "human"),
    # IP-rotation bot — changes IP per click (none are blacklisted), but
    # clicks arrive in < 8ms and always hit the exact same pixel
    ("sess-bot-rotator",  "185.220.101.5",     7.3, 0.88, 0.1,    320.0, "",                        "bot-ip-rotation"),
    # Residential-proxy bot — uses real residential IPs that would never be
    # blacklisted, but mouse trajectory is perfectly linear (linearity = 0.98)
    ("sess-bot-resid",    "76.188.23.55",    420.0, 0.98, 0.4,  1_200.0, "",                        "bot-residential-proxy"),
    # Whitelisted computer-use agent — PerformEdge QA synthetic monitor.
    # Its click patterns look like a bot (fast, linear) but it is legitimate.
    ("sess-agent-qa",     "10.0.0.5",         12.0, 0.97, 0.2,    100.0, "performedge-synthetic-monitor", "whitelisted-agent"),
]

# Number of click events to simulate per session (more = higher confidence score)
CLICKS_PER_SESSION = 8


# ---------------------------------------------------------------------------
# Helper: classify a single click's behavioral signals
# ---------------------------------------------------------------------------

def _behavior_outcome(inter_click_ms: float, linearity: float, pixel_var: float) -> str:
    """Encode behavioral telemetry into a deterministic outcome string."""
    flags = []
    if inter_click_ms < 10:
        flags.append("sub10ms")
    if linearity > 0.95:
        flags.append("linear-trajectory")
    if pixel_var < 1.0:
        flags.append("zero-pixel-variance")
    return "bot-signal:" + "+".join(flags) if flags else "human-like-behavior"


def _ip_blacklisted(ip: str) -> bool:
    """Simulate IP blacklist check (data center ranges only — misses residential proxies)."""
    return any(ip.startswith(prefix) for prefix in BLACKLISTED_IP_PREFIXES)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    db_path = f"{tmp}/fraud-pipeline.db"
    scorer = FactScorer()

    with FactStore(db_path) as store:
        retriever = FactRetriever(store, scorer)

        print("=" * 68)
        print("clickproof — Behavioral Fraud Detection Pipeline")
        print(f"Campaign: {CAMPAIGN}  |  Sessions: {len(CLICK_SESSIONS)}")
        print("=" * 68)

        # ── Phase 1: Simulate click event stream ──────────────────────────
        print("\n[1] Ingesting click events...\n")
        print(f"  {'Session':<24}  {'IP':<16}  {'Blacklisted?':>12}  {'Outcome':<34}")
        print("  " + "-" * 88)

        for (session_id, ip, inter_ms, linearity, pix_var,
             dwell_ms, agent_run_id, label) in CLICK_SESSIONS:

            outcome = _behavior_outcome(inter_ms, linearity, pix_var)
            blacklisted = _ip_blacklisted(ip)

            # Whitelisted agents: force confirmed=True regardless of behavior
            is_whitelisted = agent_run_id in AGENT_WHITELIST
            is_human_signal = (outcome == "human-like-behavior") or is_whitelisted

            # Record UIFact for this session's behavioral profile
            fact = UIFact(
                app_name=APP,
                app_version=CAMPAIGN,
                element=session_id,
                action="click",
                outcome=outcome,
                context=f"dwell:{int(dwell_ms)}ms",
            )
            store.add_fact(fact)

            # Simulate CLICKS_PER_SESSION observations (with slight timestamp spread)
            for click_num in range(CLICKS_PER_SESSION):
                ts = NOW - (CLICKS_PER_SESSION - click_num) * (inter_ms / 1000.0)
                store.add_observation(FactObservation(
                    fact_id=fact.id,
                    observed_at=ts,
                    confirmed=is_human_signal,
                    agent_run_id=agent_run_id or f"pipeline-run-{label}",
                ))

            bl_tag = "YES (blocked)" if blacklisted else "no"
            print(f"  {session_id:<24}  {ip:<16}  {bl_tag:>12}  {outcome:<34}")

        # ── Phase 2: IP blacklist results ─────────────────────────────────
        print("\n" + "=" * 68)
        print("[2] IP Blacklist Results")
        print("=" * 68)

        ip_blocked = [(s, ip, label) for s, ip, *_, label in CLICK_SESSIONS
                      if _ip_blacklisted(ip)]
        ip_passed = [(s, ip, label) for s, ip, *_, label in CLICK_SESSIONS
                     if not _ip_blacklisted(ip)]

        print(f"\n  Blocked by IP blacklist : {len(ip_blocked)}")
        for s, ip, label in ip_blocked:
            print(f"    - {s} ({ip})  [{label}]")

        print(f"\n  Passed IP blacklist     : {len(ip_passed)}")
        for s, ip, label in ip_passed:
            print(f"    - {s} ({ip})  [{label}]")

        bot_passed_ip = sum(1 for _, _, label in ip_passed if label.startswith("bot"))
        print(f"\n  Bots that BYPASSED IP blacklist: {bot_passed_ip}"
              f" / {sum(1 for *_, l in CLICK_SESSIONS if l.startswith('bot'))}")

        # ── Phase 3: Behavioral scoring results ───────────────────────────
        print("\n" + "=" * 68)
        print("[3] clickproof Behavioral Scoring Results")
        print("=" * 68)
        print()

        all_pairs = retriever.query(app_name=APP, app_version=CAMPAIGN, min_score=0.0)

        header = f"  {'Session':<24}  {'Score':>6}  {'Confirmed':>10}  {'Total':>6}  {'Verdict':<20}  Label"
        print(header)
        print("  " + "-" * (len(header) - 2))

        clickproof_blocked = []
        clickproof_passed = []

        # Build a lookup from session_id to original label
        label_map = {s: label for s, *_, label in CLICK_SESSIONS}

        for fact, score in all_pairs:
            label = label_map.get(fact.element, "unknown")
            verdict = "PASS (human)" if score.score >= FRAUD_THRESHOLD else "BLOCK (bot)"
            if score.score < FRAUD_THRESHOLD:
                clickproof_blocked.append((fact.element, label, score.score))
            else:
                clickproof_passed.append((fact.element, label, score.score))

            marker = "  <-- WHITELISTED AGENT" if label == "whitelisted-agent" else ""
            print(
                f"  {fact.element:<24}  {score.score:>6.3f}  "
                f"{score.confirmed_count:>10}  {score.observation_count:>6}  "
                f"{verdict:<20}  {label}{marker}"
            )

        # ── Phase 4: Summary ──────────────────────────────────────────────
        print("\n" + "=" * 68)
        print("[4] Detection Summary")
        print("=" * 68)

        total_sessions = len(CLICK_SESSIONS)
        bot_sessions = [s for s, *_, l in CLICK_SESSIONS if l.startswith("bot")]
        human_sessions = [s for s, *_, l in CLICK_SESSIONS if l == "human"]
        agent_sessions = [s for s, *_, l in CLICK_SESSIONS if l == "whitelisted-agent"]

        bots_caught = sum(1 for s, label, _ in clickproof_blocked
                          if label.startswith("bot"))
        agents_blocked = sum(1 for s, label, _ in clickproof_blocked
                             if label == "whitelisted-agent")
        humans_blocked = sum(1 for s, label, _ in clickproof_blocked
                             if label == "human")

        print(f"\n  Total sessions          : {total_sessions}")
        print(f"  Real humans             : {len(human_sessions)}")
        print(f"  Fraud bots              : {len(bot_sessions)}")
        print(f"  Whitelisted agents      : {len(agent_sessions)}")
        print()
        print(f"  IP blacklist catch rate : {len(ip_blocked)}/{len(bot_sessions)} bots caught"
              f"  ({0 if not bot_sessions else int(len(ip_blocked)/len(bot_sessions)*100)}%)")
        print(f"  clickproof catch rate   : {bots_caught}/{len(bot_sessions)} bots caught"
              f"  ({0 if not bot_sessions else int(bots_caught/len(bot_sessions)*100)}%)")
        print()
        print(f"  False positives (humans blocked) : {humans_blocked}")
        print(f"  Agent whitelist false positives  : {agents_blocked}")
        print()

        # Bootstrap context (what an agent would see at session start)
        print("=" * 68)
        print("[5] Bootstrap context (injected into agent system prompt)")
        print("=" * 68)
        ctx = retriever.bootstrap_context(APP, CAMPAIGN)
        for line in ctx.split("\n")[:6]:
            print(f"  {line}")
        print("  ...")

print()
print("Done.")
