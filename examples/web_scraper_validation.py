"""web_scraper_validation.py — Web scraping agent tracking CSS selectors for amazon.com.

Demonstrates staleness decay and score drop from refuted observations.

Run:
    python examples/web_scraper_validation.py
"""

from __future__ import annotations

import math
import tempfile
import time

from clickproof.fact import FactObservation, UIFact
from clickproof.scorer import FactScore, FactScorer
from clickproof.store import FactStore

APP = "amazon.com"
VER = "2025"
NOW = time.time()


# ---------------------------------------------------------------------------
# Helper: recompute a score as if 'now' were some future time
# ---------------------------------------------------------------------------

def score_at_time(fact: UIFact, observations: list[FactObservation], future_now: float) -> FactScore:
    """Compute FactScore using *future_now* as the current time (staleness projection)."""
    count = len(observations)
    if count == 0:
        staleness_days = (future_now - fact.recorded_at) / 86400.0
        decay = math.exp(-0.1 * staleness_days)
        s = fact.confidence * decay
        return FactScore(
            fact_id=fact.id, app_name=fact.app_name, app_version=fact.app_version,
            element=fact.element, score=max(0.0, min(1.0, s)),
            observation_count=0, confirmed_count=0,
            last_observed=fact.recorded_at, staleness_days=staleness_days,
        )

    confirmed_count = sum(1 for o in observations if o.confirmed)
    last_observed = max(o.observed_at for o in observations)
    staleness_days = (future_now - last_observed) / 86400.0
    base_ratio = confirmed_count / count
    staleness_decay = math.exp(-0.1 * staleness_days)
    count_boost = min(1.0, 0.5 + 0.5 * math.log(1 + count) / math.log(11))
    s = base_ratio * staleness_decay * count_boost

    return FactScore(
        fact_id=fact.id, app_name=fact.app_name, app_version=fact.app_version,
        element=fact.element, score=max(0.0, min(1.0, s)),
        observation_count=count, confirmed_count=confirmed_count,
        last_observed=last_observed, staleness_days=staleness_days,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    db_path = f"{tmp}/amazon.db"

    facts = [
        UIFact(APP, VER, "#add-to-cart-button", "click", "adds-item-to-cart"),
        UIFact(APP, VER, ".price-display",       "read",  "shows-current-price"),
        UIFact(APP, VER, "#buy-now",             "click", "opens-checkout"),
    ]

    scorer = FactScorer()

    with FactStore(db_path) as store:
        for fact in facts:
            store.add_fact(fact)

        # ── 2. Simulate 10 scraping sessions over last 30 days ───────────────
        # Most recent observation is just 2 hours ago → low staleness, high score.
        for i in range(10):
            ts = NOW - (10 - i) * 7200  # spread over ~20 hours, last one 2h ago
            for fact in facts:
                store.add_observation(FactObservation(
                    fact_id=fact.id, observed_at=ts,
                    confirmed=True, agent_run_id=f"scrape-{i:02d}",
                ))

        # ── 3. Score after 10 confirmed sessions ─────────────────────────────
        print("=" * 60)
        print("After 10 confirmed sessions (last 30 days)")
        print("=" * 60)
        scores_initial: dict[str, FactScore] = {}
        for fact in facts:
            obs = store.get_observations(fact.id)
            sc = scorer.score(fact, obs)
            scores_initial[fact.element] = sc
            print(f"  {fact.element:<28}  score={sc.score:.3f}  ({sc.confirmed_count}/{sc.observation_count})")

        # ── 4. Site update — add 3 refuted observations ───────────────────────
        for fact in facts:
            store.add_observation(FactObservation(
                fact_id=fact.id, observed_at=NOW,
                confirmed=False, agent_run_id="scrape-update",
            ))

        # ── 5. Re-score after refutation ─────────────────────────────────────
        print()
        print("=" * 60)
        print("After site update (3 refuted observations)")
        print("=" * 60)
        scores_after: dict[str, FactScore] = {}
        all_obs_after: dict[str, list[FactObservation]] = {}
        for fact in facts:
            obs = store.get_observations(fact.id)
            all_obs_after[fact.element] = obs
            sc = scorer.score(fact, obs)
            scores_after[fact.element] = sc
            print(f"  {fact.element:<28}  score={sc.score:.3f}  ({sc.confirmed_count}/{sc.observation_count})")

        # ── 6. Staleness projection — 7 days from now ────────────────────────
        future_now = NOW + 7 * 86400
        print()
        print("=" * 60)
        print("Projected scores 7 days from now (if no re-validation)")
        print("=" * 60)
        for fact in facts:
            obs = all_obs_after[fact.element]
            sc_proj = score_at_time(fact, obs, future_now)
            print(f"  {fact.element:<28}  score={sc_proj.score:.3f}")

    # ── 7. Warning banner ────────────────────────────────────────────────────
    print()
    changes = ", ".join(
        f"{el} ({scores_initial[el].score:.2f}→{scores_after[el].score:.2f})"
        for el in [f.element for f in facts]
    )
    print(f"Warning: CSS selectors for amazon.com need re-validation: {changes}")

print()
print("Done.")
