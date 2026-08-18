"""clickproof MCP server - Model Context Protocol tools for UI behavioral facts."""

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
) -> dict[str, Any]:
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
) -> list[dict[str, Any]]:
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
) -> dict[str, Any]:
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
) -> dict[str, Any]:
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
) -> dict[str, Any]:
    """Query scored facts. Returns ``{"facts": [...], "count": N}``."""
    with _get_store() as store:
        retriever = FactRetriever(store, FactScorer())
        pairs = retriever.query(app_name=app_name, app_version=app_version, min_score=min_score)
    facts = [{"fact": f.to_dict(), "score": s.to_dict()} for f, s in pairs]
    return {"facts": facts, "count": len(facts)}


def clickproof_bootstrap(app_name: str, app_version: str = "unknown") -> dict[str, Any]:
    """Return bootstrap context string. Returns ``{"context": ...}``."""
    with _get_store() as store:
        retriever = FactRetriever(store, FactScorer())
        ctx = retriever.bootstrap_context(app_name=app_name, app_version=app_version)
    return {"context": ctx}


def run_server() -> None:
    """Run the clickproof MCP server (requires mcp package)."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import TextContent, Tool
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
                name="clickproof_add_fact",
                description=(
                    "Store a durable UI behavioral fact for a computer-use agent. "
                    "Use when the agent learns that a specific UI element performs a known "
                    "action/outcome (e.g. export-csv-button -> opens-download-dialog). "
                    "Do not use for one-off DOM snapshots; use clickproof_observe to confirm "
                    "or refute an existing fact after a later run."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "Application identifier, e.g. 'salesforce'.",
                        },
                        "app_version": {
                            "type": "string",
                            "description": "App version string that scopes the fact, e.g. '2025.11'.",
                        },
                        "element": {
                            "type": "string",
                            "description": "Semantic UI element id, e.g. 'export-csv-button'.",
                        },
                        "action": {
                            "type": "string",
                            "description": "Agent action verb: click, type, or navigate.",
                        },
                        "outcome": {
                            "type": "string",
                            "description": "Observed result, e.g. 'opens-download-dialog'.",
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional surrounding UI context that disambiguates the element.",
                            "default": "",
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Initial confidence in [0.0, 1.0]. Default 1.0.",
                            "default": 1.0,
                        },
                    },
                    "required": ["app_name", "app_version", "element", "action", "outcome"],
                },
            ),
            Tool(
                name="clickproof_observe",
                description=(
                    "Record whether a previously stored UIFact still holds after an agent run. "
                    "Use after attempting the action described by an existing fact. "
                    "Pass confirmed=true when the outcome matched; false when it failed or changed. "
                    "Do not use this to create new facts — call clickproof_add_fact first."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "fact_id": {
                            "type": "string",
                            "description": "ID returned by clickproof_add_fact.",
                        },
                        "confirmed": {
                            "type": "boolean",
                            "description": "True if the fact's outcome still held; false if refuted.",
                        },
                        "agent_run_id": {
                            "type": "string",
                            "description": "Optional id of the agent run that produced this observation.",
                            "default": "",
                        },
                    },
                    "required": ["fact_id", "confirmed"],
                },
            ),
            Tool(
                name="clickproof_query",
                description=(
                    "Return scored UI behavioral facts for an application, filtered by min_score. "
                    "Use before acting in a UI to avoid ghost clicks on elements whose behavior "
                    "is unknown or low-confidence. Prefer clickproof_bootstrap when you need a "
                    "ready-to-inject text summary instead of structured JSON."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "Application name to query.",
                        },
                        "app_version": {
                            "type": "string",
                            "description": "Optional version filter; omit to search all versions.",
                        },
                        "min_score": {
                            "type": "number",
                            "description": "Minimum confidence score threshold in [0.0, 1.0]. Default 0.5.",
                            "default": 0.5,
                        },
                    },
                    "required": ["app_name"],
                },
            ),
            Tool(
                name="clickproof_bootstrap",
                description=(
                    "Build a markdown summary of known UI facts for an app, suitable for "
                    "prepending to an agent system prompt. Use at session start. "
                    "Use clickproof_query instead when the agent needs structured fact/score objects."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "Application to summarize.",
                        },
                        "app_version": {
                            "type": "string",
                            "description": "Optional version scope. Default 'unknown'.",
                            "default": "unknown",
                        },
                    },
                    "required": ["app_name"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:

        if name == "clickproof_add_fact":
            result: Any = clickproof_add_fact(**arguments)
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

    async def _main() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_main())


if __name__ == "__main__":
    run_server()
