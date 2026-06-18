"""guiproof CLI — store, observe, and query UI behavioral facts."""

from __future__ import annotations

import time

import click
from rich.console import Console

from guiproof.fact import FactObservation, UIFact
from guiproof.report import print_facts, to_json
from guiproof.retriever import FactRetriever
from guiproof.scorer import FactScorer
from guiproof.store import FactStore

_console = Console()


@click.group()
@click.option(
    "--db",
    default="guiproof.db",
    show_default=True,
    envvar="GUIPROOF_DB",
    help="Path to the SQLite database file.",
)
@click.version_option(package_name="guiproof")
@click.pass_context
def main(ctx: click.Context, db: str) -> None:
    """guiproof — persistent GUI behavioral facts for computer-use agents."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = db


# ── add ───────────────────────────────────────────────────────────────────────


@main.command()
@click.argument("app")
@click.argument("version")
@click.argument("element")
@click.argument("action")
@click.argument("outcome")
@click.option("--context", default="", help="Optional UI context (e.g. reports-page).")
@click.option("--confidence", default=1.0, show_default=True, help="Initial confidence [0-1].")
@click.pass_context
def add(
    ctx: click.Context,
    app: str,
    version: str,
    element: str,
    action: str,
    outcome: str,
    context: str,
    confidence: float,
) -> None:
    """Stage a UIFact.

    \b
    Examples:
      guiproof add salesforce 2025.11 export-csv-button click opens-download-dialog
      guiproof add gmail unknown compose-button click opens-compose-window --context inbox
    """
    fact = UIFact(
        app_name=app,
        app_version=version,
        element=element,
        action=action,
        outcome=outcome,
        context=context,
        confidence=confidence,
    )
    with FactStore(ctx.obj["db"]) as store:
        store.add_fact(fact)
    _console.print(f"[green]✓[/green] Added fact [dim]{fact.id}[/dim]: {fact.element}")


# ── observe ───────────────────────────────────────────────────────────────────


@main.command()
@click.argument("fact_id")
@click.option(
    "--confirmed/--refuted",
    default=True,
    help="Whether the observation confirms or refutes the fact.",
)
@click.option("--run-id", default="", help="Optional agent run ID for tracing.")
@click.pass_context
def observe(ctx: click.Context, fact_id: str, confirmed: bool, run_id: str) -> None:
    """Record an observation confirming or refuting a UIFact.

    \b
    Examples:
      guiproof observe abc123def456 --confirmed
      guiproof observe abc123def456 --refuted --run-id run_20251101
    """
    obs = FactObservation(
        fact_id=fact_id,
        observed_at=time.time(),
        confirmed=confirmed,
        agent_run_id=run_id,
    )
    with FactStore(ctx.obj["db"]) as store:
        fact = store.get_fact(fact_id)
        if fact is None:
            _console.print(f"[red]✗[/red] Fact {fact_id!r} not found in store.")
            raise SystemExit(1)
        store.add_observation(obs)
    status = "[green]confirmed[/green]" if confirmed else "[red]refuted[/red]"
    _console.print(f"[green]✓[/green] Observation {obs.id!r} recorded as {status}.")


# ── query ─────────────────────────────────────────────────────────────────────


@main.command()
@click.argument("app")
@click.option("--version", default=None, help="Filter to a specific app version.")
@click.option(
    "--min-score", default=0.5, show_default=True, help="Minimum confidence score threshold."
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def query(
    ctx: click.Context, app: str, version: str | None, min_score: float, as_json: bool
) -> None:
    """Retrieve facts for an app, sorted by confidence score.

    \b
    Examples:
      guiproof query salesforce
      guiproof query salesforce --version 2025.11 --min-score 0.7
      guiproof query gmail --json
    """
    with FactStore(ctx.obj["db"]) as store:
        retriever = FactRetriever(store, FactScorer())
        pairs = retriever.query(app_name=app, app_version=version, min_score=min_score)

    if as_json:
        click.echo(to_json(pairs))
    else:
        if not pairs:
            _console.print(f"[yellow]No facts found for {app!r} (min_score={min_score}).[/yellow]")
        else:
            print_facts(pairs, console=_console)


# ── log ───────────────────────────────────────────────────────────────────────


@main.command(name="log")
@click.option("--app", default=None, help="Filter by app name.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def log_cmd(ctx: click.Context, app: str | None, as_json: bool) -> None:
    """List all stored facts.

    \b
    Examples:
      guiproof log
      guiproof log --app salesforce
      guiproof log --json
    """
    with FactStore(ctx.obj["db"]) as store:
        facts = store.list_facts(app_name=app)
        scorer = FactScorer()
        pairs = []
        for fact in facts:
            observations = store.get_observations(fact.id)
            fs = scorer.score(fact, observations)
            pairs.append((fact, fs))

    if as_json:
        click.echo(to_json(pairs))
    else:
        if not pairs:
            _console.print("[yellow]Store is empty.[/yellow]")
        else:
            print_facts(pairs, console=_console)


# ── status ────────────────────────────────────────────────────────────────────


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show store information and statistics.

    \b
    Examples:
      guiproof status
      guiproof --db /path/to/store.db status
    """
    db_path = ctx.obj["db"]
    with FactStore(db_path) as store:
        facts = store.list_facts()
        total_obs = sum(len(store.get_observations(f.id)) for f in facts)
        apps: set[str] = {f.app_name for f in facts}

    _console.print("[bold cyan]guiproof store status[/bold cyan]")
    _console.print(f"  database:      {db_path}")
    _console.print(f"  facts:         {len(facts)}")
    _console.print(f"  observations:  {total_obs}")
    _console.print(f"  applications:  {len(apps)}")
    if apps:
        _console.print(f"  app list:      {', '.join(sorted(apps))}")


if __name__ == "__main__":
    main()
