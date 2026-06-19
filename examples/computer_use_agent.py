"""computer_use_agent.py — Simulates a computer-use agent automating Salesforce CRM
across 3 sessions, showing how clickproof accumulates and refutes UI facts.

Run:
    python examples/computer_use_agent.py
"""

from __future__ import annotations

import tempfile
import time

from clickproof.fact import FactObservation, UIFact
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer
from clickproof.store import FactStore

APP = "salesforce"
VER = "2025.11"
NOW = time.time()


def _obs(fact_id: str, confirmed: bool, offset_secs: float, run_id: str = "") -> FactObservation:
    return FactObservation(
        fact_id=fact_id,
        observed_at=NOW - offset_secs,
        confirmed=confirmed,
        agent_run_id=run_id,
    )


with tempfile.TemporaryDirectory() as tmp:
    db_path = f"{tmp}/crm.db"

    # ── Session 1: Discovery ─────────────────────────────────────────────────
    print("=" * 60)
    print("Session 1 — discovery")
    print("=" * 60)

    fact_defs = [
        ("export-csv-button", "click",  "opens-download-dialog"),
        ("new-record-button", "click",  "opens-new-record-form"),
        ("filter-dropdown",   "select", "filters-list-view"),
        ("save-button",       "click",  "saves-record"),
        ("delete-button",     "click",  "shows-confirm-dialog"),
    ]

    facts: list[UIFact] = []
    with FactStore(db_path) as store:
        for element, action, outcome in fact_defs:
            fact = UIFact(app_name=APP, app_version=VER, element=element,
                          action=action, outcome=outcome)
            store.add_fact(fact)
            facts.append(fact)

        # Each fact gets 1-2 confirmed observations
        for i, fact in enumerate(facts):
            store.add_observation(_obs(fact.id, True, 3600 + i * 60, "run_s1a"))
            if i % 2 == 0:
                store.add_observation(_obs(fact.id, True, 1800 + i * 30, "run_s1b"))

    print(f"  Discovered {len(facts)} facts")

    # ── Session 2: Load + Use ────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("Session 2 — loading + using")
    print("=" * 60)

    scorer = FactScorer()
    with FactStore(db_path) as store:
        retriever = FactRetriever(store, scorer)
        pairs = retriever.query(APP, VER, min_score=0.0)

        print("\n  Bootstrap context (what the agent sees in its system prompt):\n")
        ctx = retriever.bootstrap_context(APP, VER)
        for line in ctx.split("\n"):
            print(f"    {line}")

        # Agent performs 5 confirmed actions
        for fact, _ in pairs:
            store.add_observation(_obs(fact.id, True, 10, "run_s2"))

        # Re-query after new observations
        pairs2 = retriever.query(APP, VER, min_score=0.0)
        avg_conf = sum(s.score for _, s in pairs2) / max(1, len(pairs2))

    print(f"\n  Session 2: loaded {len(pairs)} facts (avg confidence {avg_conf:.2f})")

    # ── Session 3: UI changed ────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("Session 3 — UI changed")
    print("=" * 60)

    with FactStore(db_path) as store:
        retriever = FactRetriever(store, scorer)
        all_pairs = retriever.query(APP, VER, min_score=0.0)

        export_fact = next(f for f, _ in all_pairs if f.element == "export-csv-button")

        obs_before = store.get_observations(export_fact.id)
        score_before = scorer.score(export_fact, obs_before)

        # The button now behaves differently — add a refuted observation
        store.add_observation(_obs(export_fact.id, False, 5, "run_s3"))

        obs_after = store.get_observations(export_fact.id)
        score_after = scorer.score(export_fact, obs_after)

    print(
        f"\n  Session 3: 1 fact refuted "
        f"(export-csv-button: {score_before.score:.3f} → {score_after.score:.3f})"
    )

print()
print("Done.")
