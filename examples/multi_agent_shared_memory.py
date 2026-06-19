"""multi_agent_shared_memory.py — 5 agents sharing a clickproof database as collective memory.

Demonstrates how multiple independent agents contribute observations to build
a shared understanding of an enterprise SaaS application's UI.

Run:
    python examples/multi_agent_shared_memory.py
"""

from __future__ import annotations

import tempfile
import time

from clickproof.fact import FactObservation, UIFact
from clickproof.scorer import FactScorer
from clickproof.store import FactStore

APP = "enterprise-saas"
VER = "1.0"
NOW = time.time()

# ---------------------------------------------------------------------------
# 8 UIFacts for "enterprise-saas" v1.0
# ---------------------------------------------------------------------------

FACT_DEFS = [
    ("dashboard-home-btn",  "click",  "navigates-to-dashboard"),
    ("settings-gear-icon",  "click",  "opens-settings-panel"),
    ("user-panel-toggle",   "click",  "expands-user-info"),
    ("export-report-btn",   "click",  "downloads-pdf-report"),
    ("search-bar",          "type",   "filters-table-results"),
    ("save-draft-btn",      "click",  "saves-without-publishing"),
    ("notification-bell",   "click",  "opens-notification-tray"),
    # Discovered later by agent-003:
    ("hidden-menu",         "hover",  "opens-admin-panel"),
]

facts: list[UIFact] = [
    UIFact(APP, VER, el, action, outcome)
    for el, action, outcome in FACT_DEFS
]

with tempfile.TemporaryDirectory() as tmp:
    db_path = f"{tmp}/shared.db"
    scorer = FactScorer()

    with FactStore(db_path) as store:

        # Store first 7 facts (fact 8 added by agent-003 below)
        for fact in facts[:7]:
            store.add_fact(fact)

        total_observations = 0

        # ── Agents 001–004 each confirm facts 1–7 ─────────────────────────
        for agent_idx in range(1, 5):
            agent_id = f"agent-{agent_idx:03d}"
            for fi, fact in enumerate(facts[:7]):
                ts = NOW - (5 - agent_idx) * 3600 - fi * 60
                store.add_observation(FactObservation(
                    fact_id=fact.id, observed_at=ts,
                    confirmed=True, agent_run_id=agent_id,
                ))
                total_observations += 1

        # ── Agent-002 finds export-report-btn broken (refuted) ────────────
        broken = facts[3]  # export-report-btn
        store.add_observation(FactObservation(
            fact_id=broken.id, observed_at=NOW - 1200,
            confirmed=False, agent_run_id="agent-002",
        ))
        total_observations += 1

        # ── Agent-003 discovers the hidden-menu (fact 8) ──────────────────
        hidden = facts[7]
        store.add_fact(hidden)
        store.add_observation(FactObservation(
            fact_id=hidden.id, observed_at=NOW - 900,
            confirmed=True, agent_run_id="agent-003",
        ))
        total_observations += 1

        # ── Agents 004 & 005 also confirm the hidden-menu ─────────────────
        for agent_id in ["agent-004", "agent-005"]:
            store.add_observation(FactObservation(
                fact_id=hidden.id, observed_at=NOW - 600,
                confirmed=True, agent_run_id=agent_id,
            ))
            total_observations += 1

        # ── Score all 8 facts and print summary ───────────────────────────
        print("=" * 60)
        print("Collective intelligence — shared fact table")
        print("=" * 60)
        print()

        header = f"  {'Fact':<26}  {'Confirmed':>10}  {'Total':>6}  {'Score':>7}"
        print(header)
        print("  " + "-" * (len(header) - 2))

        total_score = 0.0
        for fact in facts:
            obs = store.get_observations(fact.id)
            sc = scorer.score(fact, obs)
            total_score += sc.score
            flag = "  <- newly discovered" if fact.element == "hidden-menu" else ""
            print(
                f"  {fact.element:<26}  {sc.confirmed_count:>10}  "
                f"{sc.observation_count:>6}  {sc.score:>7.3f}{flag}"
            )

    avg_score = total_score / len(facts)
    unique_agents = 5

    print()
    print(
        f"Collective intelligence: {total_observations} observations from {unique_agents} agents "
        f"-> {len(facts)} facts with avg confidence {avg_score:.2f}"
    )

print()
print("Done.")
