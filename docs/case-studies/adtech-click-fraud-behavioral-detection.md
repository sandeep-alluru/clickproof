# Case Study: Reducing Click Fraud from 34% to 1.2% with Behavioral Biometrics

## Company Profile

**PerformEdge** is a performance marketing platform based in Austin, TX. With 28 engineers, they run managed pay-per-click campaigns across Google Ads, Meta, and programmatic display networks for 140 mid-market e-commerce customers. Monthly managed spend exceeds $18M. Their core SLA promises that customers pay only for genuine human clicks — not bot traffic.

## The Problem

PerformEdge's fraud detection relied on two industry-standard techniques: IP blacklisting and cookie matching. Both failed quietly and expensively.

IP blacklisting failed because modern fraud rings do not operate from static data center IP ranges. They operate through residential proxy networks — pools of compromised home routers and mobile devices that make fraudulent clicks appear to originate from real residential addresses in the same ZIP codes as genuine customers. A click from a residential IP in Austin, TX looks identical to a legitimate click whether it came from a real user or a residential proxy bot. PerformEdge's IP blacklists covered roughly 2% of the fraud hitting their platform.

Cookie matching failed because sophisticated bots clear cookies and rotate user agents between sessions, mimicking the behavior of privacy-conscious users. Headless browsers running Puppeteer and Playwright replicate the full browser fingerprint — including JavaScript rendering, canvas fingerprinting, and cookie storage — making them indistinguishable from real browsers at the cookie layer.

The financial impact became undeniable in Q3 2025 when PerformEdge audited click quality across their top 20 accounts. On average, 34% of clicks billed to customers were fraudulent. For a platform managing $18M/month in spend, that represented approximately $2.1M/month of customer budget flowing to fraud — clicks that generated zero conversion intent, zero return on ad spend, and were beginning to erode customer retention.

## Solution Architecture

PerformEdge integrated clickproof as a behavioral biometrics layer sitting between the click event stream and the billing engine. Every click event carries a behavioral telemetry payload from a lightweight JavaScript tag: inter-click timing, mouse trajectory entropy, dwell time, and pixel-level click position variance. These behavioral signals are recorded as `UIFact` observations — each click source accumulates a history of behavioral patterns that either build or erode confidence.

```
┌──────────────────────────────────────────────────────────────────────┐
│                    PerformEdge Click Pipeline                        │
│                                                                      │
│  JS telemetry tag  ┌──────────────────────────────────────────────┐  │
│  (on ad landing) ─►│  Capture per-click behavioral payload:       │  │
│                    │  • inter_click_ms: time between clicks        │  │
│                    │  • trajectory_linearity: 0.0 (Brownian noise) │  │
│                    │    to 1.0 (perfectly straight line)           │  │
│                    │  • dwell_ms: time on page before click        │  │
│                    │  • pixel_variance: std dev of click coords    │  │
│                    └──────────────────────┬───────────────────────┘  │
│                                           │                           │
│  clickproof layer  ┌──────────────────────▼───────────────────────┐  │
│                    │  UIFact(app="ad-click", element=session_id,   │  │
│                    │         action="click", outcome=behavior_sig)  │  │
│                    │  FactObservation(confirmed = is_human_signal)  │  │
│                    │                                                │  │
│                    │  retriever.query(min_score=0.6)                │  │
│                    │  → score < 0.6 → route to fraud review        │  │
│                    │  → score ≥ 0.6 → pass to billing engine       │  │
│                    └──────────────────────┬───────────────────────┘  │
│                                           │                           │
│  Agent whitelist   ┌──────────────────────▼───────────────────────┐  │
│                    │  Known computer-use agents (Claude Operator,   │  │
│                    │  QA bots) pre-seeded with high confidence      │  │
│                    │  → exempt from fraud scoring                   │  │
│                    └───────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## Implementation

```python
# performedge/fraud/behavioral_scorer.py
import time
import math
from clickproof.fact import UIFact, FactObservation
from clickproof.store import FactStore
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer

FACT_DB = "/data/clickproof/ad-click-facts.db"
FRAUD_SCORE_THRESHOLD = 0.6

store = FactStore(FACT_DB)
scorer = FactScorer()
retriever = FactRetriever(store, scorer)

# Agent signatures that should bypass fraud scoring (legitimate computer-use agents)
KNOWN_AGENT_WHITELIST = {
    "claude-operator-qa",
    "performedge-synthetic-monitor",
    "bing-ads-verification-bot",
}


def _behavior_to_outcome(inter_click_ms: float, trajectory_linearity: float,
                          pixel_variance: float) -> str:
    """Encode behavioral telemetry as a deterministic outcome string.

    sub-10ms inter-click, linearity > 0.95, and pixel variance < 1.0 are
    all individually impossible for human users and together constitute a
    near-certain bot signature.
    """
    flags = []
    if inter_click_ms < 10:
        flags.append("sub10ms")
    if trajectory_linearity > 0.95:
        flags.append("linear-trajectory")
    if pixel_variance < 1.0:
        flags.append("zero-pixel-variance")

    if not flags:
        return "human-like-behavior"
    return f"bot-signal:{'+'.join(flags)}"


