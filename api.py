"""clickproof FastAPI server — REST endpoints for UI behavioral facts."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

import clickproof
from clickproof.fact import FactObservation, UIFact
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScore, FactScorer
from clickproof.store import FactStore

app = FastAPI(
    title="clickproof API",
    description="Persistent GUI behavioral facts for computer-use agents.",
    version=clickproof.__version__,
)

_DEFAULT_DB = "clickproof.db"


def _store(db: str = _DEFAULT_DB) -> FactStore:
    return FactStore(db)


# ── Models ────────────────────────────────────────────────────────────────────


class FactIn(BaseModel):
    app_name: str
    app_version: str
    element: str
    action: str
    outcome: str
    context: str = ""
    confidence: float = 1.0
    db: str = _DEFAULT_DB


class ObservationIn(BaseModel):
    fact_id: str
    confirmed: bool
    agent_run_id: str = ""
    db: str = _DEFAULT_DB


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict[str, str]:
    """Health check — returns status and version."""
    return {"status": "ok", "version": clickproof.__version__}


@app.post("/fact")
def add_fact(body: FactIn) -> dict:
    """Add a UIFact to the store."""
    fact = UIFact(
        app_name=body.app_name,
        app_version=body.app_version,
        element=body.element,
        action=body.action,
        outcome=body.outcome,
        context=body.context,
        confidence=body.confidence,
    )
    with _store(body.db) as store:
        store.add_fact(fact)
    return fact.to_dict()


@app.post("/observe")
def add_observation(body: ObservationIn) -> dict:
    """Record a FactObservation confirming or refuting a UIFact."""
    obs = FactObservation(
        fact_id=body.fact_id,
        observed_at=time.time(),
        confirmed=body.confirmed,
        agent_run_id=body.agent_run_id,
    )
    with _store(body.db) as store:
        fact = store.get_fact(body.fact_id)
        if fact is None:
            raise HTTPException(status_code=404, detail=f"Fact {body.fact_id!r} not found.")
        store.add_observation(obs)
    return obs.to_dict()


@app.get("/query")
def query_facts(
    app_name: str = Query(..., description="Application name to query."),
    app_version: str | None = Query(None, description="Optional version filter."),
    min_score: float = Query(0.5, description="Minimum score threshold."),
    db: str = Query(_DEFAULT_DB, description="Database path."),
) -> list[dict]:
    """Retrieve scored facts for an application."""
    with _store(db) as store:
        retriever = FactRetriever(store, FactScorer())
        pairs = retriever.query(app_name=app_name, app_version=app_version, min_score=min_score)
    return [{"fact": f.to_dict(), "score": s.to_dict()} for f, s in pairs]


@app.get("/facts")
def list_facts(
    app_name: str | None = Query(None, description="Optional app filter."),
    db: str = Query(_DEFAULT_DB, description="Database path."),
) -> list[dict]:
    """List all stored facts."""
    with _store(db) as store:
        facts = store.list_facts(app_name=app_name)
    return [f.to_dict() for f in facts]


@app.get("/bootstrap")
def bootstrap(
    app_name: str = Query(..., description="Application name to bootstrap."),
    app_version: str = Query("unknown", description="App version."),
    db: str = Query(_DEFAULT_DB, description="Database path."),
) -> dict:
    """Return a text context string for agent system prompt injection."""
    with _store(db) as store:
        retriever = FactRetriever(store, FactScorer())
        context = retriever.bootstrap_context(app_name=app_name, app_version=app_version)
    return {"app_name": app_name, "app_version": app_version, "context": context}
