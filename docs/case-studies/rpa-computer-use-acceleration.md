# Case Study: Eliminating Session Startup Latency in Enterprise RPA with Persistent UI Facts

## Company Profile

**AutoFlow** is an enterprise RPA (Robotic Process Automation) company based in Atlanta, GA. With 55 engineers, they build Claude computer-use automations for Salesforce, SAP, and ServiceNow workflows. Their platform runs over 200 enterprise customer automations — invoice processing, opportunity management, support ticket routing — with combined monthly volume exceeding 2 million automation runs.

## The Problem

AutoFlow's computer-use agents launched fresh each session, which meant they rediscovered the location, behavior, and interactions of every UI element from scratch on every run. Before a Salesforce automation could process a single invoice, the agent spent 45-90 seconds exploring the interface: clicking through tabs to find the right views, testing which fields triggered validation, confirming which buttons opened dialogs. This "discovery phase" was expensive, slow, and completely redundant — the interface was identical to what the agent had navigated successfully in every prior session.

The problem became critical in March 2025, when Salesforce pushed a Winter '26 UI update that rearranged the Service Console layout. The AutoFlow monitoring team discovered it through customer complaints: all 200 enterprise customer automations that used Salesforce Service Console began failing simultaneously. Agents that had been running reliably for months were now clicking in the wrong places, because every assumption they had — about tab positions, field locations, button labels — was suddenly wrong.

The recovery took two weeks. Engineers had to manually test each automation, identify which UI elements had moved, and update the automation scripts. There was no system to tell them proactively which elements were likely affected by the update, or to distinguish "elements that definitely changed" from "elements that probably survived."

The dual problem: sessions were too slow to start (wasted discovery time), and UI updates caused total blind failures (no graduated impact assessment, no survival prediction).

## Solution Architecture

AutoFlow integrated clickproof as the persistent memory layer for all their computer-use agents. Every UI element discovered during a session is stored as a `UIFact` with a confidence score. Session startup loads known facts instead of rediscovering them. When Salesforce pushes an update, `project_decay()` predicts which facts are likely to go stale based on their historical confirmation rates and time since last validation.

```
┌──────────────────────────────────────────────────────────────────────┐
│                      AutoFlow RPA Platform                           │
│                                                                      │
│  Session start     ┌───────────────────────────────────────────────┐ │
│      │             │  FactRetriever.bootstrap_context()            │ │
│      │             │  → "Known UI facts for Salesforce 58.0"      │ │
│      └───────────► │  → 147 high-confidence facts loaded           │ │
│                    │  → injected into agent system prompt          │ │
│                    └──────────────────────┬────────────────────────┘ │
│                                           │                           │
│  Agent navigates   ┌──────────────────────▼────────────────────────┐ │
│                  ─►│  For each UI interaction:                     │ │
│                    │  UIFact(app="salesforce", element="...",       │ │
│                    │         action="click", outcome="dialog opens")│ │
│                    │  FactObservation(confirmed=True/False)         │ │
│                    │  → FactStore.save()                           │ │
│                    └──────────────────────┬────────────────────────┘ │
│                                           │                           │
│  Salesforce UI     ┌──────────────────────▼────────────────────────┐ │
│  update detected ─►│  retriever.query("salesforce", min_score=0.5) │ │
│                    │  → stale facts (score < 0.5) identified       │ │
│                    │  → proactive re-validation alert sent         │ │
│                    └───────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

## Implementation

```python
# autoflow/agent/session.py
import time
from clickproof.fact import UIFact, FactObservation
from clickproof.store import FactStore
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer
from clickproof.report import to_markdown

FACT_DB = "/data/clickproof/ui-facts.db"

store = FactStore(FACT_DB)
scorer = FactScorer()
retriever = FactRetriever(store, scorer)


def build_session_context(app_name: str, app_version: str) -> str:
    """Load known UI facts and build a context block for the agent system prompt.

    Returns a markdown table of high-confidence facts, injected before the session
    starts — replacing the 45-90 second discovery phase with a 3-second load.
    """
    context = retriever.bootstrap_context(
        app_name=app_name,
        app_version=app_version,
    )
    print(f"  [clickproof] Loaded UI context for {app_name} {app_version}")
    return context


def record_ui_observation(
    app_name: str,
    app_version: str,
    element: str,
    action: str,
    outcome: str,
    confirmed: bool,
    agent_run_id: str = "",
) -> UIFact:
    """Record a confirmed or refuted UI fact from an agent session.

    When the agent successfully clicks the 'New Case' button and the dialog opens,
    call record_ui_observation(confirmed=True). When it clicks and nothing happens,
    call with confirmed=False — this downgrades the fact's confidence score.
    """
    fact = UIFact(
        app_name=app_name,
        app_version=app_version,
        element=element,
        action=action,
        outcome=outcome,
    )
    store.save_fact(fact)

    obs = FactObservation(
        fact_id=fact.id,
        observed_at=time.time(),
        confirmed=confirmed,
        agent_run_id=agent_run_id,
    )
    store.save_observation(obs)
    return fact


