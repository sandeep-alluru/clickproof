# Case Study: Persistent CSS Selector Memory for High-Volume Web Data Extraction

## Company Profile

**DataHarvest** is a web data extraction company based in Seattle, WA. With 30 engineers, they build AI agents that scrape structured data from 500+ e-commerce, financial, and news websites on behalf of enterprise customers. Their agents extract product prices, financial disclosures, and editorial content for market intelligence platforms. They process roughly 3 million page scrapes per month.

## The Problem

CSS selectors are the fundamental unit of web scraping — they define which elements on a page contain the data the agent needs. Selectors change when websites are redesigned. The problem DataHarvest faced was twofold.

**First, re-validation waste.** Their agents had no memory of which selectors had worked in previous runs. Each scraping session began with a validation phase: the agent would attempt a set of candidate selectors, confirm which ones returned data, and discard the failures. This re-validation consumed the first 25-30% of every scraping run — time spent rediscovering information the agent already knew from yesterday's run. For their 3 million monthly scrapes, this represented approximately 750,000 scrapes' worth of wasted validation work.

**Second, silent redesign breakage.** When Amazon redesigned their product listing page in November 2024, DataHarvest's agents had no mechanism to detect the change proactively. Every one of their 200 extraction rules targeting Amazon product pages failed silently on the first run after the redesign — agents attempted the old selectors, got empty results or errors, and returned empty datasets. Customers noticed missing data 6-12 hours later, generating 47 support tickets in a single day.

The investigation revealed that only 12 of the 200 rules actually needed to be updated — Amazon had changed the product title selector and the price selector, but the review count, rating, ASIN, and seller information selectors were unchanged. But with no record of which selectors had worked historically, engineers had to re-test all 200 rules from scratch.

## Solution Architecture

DataHarvest integrated clickproof as their CSS selector memory layer. Every confirmed selector becomes a `UIFact`. Agents start each session by loading known-good selectors via `bootstrap_context()` rather than re-discovering them. The `FactScorer` staleness decay identifies selectors that haven't been confirmed recently, enabling pre-run impact assessment before scraping begins.

```
┌──────────────────────────────────────────────────────────────────────┐
│                     DataHarvest Scraping Platform                    │
│                                                                      │
│  Scraping run       ┌──────────────────────────────────────────────┐ │
│  scheduled      ─► │  1. Load known facts:                        │ │
│                     │     retriever.bootstrap_context("amazon")    │ │
│                     │     → "Known selectors for amazon 2024-11:"  │ │
│                     │     → #productTitle (score: 0.94)           │ │
│                     │     → .a-price-whole (score: 0.88)          │ │
│                     │     → 198 more selectors...                 │ │
│                     │                                              │ │
│                     │  2. Pre-run: flag low-score selectors        │ │
│                     │     retriever.query(min_score=0.5)           │ │
│                     │     → 12 selectors below threshold          │ │
│                     │     → alert sent, skip stale rules          │ │
│                     │                                              │ │
│                     │  3. During run: record outcomes              │ │
│                     │     FactObservation(confirmed=True/False)    │ │
│                     │     → scores updated in real-time           │ │
│                     └──────────────────────────────────────────────┘ │
│                                                                      │
│  New deployment     ┌──────────────────────────────────────────────┐ │
│                  ─► │  export_bootstrap_pack("amazon")             │ │
│                     │  → full fact history seeded to new instance  │ │
│                     └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

## Implementation

```python
# dataharvest/scraper/selector_memory.py
import time
import json
from clickproof.fact import UIFact, FactObservation
from clickproof.store import FactStore
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer, FactScore
from clickproof.report import to_markdown, to_json

FACT_DB = "/data/clickproof/selector-facts.db"

store = FactStore(FACT_DB)
scorer = FactScorer()
retriever = FactRetriever(store, scorer)


def get_session_selectors(
    site: str,
    site_version: str,
    min_score: float = 0.6,
) -> str:
    """Load known CSS selectors as an agent context block.

    The returned string is injected into the scraping agent's system prompt,
    giving it a ranked list of selectors to try first — avoiding re-discovery.
    """
    return retriever.bootstrap_context(
        app_name=site,
        app_version=site_version,
    )


def record_selector_result(
    site: str,
    site_version: str,
    css_selector: str,
    data_field: str,
    confirmed: bool,
    run_id: str = "",
    context: str = "",
) -> UIFact:
    """Record whether a CSS selector successfully extracted data.

    Args:
        site: e.g., "amazon.com"
        site_version: Page layout version (from date or layout fingerprint)
        css_selector: The CSS selector string, e.g., "#productTitle"
        data_field: What data this selector extracts, e.g., "product_title"
        confirmed: True if selector returned non-empty data, False if it failed
        run_id: Scraping job ID for traceability
        context: Additional context (e.g., page URL pattern)
    """
    fact = UIFact(
        app_name=site,
        app_version=site_version,
        element=css_selector,
        action="extract",
        outcome=f"returns:{data_field}",
        context=context,
    )
    store.save_fact(fact)

    obs = FactObservation(
        fact_id=fact.id,
        observed_at=time.time(),
        confirmed=confirmed,
        agent_run_id=run_id,
    )
    store.save_observation(obs)
    return fact


