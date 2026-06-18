"""Tests for the CLI using Click's CliRunner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from guiproof.cli import main
from guiproof.store import FactStore


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


class TestCliAdd:
    def test_add_basic(self, runner: CliRunner, db_path: str) -> None:
        result = runner.invoke(
            main,
            ["--db", db_path, "add", "salesforce", "2025.11",
             "export-csv-button", "click", "opens-download-dialog"],
        )
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_add_with_context(self, runner: CliRunner, db_path: str) -> None:
        result = runner.invoke(
            main,
            ["--db", db_path, "add", "app", "1.0",
             "btn", "click", "ok", "--context", "reports-page"],
        )
        assert result.exit_code == 0

    def test_add_with_confidence(self, runner: CliRunner, db_path: str) -> None:
        result = runner.invoke(
            main,
            ["--db", db_path, "add", "app", "1.0",
             "btn", "click", "ok", "--confidence", "0.7"],
        )
        assert result.exit_code == 0

    def test_add_persists_to_store(self, runner: CliRunner, db_path: str) -> None:
        runner.invoke(
            main,
            ["--db", db_path, "add", "salesforce", "2025.11",
             "export-csv-button", "click", "opens-download-dialog"],
        )
        with FactStore(db_path) as store:
            facts = store.list_facts()
        assert len(facts) == 1

    def test_add_duplicate_is_idempotent(self, runner: CliRunner, db_path: str) -> None:
        args = ["--db", db_path, "add", "app", "1.0", "btn", "click", "ok"]
        runner.invoke(main, args)
        runner.invoke(main, args)
        with FactStore(db_path) as store:
            assert len(store.list_facts()) == 1


class TestCliObserve:
    def test_observe_confirmed(self, runner: CliRunner, db_path: str) -> None:
        # First add a fact
        runner.invoke(
            main,
            ["--db", db_path, "add", "app", "1.0", "btn", "click", "ok"],
        )
        with FactStore(db_path) as store:
            fact = store.list_facts()[0]
        result = runner.invoke(
            main,
            ["--db", db_path, "observe", fact.id, "--confirmed"],
        )
        assert result.exit_code == 0
        assert "confirmed" in result.output.lower()

    def test_observe_refuted(self, runner: CliRunner, db_path: str) -> None:
        runner.invoke(
            main,
            ["--db", db_path, "add", "app", "1.0", "btn", "click", "ok"],
        )
        with FactStore(db_path) as store:
            fact = store.list_facts()[0]
        result = runner.invoke(
            main,
            ["--db", db_path, "observe", fact.id, "--refuted"],
        )
        assert result.exit_code == 0
        assert "refuted" in result.output.lower()

    def test_observe_nonexistent_fact(self, runner: CliRunner, db_path: str) -> None:
        result = runner.invoke(
            main,
            ["--db", db_path, "observe", "nonexistent_id", "--confirmed"],
        )
        assert result.exit_code != 0


class TestCliQuery:
    def test_query_empty_store(self, runner: CliRunner, db_path: str) -> None:
        result = runner.invoke(
            main,
            ["--db", db_path, "query", "salesforce"],
        )
        assert result.exit_code == 0

    def test_query_returns_facts(self, runner: CliRunner, db_path: str) -> None:
        runner.invoke(
            main,
            ["--db", db_path, "add", "salesforce", "2025.11",
             "export-csv-button", "click", "opens-download-dialog"],
        )
        result = runner.invoke(
            main,
            ["--db", db_path, "query", "salesforce", "--min-score", "0.0"],
        )
        assert result.exit_code == 0

    def test_query_json_output(self, runner: CliRunner, db_path: str) -> None:
        runner.invoke(
            main,
            ["--db", db_path, "add", "app", "1.0", "btn", "click", "ok"],
        )
        result = runner.invoke(
            main,
            ["--db", db_path, "query", "app", "--min-score", "0.0", "--json"],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "count" in parsed


class TestCliLog:
    def test_log_empty(self, runner: CliRunner, db_path: str) -> None:
        result = runner.invoke(main, ["--db", db_path, "log"])
        assert result.exit_code == 0

    def test_log_shows_facts(self, runner: CliRunner, db_path: str) -> None:
        runner.invoke(
            main,
            ["--db", db_path, "add", "salesforce", "2025.11",
             "export-csv-button", "click", "opens-download-dialog"],
        )
        result = runner.invoke(main, ["--db", db_path, "log"])
        assert result.exit_code == 0

    def test_log_json_output(self, runner: CliRunner, db_path: str) -> None:
        runner.invoke(
            main,
            ["--db", db_path, "add", "app", "1.0", "btn", "click", "ok"],
        )
        result = runner.invoke(main, ["--db", db_path, "log", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "count" in parsed


class TestCliStatus:
    def test_status_empty_store(self, runner: CliRunner, db_path: str) -> None:
        result = runner.invoke(main, ["--db", db_path, "status"])
        assert result.exit_code == 0
        assert "facts" in result.output.lower() or "database" in result.output.lower()

    def test_status_with_facts(self, runner: CliRunner, db_path: str) -> None:
        runner.invoke(
            main,
            ["--db", db_path, "add", "salesforce", "2025.11",
             "export-csv-button", "click", "opens-download-dialog"],
        )
        result = runner.invoke(main, ["--db", db_path, "status"])
        assert result.exit_code == 0
        assert "1" in result.output

    def test_help_returns_zero(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert len(result.output) > 20