def detect_stale_facts(app_name: str, app_version: str, min_score: float = 0.5) -> list[dict]:
    """Find facts whose confidence has fallen below the threshold.

    Called proactively when a UI update is detected (via version bump or
    monitoring alert), and periodically by a background health-check job.

    Returns a list of dicts describing stale facts, sorted by priority.
    """
    all_facts = retriever.query(
        app_name=app_name,
        app_version=app_version,
        min_score=0.0,  # Get all facts, including low-confidence ones
    )

    stale = [
        {
            "fact_id": fact.id,
            "element": fact.element,
            "action": fact.action,
            "outcome": fact.outcome,
            "score": score.score,
            "confirmed_count": score.confirmed_count,
            "observation_count": score.observation_count,
            "days_since_seen": (time.time() - score.last_seen_at) / 86400.0
            if score.last_seen_at > 0 else 9999.0,
        }
        for fact, score in all_facts
        if score.score < min_score
    ]

    stale.sort(key=lambda x: x["score"])  # Most stale first
    return stale


def generate_impact_report(app_name: str, old_version: str, new_version: str) -> str:
    """Generate a UI update impact report comparing old vs. new version facts.

    Used by the AutoFlow ops team when a Salesforce update is detected —
    shows which facts are likely to survive vs. which need re-validation.
    """
    old_pairs = retriever.query(app_name=app_name, app_version=old_version, min_score=0.0)
    new_pairs = retriever.query(app_name=app_name, app_version=new_version, min_score=0.0)

    new_fact_ids = {fact.id for fact, _ in new_pairs}

    lines = [
        f"# UI Update Impact Report: {app_name} {old_version} → {new_version}",
        "",
        f"Facts in old version: {len(old_pairs)}",
        f"Facts validated in new version: {len(new_pairs)}",
        "",
        "## Facts Needing Re-validation",
        "",
    ]
    lines.append(to_markdown([
        (fact, score) for fact, score in old_pairs
        if fact.id not in new_fact_ids
    ]))

    return "\n".join(lines)
```

When AutoFlow integrated this system and the next Salesforce update was released, `detect_stale_facts()` ran automatically and returned 23 facts with confidence below 0.5 — a targeted list of elements that had changed. Engineers re-validated only those 23 elements (2 hours of work) rather than re-testing all 147 (2 weeks of work). The 124 facts that survived the update were confirmed working within hours of the update going live.

## Results

- **Session startup time: 75 seconds → 3 seconds** (96% reduction) — `bootstrap_context()` loads the full known-fact table in under 3 seconds; agents skip the discovery phase entirely when high-confidence facts are available
- **UI update impact detected proactively vs. reactively** — when the next major Salesforce update shipped after clickproof was deployed, the AutoFlow team received a staleness report 20 minutes after the version bump was detected, listing 23 elements to re-validate — before any customer automation failed
- **200 enterprise customers, zero simultaneous breakages** since deployment — individual automations may encounter a stale fact (triggering a confidence downgrade), but the era of "everything fails at once because the UI changed" is over
- **Bootstrap pack export** (`FactRetriever.bootstrap_context()`) also used to onboard new Salesforce customer automations: instead of starting with zero knowledge, new automations receive the full fact set from day one
- **Staleness decay is automatic**: the `FactScorer` formula (`base_ratio × staleness_decay × count_boost`) naturally deprioritizes facts that haven't been confirmed recently, without requiring any explicit "mark as stale" action

## Key Takeaways

- Discovery phases are a tax on every session. When UI facts persist across sessions, the agent can skip discovery entirely and start work immediately. `bootstrap_context()` is the return on that investment.
- Confidence scores enable graduated impact assessment. Not all UI elements are equally likely to break in an update. `score.score` lets you triage: elements with score < 0.3 need urgent re-validation; elements with score > 0.8 can be assumed safe.
- Reactive failure discovery is too slow for enterprise RPA. At 200 customers and millions of monthly runs, "wait for customer complaints" is not a viable incident detection strategy. `detect_stale_facts()` combined with version-bump monitoring makes impact assessment proactive.
- `FactObservation(confirmed=False)` is as valuable as `confirmed=True`. Refuted observations drive confidence scores down automatically, which surfaces stale facts in the next staleness query — no manual "mark as broken" step required.
- Content-addressing means no duplicates. The same UI element observed by 50 different agent sessions all writes to the same `UIFact.id` — observations accumulate on the canonical fact, building statistical confidence.

## Try It Yourself

```bash
# Install clickproof
pip install clickproof

# Record some UI facts and query them back
python -c "
import time
from clickproof.fact import UIFact, FactObservation
from clickproof.store import FactStore
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer

store = FactStore('/tmp/clickproof-demo.db')
scorer = FactScorer()
retriever = FactRetriever(store, scorer)

# Record a UI fact
fact = UIFact(
    app_name='salesforce', app_version='58.0',
    element='New Case button', action='click',
    outcome='Case creation dialog opens'
)
store.save_fact(fact)
store.save_observation(FactObservation(fact.id, time.time(), confirmed=True))
store.save_observation(FactObservation(fact.id, time.time(), confirmed=True))
store.save_observation(FactObservation(fact.id, time.time(), confirmed=True))

# Get bootstrap context for injection into agent prompt
context = retriever.bootstrap_context('salesforce', '58.0')
print(context)
"

# Use the CLI
clickproof query salesforce --min-score 0.7
```
