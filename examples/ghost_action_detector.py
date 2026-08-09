"""
ghost_action_detector.py — Surface the agent actions that "happened" but left
no trace in the system.

A computer-use agent automates a CRM workflow: it clicks "Save", "Send Email",
and "Schedule Follow-up" on behalf of a sales rep.  In 12 % of runs the agent
logs the action as complete, but the CRM silently failed (network blip, stale
session, modal dialog intercepted the click).  The agent moves on, the rep
assumes the email was sent — the deal is lost.

clickproof maintains a registry of expected UI outcomes.  After each agent
action, the automation framework records an observation: confirmed=True if the
expected state was reached, False otherwise.  Ghost actions — those with no
confirmation or an explicit confirmed=False — surface in the score report.

Run:
    python examples/ghost_action_detector.py
"""
from __future__ import annotations

import tempfile
import time

from clickproof.fact import FactObservation, UIFact
from clickproof.report import to_json
from clickproof.retriever import FactRetriever
from clickproof.store import FactStore

# ── Expected UI facts (registered once at pipeline setup) ─────────────────────

EXPECTED_FACTS: list[UIFact] = [
    UIFact(
        app_name    = "salesforce",
        app_version = "2026.6",
        element     = "save-record-button",
        action      = "click",
        outcome     = "record-saved-toast-visible",
        context     = "opportunity-detail",
        confidence  = 1.0,
    ),
    UIFact(
        app_name    = "salesforce",
        app_version = "2026.6",
        element     = "send-email-button",
        action      = "click",
        outcome     = "email-queued-confirmation",
        context     = "opportunity-detail",
        confidence  = 1.0,
    ),
    UIFact(
        app_name    = "salesforce",
        app_version = "2026.6",
        element     = "schedule-followup-button",
        action      = "click",
        outcome     = "calendar-event-created",
        context     = "opportunity-detail",
        confidence  = 1.0,
    ),
    UIFact(
        app_name    = "salesforce",
        app_version = "2026.6",
        element     = "close-opportunity-button",
        action      = "click",
        outcome     = "stage-set-to-closed-won",
        context     = "opportunity-detail",
        confidence  = 0.95,
    ),
]


# ── Simulated agent run observations across 10 CRM sessions ───────────────────
# confirmed=True means expected outcome was observed; False means ghost action

def build_observations(facts: list[UIFact]) -> list[FactObservation]:
    """Simulate 10 agent runs — some actions ghost in certain sessions."""
    obs: list[FactObservation] = []
    fact_by_element = {f.element: f for f in facts}
    base_ts = time.time() - 10 * 3600   # 10 hours ago

    sessions = [
        # (session_id, {element: confirmed?})
        ("run-001", {"save-record-button": True,  "send-email-button": True,  "schedule-followup-button": True,  "close-opportunity-button": True}),
        ("run-002", {"save-record-button": True,  "send-email-button": False, "schedule-followup-button": True,  "close-opportunity-button": True}),
        ("run-003", {"save-record-button": True,  "send-email-button": True,  "schedule-followup-button": False, "close-opportunity-button": True}),
        ("run-004", {"save-record-button": False, "send-email-button": False, "schedule-followup-button": True,  "close-opportunity-button": True}),
        ("run-005", {"save-record-button": True,  "send-email-button": True,  "schedule-followup-button": True,  "close-opportunity-button": True}),
        ("run-006", {"save-record-button": True,  "send-email-button": False, "schedule-followup-button": False, "close-opportunity-button": False}),
        ("run-007", {"save-record-button": True,  "send-email-button": True,  "schedule-followup-button": True,  "close-opportunity-button": True}),
        ("run-008", {"save-record-button": True,  "send-email-button": True,  "schedule-followup-button": True,  "close-opportunity-button": True}),
        ("run-009", {"save-record-button": True,  "send-email-button": False, "schedule-followup-button": True,  "close-opportunity-button": True}),
        ("run-010", {"save-record-button": True,  "send-email-button": True,  "schedule-followup-button": False, "close-opportunity-button": True}),
    ]

    for i, (run_id, results) in enumerate(sessions):
        ts = base_ts + i * 3600
        for element, confirmed in results.items():
            fact = fact_by_element[element]
            obs.append(FactObservation(
                fact_id      = fact.id,
                observed_at  = ts,
                confirmed    = confirmed,
                agent_run_id = run_id,
            ))

    return obs


