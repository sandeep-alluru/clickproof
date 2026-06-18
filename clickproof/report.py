"""Report formatters — Rich console, JSON, and Markdown output for clickproof."""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table

from clickproof.fact import UIFact
from clickproof.scorer import FactScore


def _default_console() -> Console:
    return Console()


def print_facts(
    scores: list[tuple[UIFact, FactScore]],
    console: Console | None = None,
) -> None:
    """Print a table of facts and their scores to the console.

    Args:
        scores: List of (UIFact, FactScore) pairs.
        console: Optional Rich Console. A new one is created if not provided.
    """
    con = console or _default_console()

    if not scores:
        con.print("[yellow]No facts found.[/yellow]")
        return

    table = Table(
        title="clickproof — UI Behavioral Facts",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Score", style="bold green", width=6)
    table.add_column("App", style="cyan")
    table.add_column("Version", style="dim")
    table.add_column("Element", style="white")
    table.add_column("Action", style="yellow")
    table.add_column("Outcome", style="white")
    table.add_column("Obs", justify="right", style="dim")

    for fact, score in scores:
        score_str = f"{score.score:.2f}"
        color = "green" if score.score >= 0.7 else ("yellow" if score.score >= 0.4 else "red")
        table.add_row(
            f"[{color}]{score_str}[/{color}]",
            fact.app_name,
            fact.app_version,
            fact.element,
            fact.action,
            fact.outcome,
            str(score.observation_count),
        )

    con.print(table)


def print_fact(
    fact: UIFact,
    score: FactScore | None = None,
    console: Console | None = None,
) -> None:
    """Print a single fact with optional score detail.

    Args:
        fact: The UIFact to display.
        score: Optional FactScore for this fact.
        console: Optional Rich Console.
    """
    con = console or _default_console()
    con.print(f"[bold cyan]UIFact[/bold cyan] [dim]{fact.id}[/dim]")
    con.print(f"  app:     [cyan]{fact.app_name}[/cyan] v{fact.app_version}")
    con.print(f"  element: {fact.element}")
    con.print(f"  action:  [yellow]{fact.action}[/yellow]")
    con.print(f"  outcome: {fact.outcome}")
    if fact.context:
        con.print(f"  context: [dim]{fact.context}[/dim]")
    if score is not None:
        color = "green" if score.score >= 0.7 else ("yellow" if score.score >= 0.4 else "red")
        con.print(
            f"  score:   [{color}]{score.score:.4f}[/{color}]"
            f"  ({score.confirmed_count}/{score.observation_count} obs,"
            f" {score.staleness_days:.1f}d stale)"
        )


def to_json(facts_scores: list[tuple[UIFact, FactScore]]) -> str:
    """Serialize facts and scores to a JSON string.

    Args:
        facts_scores: List of (UIFact, FactScore) pairs.

    Returns:
        JSON string with keys ``count``, ``facts``.
    """
    payload = {
        "count": len(facts_scores),
        "facts": [
            {
                "fact": fact.to_dict(),
                "score": score.to_dict(),
            }
            for fact, score in facts_scores
        ],
    }
    return json.dumps(payload, indent=2)


def to_markdown(facts_scores: list[tuple[UIFact, FactScore]]) -> str:
    """Format facts and scores as a Markdown table.

    Args:
        facts_scores: List of (UIFact, FactScore) pairs.

    Returns:
        Markdown string with a header and table.
    """
    lines = [
        "## clickproof — UI Behavioral Facts",
        "",
        f"_{len(facts_scores)} fact(s) retrieved_",
        "",
        "| Score | App | Version | Element | Action | Outcome | Obs |",
        "|------:|-----|---------|---------|--------|---------|----:|",
    ]

    for fact, score in facts_scores:
        lines.append(
            f"| {score.score:.2f}"
            f" | {fact.app_name}"
            f" | {fact.app_version}"
            f" | {fact.element}"
            f" | {fact.action}"
            f" | {fact.outcome}"
            f" | {score.observation_count} |"
        )

    return "\n".join(lines)
