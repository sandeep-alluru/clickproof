"""clickproof MCP server — Model Context Protocol tools for UI behavioral facts."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from clickproof.fact import FactObservation, UIFact
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer
from clickproof.store import FactStore

_DEFAULT_DB = os.environ.get("CLICKPROOF_DB", "clickproof.db")


def _get_store() -> FactStore:
    return FactStore(_DEFAULT_DB)


def add_ui_fact(
    app_name: str,
    app_version: str,
    element: str,
    action: str,
    outcome: str,
    context: str = "",
    confidence: float = 1.0,
) -> dict:
    """Add a UIFact to the clickproof store.

    Args:
        app_name: Application identifier, e.g. "salesforce".
        app_version: Version string, e.g. "2025.11".
        element: Semantic element, e.g. "export-csv-button".
        action: What to do: "click", "type", "navigate".
        outcome: What happens: "opens-download-dialog".
        context: Optional UI context.
        confidence: Initial confidence in [0.0, 1.0].

    Returns:
        The serialized UIFact dict.
    """
    fact = UIFact(
        app_name=app_name,
        app_version=app_version,
        element=element,
        action=action,
        outcome=outcome,
        context=context,
        confidence=confidence,
    )
    with _get_store() as store:
        store.add_fact(fact)
    return fact.to_dict()


def query_facts(
    app_name: str,
    app_version: str | None = None,
    min_score: float = 0.5,
) -> list[dict]:
    """Query UI behavioral facts for an application.

    Args:
        app_name: Application name to query.
        app_version: Optional version filter.
        min_score: Minimum confidence score threshold.

    Returns:
        List of dicts, each with "fact" and "score" keys.
    """
    with _get_store() as store:
        retriever = FactRetriever(store, FactScorer())
        pairs = retriever.query(app_name=app_name, app_version=app_version, min_score=min_score)
    return [{"fact": f.to_dict(), "score": s.to_dict()} for f, s in pairs]


def bootstrap_context(app_name: str, app_version: str = "unknown") -> str:
    """Return a text summary of known facts for agent context injection.

    Args:
        app_name: Application to summarize.
        app_version: Optional version to scope the summary.

    Returns:
        Markdown-formatted text suitable for prepending to a system prompt.
    """
    with _get_store() as store:
        retriever = FactRetriever(store, FactScorer())
        return retriever.bootstrap_context(app_name=app_name, app_version=app_version)


# ── New MCP tool implementations ──────────────────────────────────────────────


def clickproof_add_fact(
    app_name: str,
    app_version: str,
    element: str,
    action: str,
    outcome: str,
    context: str = "",
    confidence: float = 1.0,
) -> dict:
    """Store a UI behavioral fact. Returns ``{"id": fact.id}``."""
    fact = UIFact(
        app_name=app_name,
        app_version=app_version,
        element=element,
        action=action,
        outcome=outcome,
        context=context,
        confidence=confidence,
    )
    with _get_store() as store:
        store.add_fact(fact)
    return {"id": fact.id}


def clickproof_observe(
    fact_id: str,
    confirmed: bool,
    agent_run_id: str = "",
) -> dict:
    """Record a FactObservation. Returns ``{"id": obs.id}``."""
    obs = FactObservation(
        fact_id=fact_id,
        observed_at=time.time(),
        confirmed=confirmed,
        agent_run_id=agent_run_id,
    )
    with _get_store() as store:
        store.add_observation(obs)
    return {"id": obs.id}


def clickproof_query(
    app_name: str,
    app_version: str | None = None,
    min_score: float = 0.5,
) -> dict:
    """Query scored facts. Returns ``{"facts": [...], "count": N}``."""
    with _get_store() as store:
        retriever = FactRetriever(store, FactScorer())
        pairs = retriever.query(app_name=app_name, app_version=app_version, min_score=min_score)
    facts = [{"fact": f.to_dict(), "score": s.to_dict()} for f, s in pairs]
    return {"facts": facts, "count": len(facts)}


def clickproof_bootstrap(app_name: str, app_version: str = "unknown") -> dict:
    """Return bootstrap context string. Returns ``{"context": ...}``."""
    with _get_store() as store:
        retriever = FactRetriever(store, FactScorer())
        ctx = retriever.bootstrap_context(app_name=app_name, app_version=app_version)
    return {"context": ctx}


def run_server() -> None:
    """Run the clickproof MCP server (requires mcp package)."""
    try:
        from mcp.server import Server  # type: ignore[import-untyped]
        from mcp.server.stdio import stdio_server  # type: ignore[import-untyped]
        from mcp.types import TextContent, Tool  # type: ignore[import-untyped]
    except ImportError as exc:
        msg = (
            "The 'mcp' package is required to run the MCP server. "
            "Install with: pip install 'clickproof[mcp]'"
        )
        raise ImportError(msg) from exc

    server = Server("clickproof")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="add_ui_fact",
                description="Add a UI behavioral fact to the clickproof store.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string"},
                        "app_version": {"type": "string"},
                        "element": {"type": "string"},
                        "action": {"type": "string"},
                        "outcome": {"type": "string"},
                        "context": {"type": "string", "default": ""},
                        "confidence": {"type": "number", "default": 1.0},
                    },
                    "required": ["app_name", "app_version", "element", "action", "outcome"],
                },
            ),
            Tool(
                name="query_facts",
                description="Query UI behavioral facts for an application.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string"},
                        "app_version": {"type": "string"},
                        "min_score": {"type": "number", "default": 0.5},
                    },
                    "required": ["app_name"],
                },
            ),
            Tool(
                name="bootstrap_context",
                description="Get a text summary of known facts for agent context injection.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string"},
                        "app_version": {"type": "string", "default": "unknown"},
                    },
                    "required": ["app_name"],
                },
            ),
            Tool(
                name="clickproof_add_fact",
                description="Store a UI behavioral fact for an application.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string"},
                        "app_version": {"type": "string"},
                        "element": {"type": "string"},
                        "action": {"type": "string"},
                        "outcome": {"type": "string"},
                        "context": {"type": "string", "default": ""},
                        "confidence": {"type": "number", "default": 1.0},
                    },
                    "required": ["app_name", "app_version", "element", "action", "outcome"],
                },
            ),
            Tool(
                name="clickproof_observe",
                description="Record a FactObservation confirming or refuting a UIFact.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "fact_id": {"type": "string"},
                        "confirmed": {"type": "boolean"},
                        "agent_run_id": {"type": "string", "default": ""},
                    },
                    "required": ["fact_id", "confirmed"],
                },
            ),
            Tool(
                name="clickproof_query",
                description="Query scored UI behavioral facts for an application.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string"},
                        "app_version": {"type": "string"},
                        "min_score": {"type": "number", "default": 0.5},
                    },
                    "required": ["app_name"],
                },
            ),
            Tool(
                name="clickproof_bootstrap",
                description="Get a bootstrap context string for an application.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string"},
                        "app_version": {"type": "string", "default": "unknown"},
                    },
                    "required": ["app_name"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:

        if name == "add_ui_fact":
            result: Any = add_ui_fact(**arguments)
        elif name == "query_facts":
            result = query_facts(**arguments)
        elif name == "bootstrap_context":
            result = bootstrap_context(**arguments)
        elif name == "clickproof_add_fact":
            result = clickproof_add_fact(**arguments)
        elif name == "clickproof_observe":
            result = clickproof_observe(**arguments)
        elif name == "clickproof_query":
            result = clickproof_query(**arguments)
        elif name == "clickproof_bootstrap":
            result = clickproof_bootstrap(**arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    import asyncio

    asyncio.run(stdio_server(server))


if __name__ == "__main__":
    run_server()