def pre_run_impact_assessment(
    site: str,
    site_version: str,
    alert_threshold: float = 0.5,
) -> dict:
    """Assess which selectors are likely to fail before starting a scraping run.

    Returns a summary with:
    - healthy: selectors to use without re-validation
    - at_risk: selectors that should be re-validated first
    - unknown: selectors with no history (need full discovery)
    """
    all_pairs = retriever.query(site, site_version, min_score=0.0)

    healthy = [(f, s) for f, s in all_pairs if s.score >= alert_threshold]
    at_risk = [(f, s) for f, s in all_pairs if s.score < alert_threshold]

    return {
        "site": site,
        "version": site_version,
        "healthy_count": len(healthy),
        "at_risk_count": len(at_risk),
        "at_risk_selectors": [
            {
                "selector": f.element,
                "data_field": f.outcome.replace("returns:", ""),
                "score": s.score,
                "last_confirmed": s.last_seen_at,
                "confirmed": s.confirmed_count,
                "total": s.observation_count,
            }
            for f, s in at_risk
        ],
        "healthy_markdown": to_markdown(healthy),
    }


def export_bootstrap_pack(site: str, site_version: str) -> str:
    """Export all known selectors as a JSON bootstrap pack.

    Used to seed new scraper deployments (new regions, new worker nodes)
    with the full history of known-good selectors — avoiding cold-start.
    """
    all_pairs = retriever.query(site, site_version, min_score=0.0)
    return to_json(all_pairs)


# --- Example: pre-run check for Amazon after a layout change alert ---
def handle_layout_change_alert(site: str, new_version: str) -> None:
    """Called when a page layout fingerprint change is detected."""
    assessment = pre_run_impact_assessment(site, new_version, alert_threshold=0.5)

    print(f"\nLayout change detected: {site} → version {new_version}")
    print(f"  Healthy selectors   : {assessment['healthy_count']}")
    print(f"  At-risk selectors   : {assessment['at_risk_count']}")

    if assessment["at_risk_selectors"]:
        print("\n  Selectors requiring re-validation:")
        for s in assessment["at_risk_selectors"]:
            print(f"    [{s['score']:.3f}] {s['selector']} → {s['data_field']} "
                  f"({s['confirmed']}/{s['total']} confirmed)")
```

When the simulated Amazon redesign alert ran with this system, `handle_layout_change_alert()` returned exactly 12 at-risk selectors — the two that actually changed (product title, price) plus 10 that had lower historical confirmation rates (due to A/B testing variants). Engineers re-validated those 12. The 188 surviving selectors were back online in 2 hours rather than 2 weeks.

## Results

- **Selector re-validation time eliminated** — for sites with a full fact history, sessions skip the validation phase entirely; known-good selectors are injected at session start via `bootstrap_context()`
- **Amazon redesign impact: 200 broken rules → 12 requiring re-validation** (94% survival rate identified immediately, before re-testing began)
- **500 sites tracked** across DataHarvest's customer portfolio, with selector fact databases maintained per site and per layout version
- **New deployment onboarding**: new scraper worker nodes receive a `export_bootstrap_pack()` JSON blob during provisioning, achieving full knowledge from day one rather than re-learning over the first week of production traffic
- **Confidence scores correlate with actual reliability**: A/B testing on DataHarvest's own data showed that selectors with clickproof scores above 0.7 had a 96.3% success rate on the next run; selectors with scores below 0.4 had a 31% success rate — the score is a reliable pre-run predictor

## Key Takeaways

- Re-validation is pure waste when history is available. The `bootstrap_context()` call turns 30 minutes of per-session discovery into a 2-second context load. For a platform with 3 million monthly scrapes, this compounds into enormous efficiency gains.
- Staleness decay is the right model for CSS selectors. A selector confirmed 50 times last month but not confirmed in 2 weeks should have lower confidence than one confirmed yesterday. `exp(-0.1 × days_since_last_obs)` captures this naturally.
- Pre-run impact assessment beats reactive incident response. Knowing which selectors are at risk before a run starts lets you either skip those rules, re-validate them, or alert customers proactively — rather than discovering failures from empty datasets.
- Content-addressing eliminates duplicate fact records. The same CSS selector for the same element on the same site version always maps to the same `UIFact.id`, regardless of which agent instance or which run recorded it. Observations accumulate on the canonical record.
- `export_bootstrap_pack()` is how you solve the cold-start problem for distributed scraper fleets.

## Try It Yourself

```bash
# Install clickproof
pip install clickproof

# Simulate a scraper that learns and remembers CSS selectors
python -c "
import time
from clickproof.fact import UIFact, FactObservation
from clickproof.store import FactStore
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer

store = FactStore('/tmp/scraper-demo.db')
scorer = FactScorer()
retriever = FactRetriever(store, scorer)

# Record confirmed selectors from past runs
for selector, field, n_confirmed in [
    ('#productTitle', 'title', 15),
    ('.a-price-whole', 'price', 12),
    ('#acrCustomerReviewText', 'review_count', 8),
]:
    fact = UIFact('amazon.com', '2025-01', selector, 'extract', f'returns:{field}')
    store.save_fact(fact)
    for _ in range(n_confirmed):
        store.save_observation(FactObservation(fact.id, time.time(), confirmed=True))

# Query — sorted by confidence
context = retriever.bootstrap_context('amazon.com', '2025-01')
print(context)
"

# Use the CLI
clickproof query amazon.com --min-score 0.6
clickproof facts --db /tmp/scraper-demo.db
```
