"""FastAPI REST wrapper for clickproof.

Start:   uvicorn clickproof.api:app --reload
Install: pip install "clickproof[api]"
Docs:    http://localhost:8000/docs
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from fastapi import FastAPI, Query
    from pydantic import BaseModel
except ImportError as exc:
    raise ImportError(
        "API server requires: pip install 'clickproof[api]'"
    ) from exc

from clickproof import __version__
from clickproof.fact import FactObservation, UIFact
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer
from clickproof.store import FactStore

_DB_PATH = os.environ.get("CLICKPROOF_DB", "clickproof.db")

app = FastAPI(
    title="clickproof API",
    description="Persistent GUI behavioral facts for computer-use agents",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    version: str


class UIFactRequest(BaseModel):
    app_name: str
    app_version: str
    element: str
    action: str
    outcome: str
    context: str = ""
    confidence: float = 1.0


class FactObservationRequest(BaseModel):
    fact_id: str
    observed_at: float
    confirmed: bool
    agent_run_id: str = ""


class FactScoreResponse(BaseModel):
    score: float
    confirmed_count: int
    observation_count: int
    last_seen_at: float


class FactWithScore(BaseModel):
    fact: dict
    score: FactScoreResponse


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> dict:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@app.post("/fact", status_code=201)
async def add_fact(body: UIFactRequest) -> dict:
    """Store (upsert) a UIFact."""
    fact = UIFact(
        app_name=body.app_name,
        app_version=body.app_version,
        element=body.element,
        action=body.action,
        outcome=body.outcome,
        context=body.context,
        confidence=body.confidence,
    )
    with FactStore(_DB_PATH) as store:
        store.add_fact(fact)
    return {"id": fact.id}


@app.post("/observe", status_code=201)
async def add_observation(body: FactObservationRequest) -> dict:
    """Record a FactObservation."""
    obs = FactObservation(
        fact_id=body.fact_id,
        observed_at=body.observed_at,
        confirmed=body.confirmed,
        agent_run_id=body.agent_run_id,
    )
    with FactStore(_DB_PATH) as store:
        store.add_observation(obs)
    return {"id": obs.id}


@app.get("/query")
async def query_facts(
    app_name: str = Query(...),
    app_version: Optional[str] = Query(None),
    min_score: float = Query(0.5),
) -> list[FactWithScore]:
    """Return scored facts for an app, filtered by min_score."""
    scorer = FactScorer()
    with FactStore(_DB_PATH) as store:
        retriever = FactRetriever(store, scorer)
        pairs = retriever.query(app_name=app_name, app_version=app_version, min_score=min_score)

    return [
        FactWithScore(
            fact=fact.to_dict(),
            score=FactScoreResponse(
                score=score.score,
                confirmed_count=score.confirmed_count,
                observation_count=score.observation_count,
                last_seen_at=score.last_seen_at,
            ),
        )
        for fact, score in pairs
    ]


@app.get("/facts")
async def list_facts(app_name: Optional[str] = Query(None)) -> list[dict]:
    """List all stored facts, optionally filtered by app_name."""
    with FactStore(_DB_PATH) as store:
        facts = store.list_facts(app_name=app_name)
    return [f.to_dict() for f in facts]


@app.get("/bootstrap")
async def bootstrap(
    app_name: str = Query(...),
    app_version: Optional[str] = Query(None),
) -> dict:
    """Return bootstrap context string for agent system prompt injection."""
    scorer = FactScorer()
    with FactStore(_DB_PATH) as store:
        retriever = FactRetriever(store, scorer)
        ctx = retriever.bootstrap_context(app_name=app_name, app_version=app_version)
    return {"context": ctx}
