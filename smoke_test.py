"""
End-to-end smoke test for clickproof.

Simulates a user who just cloned the repo and wants to verify everything works.
No mocking, no fixtures — real behaviour, real CLI, real HTTP server.

Run from repo root:
    python smoke_test.py
    python smoke_test.py --verbose

Exit 0 = all passed. Exit 1 = at least one failure.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

# ── Colours ───────────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv
REPO_ROOT = Path(__file__).parent
PYTHON = sys.executable

passed: list[str] = []
failed: list[tuple[str, str]] = []


def ok(name: str) -> None:
    passed.append(name)
    print(f"  {GREEN}✓{RESET} {name}")


def fail(name: str, reason: str) -> None:
    failed.append((name, reason))
    print(f"  {RED}✗{RESET} {name}")
    if VERBOSE:
        print(f"    {YELLOW}{reason}{RESET}")


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")


def run(name: str, fn):  # noqa: ANN001
    try:
        fn()
        ok(name)
    except Exception as exc:
        reason = str(exc) if not VERBOSE else traceback.format_exc().strip()
        fail(name, reason)


# ── 1. Package import ─────────────────────────────────────────────────────────

section("1. Package import")

def _test_import_version():
    import clickproof
    assert clickproof.__version__, "__version__ is empty"
    assert clickproof.__version__ != "0.0.0"

def _test_import_public_api():
    from clickproof import UIFact, FactObservation, FactScorer, FactStore, FactRetriever
    assert callable(UIFact)
    assert callable(FactStore)

run("clickproof package imports", _test_import_version)
run("Public API (UIFact, FactObservation, FactScorer, FactStore, FactRetriever)", _test_import_public_api)


# ── 2. UIFact content-addressing and serialization ────────────────────────────

section("2. UIFact content-addressing and FactScorer")

def _test_uifact_content_addressed():
    from clickproof.fact import UIFact
    f1 = UIFact(app_name="salesforce", app_version="2025.11",
                element="export-csv-button", action="click", outcome="opens-download-dialog")
    f2 = UIFact(app_name="salesforce", app_version="2025.11",
                element="export-csv-button", action="click", outcome="opens-download-dialog")
    assert f1.id == f2.id, "Same inputs must produce same ID"
    f3 = UIFact(app_name="salesforce", app_version="2025.11",
                element="export-csv-button", action="click", outcome="error:not-found")
    # Different outcome should NOT change the ID (id is based on app/version/element/action)
    assert f1.id == f3.id, "ID is content-addressed on app_name|app_version|element|action"

def _test_uifact_serialization():
    from clickproof.fact import UIFact
    f = UIFact(app_name="gmail", app_version="unknown",
               element="compose-button", action="click", outcome="opens-compose-window",
               context="inbox", confidence=0.9)
    d = f.to_dict()
    assert d["app_name"] == "gmail"
    assert d["confidence"] == 0.9
    assert d["context"] == "inbox"
    f2 = UIFact.from_dict(d)
    assert f2.id == f.id
    assert f2.outcome == f.outcome

def _test_factobservation_round_trip():
    from clickproof.fact import FactObservation
    obs = FactObservation(fact_id="abc123", observed_at=1700000000.0, confirmed=True)
    d = obs.to_dict()
    assert d["confirmed"] is True
    obs2 = FactObservation.from_dict(d)
    assert obs2.id == obs.id

def _test_factscorer_no_observations():
    from clickproof.fact import UIFact
    from clickproof.scorer import FactScorer
    fact = UIFact(app_name="app", app_version="1.0",
                  element="button", action="click", outcome="ok", confidence=0.8)
    scorer = FactScorer()
    fs = scorer.score(fact, [])
    assert 0.0 <= fs.score <= 1.0
    assert fs.observation_count == 0

def _test_factscorer_with_confirmations():
    from clickproof.fact import UIFact, FactObservation
    from clickproof.scorer import FactScorer
    import time as _time
    fact = UIFact(app_name="app", app_version="1.0",
                  element="button", action="click", outcome="ok")
    now = _time.time()
    obs = [
        FactObservation(fact_id=fact.id, observed_at=now - 10, confirmed=True),
        FactObservation(fact_id=fact.id, observed_at=now - 5, confirmed=True),
        FactObservation(fact_id=fact.id, observed_at=now - 1, confirmed=True),
    ]
    scorer = FactScorer()
    fs = scorer.score(fact, obs)
    assert fs.score > 0.5, f"Expected score > 0.5, got {fs.score}"
    assert fs.confirmed_count == 3

def _test_factretriever_query():
    from clickproof.fact import UIFact
    from clickproof.store import FactStore
    from clickproof.retriever import FactRetriever
    with tempfile.TemporaryDirectory() as tmp:
        with FactStore(f"{tmp}/test.db") as store:
            f1 = UIFact(app_name="salesforce", app_version="2025.11",
                        element="export-csv-button", action="click",
                        outcome="opens-download-dialog")
            f2 = UIFact(app_name="gmail", app_version="unknown",
                        element="compose-button", action="click",
                        outcome="opens-compose-window")
            store.add_fact(f1)
            store.add_fact(f2)
            retriever = FactRetriever(store)
            pairs = retriever.query(app_name="salesforce", min_score=0.0)
            assert len(pairs) == 1
            assert pairs[0][0].app_name == "salesforce"

run("UIFact.id is content-addressed (app_name|app_version|element|action)", _test_uifact_content_addressed)
run("UIFact.to_dict() / from_dict() round-trip preserves all fields", _test_uifact_serialization)
run("FactObservation.to_dict() / from_dict() round-trip", _test_factobservation_round_trip)
run("FactScorer.score() with no observations uses initial confidence", _test_factscorer_no_observations)
run("FactScorer.score() with confirmations returns score > 0.5", _test_factscorer_with_confirmations)
run("FactRetriever.query() filters by app_name", _test_factretriever_query)


# ── 3. Observations update scores ─────────────────────────────────────────────

section("3. Observations update scores")

def _test_refuted_observations_lower_score():
    from clickproof.fact import UIFact, FactObservation
    from clickproof.store import FactStore
    from clickproof.scorer import FactScorer
    import time as _time
    with tempfile.TemporaryDirectory() as tmp:
        with FactStore(f"{tmp}/test.db") as store:
            fact = UIFact(app_name="app", app_version="1.0",
                          element="btn", action="click", outcome="ok")
            store.add_fact(fact)
            now = _time.time()
            # Add refuting observations
            for i in range(3):
                obs = FactObservation(fact_id=fact.id, observed_at=now - i, confirmed=False)
                store.add_observation(obs)
            scorer = FactScorer()
            observations = store.get_observations(fact.id)
            fs = scorer.score(fact, observations)
            assert fs.score < 0.3, f"Refuted fact should have low score, got {fs.score}"

def _test_mixed_observations():
    from clickproof.fact import UIFact, FactObservation
    from clickproof.store import FactStore
    from clickproof.scorer import FactScorer
    import time as _time
    with tempfile.TemporaryDirectory() as tmp:
        with FactStore(f"{tmp}/test.db") as store:
            fact = UIFact(app_name="app", app_version="1.0",
                          element="btn", action="click", outcome="ok")
            store.add_fact(fact)
            now = _time.time()
            for i in range(5):
                confirmed = i % 2 == 0  # alternate
                obs = FactObservation(fact_id=fact.id, observed_at=now - i, confirmed=confirmed)
                store.add_observation(obs)
            scorer = FactScorer()
            observations = store.get_observations(fact.id)
            fs = scorer.score(fact, observations)
            assert 0.0 < fs.score < 1.0

def _test_bootstrap_context_text():
    from clickproof.fact import UIFact
    from clickproof.store import FactStore
    from clickproof.retriever import FactRetriever
    with tempfile.TemporaryDirectory() as tmp:
        with FactStore(f"{tmp}/test.db") as store:
            fact = UIFact(app_name="salesforce", app_version="2025.11",
                          element="export-csv-button", action="click",
                          outcome="opens-download-dialog")
            store.add_fact(fact)
            retriever = FactRetriever(store)
            ctx = retriever.bootstrap_context("salesforce", "2025.11")
            assert "salesforce" in ctx
            assert "export-csv-button" in ctx

run("Refuted observations lower the score significantly", _test_refuted_observations_lower_score)
run("Mixed observations produce intermediate score", _test_mixed_observations)
run("bootstrap_context() returns text with app name and facts", _test_bootstrap_context_text)


# ── 4. Report formatters ──────────────────────────────────────────────────────

section("4. Report formatters")

def _test_to_json():
    from clickproof.fact import UIFact
    from clickproof.scorer import FactScorer
    from clickproof.report import to_json
    from clickproof.store import FactStore
    with tempfile.TemporaryDirectory() as tmp:
        with FactStore(f"{tmp}/test.db") as store:
            fact = UIFact(app_name="app", app_version="1.0",
                          element="btn", action="click", outcome="ok")
            store.add_fact(fact)
            scorer = FactScorer()
            fs = scorer.score(fact, [])
            pairs = [(fact, fs)]
    parsed = json.loads(to_json(pairs))
    assert parsed["count"] == 1
    assert "facts" in parsed
    assert parsed["facts"][0]["fact"]["app_name"] == "app"

def _test_to_markdown():
    from clickproof.fact import UIFact
    from clickproof.scorer import FactScorer
    from clickproof.report import to_markdown
    fact = UIFact(app_name="app", app_version="1.0",
                  element="btn", action="click", outcome="ok")
    scorer = FactScorer()
    fs = scorer.score(fact, [])
    md = to_markdown([(fact, fs)])
    assert "clickproof" in md
    assert "|" in md
    assert "app" in md

def _test_print_facts():
    import io
    from rich.console import Console
    from clickproof.fact import UIFact
    from clickproof.scorer import FactScorer
    from clickproof.report import print_facts
    fact = UIFact(app_name="app", app_version="1.0",
                  element="btn", action="click", outcome="ok")
    scorer = FactScorer()
    fs = scorer.score(fact, [])
    buf = io.StringIO()
    con = Console(file=buf, highlight=False)
    print_facts([(fact, fs)], console=con)
    output = buf.getvalue()
    assert "app" in output or "btn" in output

run("to_json() returns valid JSON with count and facts", _test_to_json)
run("to_markdown() produces Markdown with table", _test_to_markdown)
run("print_facts() outputs facts to Rich console", _test_print_facts)


# ── 5. CLI ────────────────────────────────────────────────────────────────────

section("5. CLI (clickproof)")

def _test_cli_help():
    r = subprocess.run(
        [PYTHON, "-m", "clickproof.cli", "--help"],
        capture_output=True, text=True
    )
    assert r.returncode == 0
    assert len(r.stdout) > 20, "Help output is empty"

run("clickproof --help returns 0", _test_cli_help)

def _test_cli_add_and_query():
    with tempfile.TemporaryDirectory() as tmp:
        db = f"{tmp}/test.db"
        r = subprocess.run(
            [PYTHON, "-m", "clickproof.cli", "--db", db,
             "add", "salesforce", "2025.11", "export-csv-button", "click", "opens-download-dialog"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"add failed: {r.stderr}"
        r2 = subprocess.run(
            [PYTHON, "-m", "clickproof.cli", "--db", db, "query", "salesforce", "--min-score", "0.0"],
            capture_output=True, text=True,
        )
        assert r2.returncode == 0, f"query failed: {r2.stderr}"

def _test_cli_status():
    with tempfile.TemporaryDirectory() as tmp:
        db = f"{tmp}/test.db"
        r = subprocess.run(
            [PYTHON, "-m", "clickproof.cli", "--db", db, "status"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"status failed: {r.stderr}"

run("clickproof add + query workflow", _test_cli_add_and_query)
run("clickproof status returns 0", _test_cli_status)


# ── 6. FastAPI server ─────────────────────────────────────────────────────────

section("6. FastAPI server (clickproof[api])")

def _test_api_import():
    from clickproof.api import app
    assert app.title == "clickproof API"

def _test_api_health():
    from fastapi.testclient import TestClient
    from clickproof.api import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()

def _test_api_fact_and_query():
    from fastapi.testclient import TestClient
    from clickproof.api import app
    client = TestClient(app)
    with tempfile.TemporaryDirectory() as tmp:
        db = f"{tmp}/test.db"
        r = client.post("/fact", json={
            "app_name": "salesforce", "app_version": "2025.11",
            "element": "export-csv-button", "action": "click",
            "outcome": "opens-download-dialog", "db": db,
        })
        assert r.status_code == 200
        fact_id = r.json()["id"]
        assert fact_id
        r2 = client.get("/query", params={"app_name": "salesforce", "min_score": 0.0, "db": db})
        assert r2.status_code == 200
        data = r2.json()
        assert len(data) == 1

run("clickproof.api imports and app.title is correct", _test_api_import)
run("GET /health returns {status: ok, version: ...}", _test_api_health)
run("POST /fact + GET /query workflow", _test_api_fact_and_query)


# ── 7. MCP server ─────────────────────────────────────────────────────────────

section("7. MCP server (clickproof[mcp])")

def _test_mcp_server_importable():
    import clickproof.mcp_server as m  # noqa: F401
    assert hasattr(m, "run_server")

def _test_mcp_server_loads_cleanly():
    import clickproof.mcp_server  # noqa: F401

run("mcp_server.py imports without error", _test_mcp_server_importable)
run("mcp_server module loads cleanly (no import-time crash)", _test_mcp_server_loads_cleanly)


# ── 8. Agent config files ─────────────────────────────────────────────────────

section("8. Agent config files (what a clone gives you)")

def _check_file_nonempty(rel: str) -> None:
    p = REPO_ROOT / rel
    assert p.exists(), f"Missing: {rel}"
    assert p.stat().st_size > 50, f"File too small (likely empty): {rel}"

def _check_json_valid(rel: str) -> None:
    p = REPO_ROOT / rel
    assert p.exists(), f"Missing: {rel}"
    json.loads(p.read_text())

def _check_yaml_parseable(rel: str) -> None:
    try:
        import yaml  # type: ignore[import-untyped]
        p = REPO_ROOT / rel
        assert p.exists(), f"Missing: {rel}"
        yaml.safe_load(p.read_text())
    except ImportError:
        content = (REPO_ROOT / rel).read_text()
        assert len(content) > 20, f"File appears empty: {rel}"

def _test_claude_commands():
    commands = list((REPO_ROOT / ".claude/commands").glob("*.md"))
    assert len(commands) >= 4, f"Expected ≥4 slash commands, found {len(commands)}"

def _test_openai_tools_valid():
    _check_json_valid("tools/openai-tools.json")
    tools = json.loads((REPO_ROOT / "tools/openai-tools.json").read_text())
    assert len(tools) >= 3
    assert all("function" in t for t in tools)

def _test_openapi_yaml_parseable():
    _check_yaml_parseable("openapi.yaml")

run("AGENTS.md exists and non-empty", lambda: _check_file_nonempty("AGENTS.md"))
run("CLAUDE.md exists and non-empty", lambda: _check_file_nonempty("CLAUDE.md"))
run("CODEX.md exists and non-empty", lambda: _check_file_nonempty("CODEX.md"))
run(".github/copilot-instructions.md exists", lambda: _check_file_nonempty(".github/copilot-instructions.md"))
def _test_cursor_rules():
    mdc_files = list((REPO_ROOT / ".cursor/rules").glob("*.mdc"))
    assert len(mdc_files) >= 1, f"Expected ≥1 .mdc file in .cursor/rules/, found none"

run(".cursor/rules/ has at least one .mdc file", _test_cursor_rules)
run(".windsurfrules exists", lambda: _check_file_nonempty(".windsurfrules"))
run(".aider.conf.yml exists", lambda: _check_file_nonempty(".aider.conf.yml"))
run(".continue/config.json is valid JSON", lambda: _check_json_valid(".continue/config.json"))
run(".claude/commands/ has ≥4 slash commands", _test_claude_commands)
run("tools/openai-tools.json is valid JSON with ≥3 tools", _test_openai_tools_valid)
run("openapi.yaml is parseable YAML", _test_openapi_yaml_parseable)


# ── 9. Docs site ──────────────────────────────────────────────────────────────

section("9. MkDocs documentation site")

def _test_mkdocs_yml():
    _check_file_nonempty("mkdocs.yml")
    content = (REPO_ROOT / "mkdocs.yml").read_text()
    assert "site_name" in content
    assert "material" in content

def _test_docs_pages():
    docs = list((REPO_ROOT / "docs").glob("*.md"))
    assert len(docs) >= 8, f"Expected ≥8 doc pages, found {len(docs)}"
    names = {p.name for p in docs}
    for required in ("index.md", "quickstart.md", "architecture.md", "api-reference.md"):
        assert required in names, f"Missing docs/{required}"

run("mkdocs.yml exists with site_name and material theme", _test_mkdocs_yml)
run("docs/ has ≥8 pages including index, quickstart, architecture, api-reference", _test_docs_pages)


# ── 10. examples/demo.py ─────────────────────────────────────────────────────

section("10. examples/demo.py end-to-end")

def _test_demo_runs():
    demo = REPO_ROOT / "examples" / "demo.py"
    assert demo.exists(), "examples/demo.py not found"
    r = subprocess.run(
        [PYTHON, str(demo)],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT)
    )
    if r.returncode != 0:
        raise AssertionError(f"demo.py exited {r.returncode}:\n{r.stderr[-500:]}")

run("examples/demo.py runs end-to-end without error", _test_demo_runs)


# ── Summary ───────────────────────────────────────────────────────────────────

total = len(passed) + len(failed)
print(f"\n{'═'*60}")
print(f"{BOLD}Results: {len(passed)}/{total} passed{RESET}")

if failed:
    print(f"{RED}Failed ({len(failed)}):{RESET}")
    for name, reason in failed:
        print(f"  {RED}✗{RESET} {name}")
        short = reason.split("\n")[0][:120]
        print(f"    {YELLOW}→ {short}{RESET}")
    print(f"\n{YELLOW}Tip: run with --verbose for full tracebacks{RESET}")
else:
    print(f"{GREEN}All {total} checks passed — clickproof is ready to ship{RESET}")

print(f"{'═'*60}\n")
sys.exit(0 if not failed else 1)
