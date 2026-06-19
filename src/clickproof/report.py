"""Report formatters — JSON, Markdown, and rich console output."""
from __future__ import annotations

import json

from clickproof.fact import UIFact
from clickproof.scorer import FactScore


def to_json(pairs: list[tuple[UIFact, FactScore]]) -> str:
    """Serialize (fact, score) pairs to a JSON string."""
    facts_list = []
    for fact, score in pairs:
        facts_list.append(
            {
                "fact": fact.to_dict(),
                "score": {
                    "score": score.score,
                    "confirmed_count": score.confirmed_count,
                    "observation_count": score.observation_count,
                    "last_seen_at": score.last_seen_at,
                },
            }
        )
    return json.dumps({"count": len(facts_list), "facts": facts_list}, indent=2)


def to_markdown(pairs: list[tuple[UIFact, FactScore]]) -> str:
    """Return a GitHub-flavoured markdown table."""
    lines = [
        "| Score | App | Element | Action | Outcome | Confirmed/Total |",
        "|-------|-----|---------|--------|---------|-----------------|",
    ]
    for fact, score in pairs:
        lines.append(
            f"| {score.score:.3f} | {fact.app_name} {fact.app_version} "
            f"| {fact.element} | {fact.action} | {fact.outcome} "
            f"| {score.confirmed_count}/{score.observation_count} |"
        )
    return "\n".join(lines)


def print_facts(pairs: list[tuple[UIFact, FactScore]]) -> None:
    """Pretty-print using rich if available, otherwise plain text."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="clickproof facts", show_lines=True)
        table.add_column("Score", style="cyan", justify="right")
        table.add_column("App")
        table.add_column("Element", style="bold")
        table.add_column("Action")
        table.add_column("Outcome")
        table.add_column("Confirmed/Total", justify="right")

        for fact, score in pairs:
            colour = "green" if score.score >= 0.7 else ("yellow" if score.score >= 0.4 else "red")
            table.add_row(
                f"[{colour}]{score.score:.3f}[/{colour}]",
                f"{fact.app_name} {fact.app_version}",
                fact.element,
                fact.action,
                fact.outcome,
                f"{score.confirmed_count}/{score.observation_count}",
            )

        console.print(table)

    except ImportError:
        # Fallback: plain print
        header = f"{'Score':>7}  {'App':<20}  {'Element':<28}  {'Action':<12}  {'Outcome':<30}  Conf/Total"
        print(header)
        print("-" * len(header))
        for fact, score in pairs:
            print(
                f"{score.score:7.3f}  "
                f"{fact.app_name + ' ' + fact.app_version:<20}  "
                f"{fact.element:<28}  "
                f"{fact.action:<12}  "
                f"{fact.outcome:<30}  "
                f"{score.confirmed_count}/{score.observation_count}"
            )