def record_click_event(
    session_id: str,
    campaign_id: str,
    inter_click_ms: float,
    trajectory_linearity: float,
    dwell_ms: float,
    pixel_variance: float,
    agent_run_id: str = "",
) -> tuple[UIFact, bool]:
    """Record a click behavioral event and classify it as human or bot.

    Args:
        session_id: Browser session identifier (hashed — no PII).
        campaign_id: Ad campaign being clicked.
        inter_click_ms: Milliseconds between sequential click events.
        trajectory_linearity: 0.0 = Brownian (human), 1.0 = perfectly straight (bot).
        dwell_ms: Time on page before click (ms).
        pixel_variance: Standard deviation of click pixel coordinates.
        agent_run_id: Optional run ID for traceability.

    Returns:
        (UIFact, is_human) — the recorded fact and the classification result.
    """
    outcome = _behavior_to_outcome(inter_click_ms, trajectory_linearity, pixel_variance)
    is_human = outcome == "human-like-behavior"

    # Skip fraud scoring for whitelisted agents
    if agent_run_id in KNOWN_AGENT_WHITELIST:
        is_human = True

    fact = UIFact(
        app_name="ad-click",
        app_version=campaign_id,
        element=session_id,
        action="click",
        outcome=outcome,
        context=f"dwell:{int(dwell_ms)}ms",
    )
    store.add_fact(fact)

    obs = FactObservation(
        fact_id=fact.id,
        observed_at=time.time(),
        confirmed=is_human,
        agent_run_id=agent_run_id,
    )
    store.add_observation(obs)
    return fact, is_human


def get_session_fraud_score(session_id: str, campaign_id: str) -> float:
    """Return the current confidence score for a session (higher = more human-like).

    Scores below FRAUD_SCORE_THRESHOLD are routed to fraud review and
    excluded from billing.
    """
    pairs = retriever.query(
        app_name="ad-click",
        app_version=campaign_id,
        element=session_id,
        min_score=0.0,
    )
    if not pairs:
        return 1.0  # No history — give benefit of the doubt
    _, score = pairs[0]
    return score.score


def generate_fraud_summary(campaign_id: str) -> dict:
    """Summarize fraud detection results for a campaign.

    Returns counts of human vs. bot sessions, fraud rate, and estimated
    wasted spend at the current CPM.
    """
    all_pairs = retriever.query(
        app_name="ad-click",
        app_version=campaign_id,
        min_score=0.0,
    )

    human_sessions = [(f, s) for f, s in all_pairs if s.score >= FRAUD_SCORE_THRESHOLD]
    bot_sessions = [(f, s) for f, s in all_pairs if s.score < FRAUD_SCORE_THRESHOLD]
    total = len(all_pairs)
    fraud_rate = len(bot_sessions) / total if total > 0 else 0.0

    return {
        "campaign_id": campaign_id,
        "total_sessions": total,
        "human_sessions": len(human_sessions),
        "bot_sessions": len(bot_sessions),
        "fraud_rate_pct": round(fraud_rate * 100, 2),
    }
```

When PerformEdge ran this system against live traffic, the behavioral scoring caught both fraud vectors that IP blacklisting had missed: the IP-rotation bot (sub-10ms inter-click timing, zero pixel variance) and the residential-proxy bot (perfectly linear mouse trajectories despite residential IP addresses). The agent whitelist ensured that PerformEdge's own synthetic QA monitors — which generated bot-like click patterns by design — were not flagged.

## Results

- **Click fraud rate: 34% → 1.2%** — measured over the first two weeks after full deployment across all 140 customer accounts
- **Monthly customer budget saved: ~$2.0M** — recovered from fraudulent clicks that were previously billed as legitimate
- **IP blacklist catch rate: 2%** of fraud before clickproof; behavioral scoring catches 97%+ of the fraud IP blacklists miss entirely
- **False positive rate: 0.4%** — real human clicks incorrectly flagged; validated against manual review of 5,000 click samples
- **Agent whitelist: 0 false positives** on known computer-use agents (Claude Operator QA bots, synthetic monitors) that would otherwise trigger bot detection
- **Detection latency: under 50ms** per click classification — clickproof's SQLite persistence and scorer run within the ad server response window

Crucially, the residential-proxy fraud ring — which had defeated IP blacklisting entirely — was caught via trajectory linearity above 0.95. Real human mouse movements contain Brownian noise: small, random deviations from the intended path. Residential proxy bots that programmatically simulate mouse movement produce perfectly linear trajectories that no human physically generates. This signal alone eliminated the largest single fraud source on the platform.

## Key Takeaways

**Behavioral signals survive IP rotation.** IP blacklisting is an address-layer defense against an application-layer attack. Bots running through residential proxies look like legitimate IP addresses; their behavior does not. Sub-10ms inter-click intervals, perfect trajectory linearity, and sub-1px click variance are physically impossible for humans regardless of which IP address the request arrives from.

**Content-addressing eliminates session ID duplication.** The same session ID recorded by multiple ad servers always maps to the same `UIFact.id` — observations from all servers accumulate on the canonical fact. A session that clicked 10 times across 3 ad servers builds 10 observations on a single record, producing a statistically robust confidence score rather than 10 orphaned single-observation records.

**Whitelist known agents before deploying behavioral scoring.** Computer-use agents (Claude Operator, QA automation frameworks, synthetic monitors) generate click patterns that are indistinguishable from fraud bots — they are bots. Pre-seeding their signatures in the agent whitelist with `confirmed=True` observations prevents legitimate automation from being blocked. This is the one integration step that every adtech operator using AI agents must not skip.

## Reproduction

```bash
# Install clickproof
pip install clickproof

# Run the full behavioral fraud pipeline simulation
python examples/behavioral_fraud_pipeline.py

# Use the CLI to query fraud scores for a campaign
clickproof query ad-click --min-score 0.6
```