def hr(char: str = "─", width: int = 72) -> None:
    print(char * width)


def main() -> None:
    print()
    hr("═")
    print("  Ghost Action Detector — surface unconfirmed agent UI interactions")
    hr("═")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = f"{tmp}/clickproof.db"

        with FactStore(db_path) as store:

            # ── Register expected facts ────────────────────────────────────────
            hr()
            print(f"[1] Registering {len(EXPECTED_FACTS)} expected UI facts...\n")
            for fact in EXPECTED_FACTS:
                store.add_fact(fact)
                print(f"  + {fact.element:35s}  → {fact.outcome}")

            # ── Record observations from 10 agent runs ─────────────────────────
            hr()
            observations = build_observations(EXPECTED_FACTS)
            print(f"[2] Recording observations from 10 agent sessions"
                  f"  ({len(observations)} total)...\n")
            for obs in observations:
                store.add_observation(obs)

            ghost_count = sum(1 for o in observations if not o.confirmed)
            total_count = len(observations)
            print(f"  Total actions   : {total_count}")
            print(f"  Confirmed       : {total_count - ghost_count}")
            print(f"  Ghost (failed)  : {ghost_count}  ({ghost_count/total_count*100:.0f}%)")

            # ── Retrieve and score facts ───────────────────────────────────────
            hr()
            print("[3] Scoring facts by confirmation rate...\n")

            retriever = FactRetriever(store)

            # query() returns (UIFact, FactScore) pairs already scored
            pairs_scored = retriever.query(app_name="salesforce", min_score=0.0)
            pairs_sorted = sorted(pairs_scored, key=lambda p: p[1].score)

            print(f"  {'Element':35s}  {'Score':>6}  {'Confirmed':>9}  {'Ghost':>5}  Status")
            print(f"  {'─'*35}  {'─'*6}  {'─'*9}  {'─'*5}  {'─'*10}")
            for fact, score in pairs_sorted:
                status = "⚠ GHOST-PRONE" if score.score < 0.80 else "✓ reliable"
                obs_for_fact = [o for o in observations if o.fact_id == fact.id]
                confirmed_n  = sum(1 for o in obs_for_fact if o.confirmed)
                ghost_n      = len(obs_for_fact) - confirmed_n
                print(f"  {fact.element:35s}  {score.score:>5.2f}  {confirmed_n:>9}  {ghost_n:>5}  {status}")

            # ── Ghost action report ────────────────────────────────────────────
            fact_by_id = {f.id: f for f in EXPECTED_FACTS}  # shared by sections 4 & 5

            hr()
            print("[4] Ghost action detail (all unconfirmed observations):\n")

            ghost_obs = [o for o in observations if not o.confirmed]
            for obs in ghost_obs:
                fact = fact_by_id.get(obs.fact_id)
                if fact is None:
                    continue
                print(f"  Run {obs.agent_run_id}  |  {fact.element:35s}"
                      f"  |  expected: {fact.outcome}")

            # ── Business impact ────────────────────────────────────────────────
            hr()
            print("[5] Business impact:\n")
            email_obs        = [o for o in observations
                                if fact_by_id.get(o.fact_id) is not None
                                and fact_by_id[o.fact_id].element == "send-email-button"]
            email_ghosts     = sum(1 for o in email_obs if not o.confirmed)
            total_email_runs = len(email_obs)
            print(f"  send-email-button ghost rate : {email_ghosts}/{total_email_runs}"
                  f"  ({email_ghosts/total_email_runs*100:.0f}%)")
            print(f"  → In a team running 500 CRM sessions/month: ~{int(500 * email_ghosts/total_email_runs)}"
                  " missed follow-up emails")
            print()
            print("  Without clickproof: agent marks task complete, rep assumes it succeeded.")
            print("  With clickproof   : ghost surfaces in < 1s; pipeline retries or pages human.")
            print()

            # ── Export ─────────────────────────────────────────────────────────
            hr()
            worst_fact, worst_score = pairs_sorted[0]
            export = to_json([pairs_sorted[0]])   # to_json takes list[tuple[UIFact, FactScore]]
            print(f"[6] Lowest-confidence fact exported ({len(export)} chars JSON)")
            print(f"    Element : {worst_fact.element}")
            print(f"    Score   : {worst_score.score:.2f}  (threshold: 0.80)")
            print("    → Route to alert queue or force human confirmation on next run.\n")


if __name__ == "__main__":
    main()
