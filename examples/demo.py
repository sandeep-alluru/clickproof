"""clickproof demo — end-to-end walkthrough of all core features.

Run from repo root:
    python examples/demo.py
"""

from __future__ import annotations

import tempfile
import time

from clickproof.fact import FactObservation, UIFact
from clickproof.report import print_facts, to_json, to_markdown
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer
from clickproof.store import FactStore

print("=" * 60)
print("clickproof demo")
print("=" * 60)

# ── 1. Create a temporary store ───────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    db_path = f"{tmp}/demo.db"

    with FactStore(db_path) as store:

        # ── 2. Record UI behavioral facts ─────────────────────────────────────

        print("\n[1] Recording UI behavioral facts...")

        facts = [
            UIFact(
                app_name="salesforce",
                app_version="2025.11",
                element="export-csv-button",
                action="click",
                outcome="opens-download-dialog",
                context="reports-page",
                confidence=0.9,
            ),
            UIFact(
                app_name="salesforce",
                app_version="2025.11",
                element="new-record-button",
                action="click",
                outcome="opens-new-record-form",
                context="list-view",
                confidence=1.0,
            ),
            UIFact(
                app_name="gmail",
                app_version="unknown",
                element="compose-button",
                action="click",
                outcome="opens-compose-window",
            ),
        ]

        for fact in facts:
            store.add_fact(fact)
            print(f"  Added: {fact.element} ({fact.app_name})")

        # ── 3. Record observations ─────────────────────────────────────────────

        print("\n[2] Recording observations...")

        now = time.time()
        observations = [
            FactObservation(fact_id=facts[0].id, observed_at=now - 300, confirmed=True,
                            agent_run_id="run_001"),
            FactObservation(fact_id=facts[0].id, observed_at=now - 100, confirmed=True,
                            agent_run_id="run_002"),
            FactObservation(fact_id=facts[1].id, observed_at=now - 200, confirmed=True),
            FactObservation(fact_id=facts[1].id, observed_at=now - 50, confirmed=False,
                            agent_run_id="run_003"),
        ]
        for obs in observations:
            store.add_observation(obs)
            status = "confirmed" if obs.confirmed else "refuted"
            print(f"  Observation ({status}) for fact {obs.fact_id[:8]}...")

        # ── 4. Score and retrieve facts ────────────────────────────────────────

        print("\n[3] Retrieving and scoring facts for salesforce...")

        scorer = FactScorer()
        retriever = FactRetriever(store, scorer)
        pairs = retriever.query(app_name="salesforce", min_score=0.0)

        for fact, score in pairs:
            print(
                f"  [{score.score:.3f}] {fact.element}"
                f" ({score.confirmed_count}/{score.observation_count} obs)"
            )

        # ── 5. Bootstrap context for agent ────────────────────────────────────

        print("\n[4] Bootstrap context for agent system prompt:")
        ctx = retriever.bootstrap_context("salesforce", "2025.11")
        print(ctx)

        # ── 6. Report formatters ───────────────────────────────────────────────

        print("\n[5] JSON output (excerpt):")
        json_str = to_json(pairs)
        import json
        data = json.loads(json_str)
        print(f"  count={data['count']}, first fact: {data['facts'][0]['fact']['element']}")

        print("\n[6] Markdown table:")
        md = to_markdown(pairs)
        for line in md.split("\n")[:5]:
            print(f"  {line}")

        print("\n[7] Rich console table:")
        print_facts(pairs)

print("\nDemo complete.")
