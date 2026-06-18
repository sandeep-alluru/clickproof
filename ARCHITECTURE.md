# guiproof Architecture

## Overview

guiproof is a pure Python library for storing, scoring, and retrieving UI behavioral facts. It provides a persistent memory layer for computer-use agents, allowing them to accumulate and leverage knowledge about GUI applications across sessions.

## Layer Diagram

```
┌─────────────────────────────────────────────────────┐
│                  Agent / User                        │
└────────┬───────────────────────┬───────────────────-┘
         │                       │
    ┌────▼────┐            ┌─────▼─────┐
    │   CLI   │            │  FastAPI  │
    │ (click) │            │  (api.py) │
    └────┬────┘            └─────┬─────┘
         │                       │
    ┌────▼───────────────────────▼─────┐
    │           FactRetriever           │
    │  query() · bootstrap_context()   │
    └────┬──────────────────────┬──────┘
         │                      │
    ┌────▼────┐           ┌─────▼──────┐
    │FactStore│           │FactScorer  │
    │(SQLite) │           │score()     │
    └────┬────┘           │batch_score │
         │                └────────────┘
    ┌────▼──────────────────────┐
    │  UIFact · FactObservation  │
    │  (content-addressed IDs)   │
    └────────────────────────────┘
```

## Data Model

### UIFact

The atom of guiproof. A UIFact records what happens when an agent performs a specific action on a specific UI element in a specific application version.

- **ID** = SHA-256[:16] of `app_name|app_version|element|action`
- The same element/action pair in the same app version always produces the same ID
- The `outcome` field is **not** part of the ID — it can evolve

```python
@dataclass
class UIFact:
    app_name: str        # "salesforce"
    app_version: str     # "2025.11"
    element: str         # "export-csv-button"
    action: str          # "click"
    outcome: str         # "opens-download-dialog"
    context: str         # "reports-page" (optional)
    confidence: float    # initial confidence [0, 1]
    recorded_at: float   # unix timestamp
    id: str              # computed
```

### FactObservation

A signal from a real agent run confirming or refuting a UIFact.

- **ID** = SHA-256[:16] of `fact_id|observed_at|confirmed`
- Observations are append-only; the FactScorer aggregates them

### FactScore

Computed from observation history by FactScorer. Not persisted; computed on-the-fly.

## Scoring Algorithm

```
score = base_ratio × staleness_decay × count_boost

where:
    base_ratio     = confirmed_count / total_count
    staleness_decay = exp(-0.1 × staleness_days)
    count_boost    = min(1.0, log(1 + count) / log(11))
```

- **base_ratio**: What fraction of observations confirmed the fact?
- **staleness_decay**: Exponential decay — a fact unobserved for 10 days has ~37% of its score.
- **count_boost**: A logarithmic scale — 10 observations give full confidence weight; fewer give less.

When there are no observations, the fact's initial `confidence` field is used as the base score (with staleness decay applied from `recorded_at`).

## Storage

All data lives in a single SQLite database file.

```sql
CREATE TABLE ui_facts (
    id          TEXT PRIMARY KEY,  -- SHA-256[:16]
    app_name    TEXT NOT NULL,
    app_version TEXT NOT NULL,
    element     TEXT NOT NULL,
    action      TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    context     TEXT NOT NULL DEFAULT '',
    confidence  REAL NOT NULL DEFAULT 1.0,
    recorded_at REAL NOT NULL,
    extra       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE fact_observations (
    id           TEXT PRIMARY KEY,
    fact_id      TEXT NOT NULL,
    observed_at  REAL NOT NULL,
    confirmed    INTEGER NOT NULL,
    agent_run_id TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (fact_id) REFERENCES ui_facts(id)
);
```

## Query Flow

1. `FactRetriever.query(app_name, app_version, element, min_score)` calls `FactStore.list_facts()` with the given filters.
2. For each fact, it calls `FactStore.get_observations(fact_id)` and then `FactScorer.score(fact, observations)`.
3. Facts with score below `min_score` are excluded.
4. Results are sorted by score descending and returned as `list[tuple[UIFact, FactScore]]`.

## MCP Integration

The MCP server (`guiproof/mcp_server.py`) exposes three tools:

| Tool | Description |
|------|-------------|
| `add_ui_fact` | Add a UIFact to the store |
| `query_facts` | Query facts for an app |
| `bootstrap_context` | Get a text summary for agent injection |

The MCP server reads the database path from the `GUIPROOF_DB` environment variable.

## Extension Points

- **Custom scorer**: Pass a custom `FactScorer` subclass to `FactRetriever`.
- **Bulk import**: Use `FactStore.add_fact()` in a loop — duplicates are silently ignored.
- **Versioned rollout**: Record facts for each app version independently, then query with `app_version` filter.
