"""Tests for the CLI export and decay commands."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from clickproof.cli import main
from clickproof.fact import FactObservation, UIFact
from clickproof.store import FactStore


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


def _add_fact_with_obs(db_path: str, app: str = "myapp") -> UIFact:
    """Helper: add a fact and two confirming observations to the db."""
    now = time.time()
    fact = UIFact(
        app_name=app,
        app_version="1.0",
        element="save-button",
        action="click",
        outcome="saves",
    )
    with FactStore(db_path) as store:
        store.add_fact(fact)
        for i in range(2):
            obs = FactObservation(
                fact_id=fact.id,
                observed_at=now - i * 10,
                confirmed=True,
            )
            store.add_observation(obs)
    return fact


class TestCliExport:
    def test_export_stdout(self, runner: CliRunner, db_path: str) -> None:
        _add_fact_with_obs(db_path)
        result = runner.invoke(main, ["--db", db_path, "export", "myapp"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1
        assert data["app_name"] == "myapp"

    def test_export_empty_store(self, runner: CliRunner, db_path: str) -> None:
        result = runner.invoke(main, ["--db", db_path, "export", "myapp"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 0

    def test_export_bootstrap_flag(self, runner: CliRunner, db_path: str) -> None:
        _add_fact_with_obs(db_path)
        result = runner.invoke(main, ["--db", db_path, "export", "myapp", "--bootstrap"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["bootstrap_pack"] is True

    def test_export_to_file(self, runner: CliRunner, db_path: str, tmp_path: Path) -> None:
        _add_fact_with_obs(db_path)
        out_file = str(tmp_path / "out.json")
        result = runner.invoke(
            main, ["--db", db_path, "export", "myapp", "--output", out_file]
        )
        assert result.exit_code == 0
        with open(out_file) as fh:
            data = json.load(fh)
        assert data["count"] == 1

    def test_export_to_file_shows_message(
        self, runner: CliRunner, db_path: str, tmp_path: Path
    ) -> None:
        _add_fact_with_obs(db_path)
        out_file = str(tmp_path / "out.json")
        result = runner.invoke(
            main, ["--db", db_path, "export", "myapp", "--output", out_file]
        )
        assert result.exit_code == 0
        # The console prints "Exported to ..."
        assert "Exported" in result.output or out_file in result.output

    def test_export_structure_has_observations(self, runner: CliRunner, db_path: str) -> None:
        _add_fact_with_obs(db_path)
        result = runner.invoke(main, ["--db", db_path, "export", "myapp"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        entry = data["facts"][0]
        assert "observations" in entry
        assert len(entry["observations"]) == 2


class TestCliDecay:
    def test_decay_empty_store_rich(self, runner: CliRunner, db_path: str) -> None:
        result = runner.invoke(main, ["--db", db_path, "decay", "myapp"])
        assert result.exit_code == 0

    def test_decay_empty_store_json(self, runner: CliRunner, db_path: str) -> None:
        result = runner.invoke(
            main, ["--db", db_path, "decay", "myapp", "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_decay_with_facts_rich(self, runner: CliRunner, db_path: str) -> None:
        _add_fact_with_obs(db_path)
        result = runner.invoke(main, ["--db", db_path, "decay", "myapp"])
        assert result.exit_code == 0

    def test_decay_with_facts_json(self, runner: CliRunner, db_path: str) -> None:
        _add_fact_with_obs(db_path)
        result = runner.invoke(
            main, ["--db", db_path, "decay", "myapp", "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        row = data[0]
        assert "fact_id" in row
        assert "element" in row
        assert "current_score" in row
        assert "score_in_7_days" in row
        assert "score_in_30_days" in row
        assert "days_until_threshold" in row
        assert "recommendation" in row

    def test_decay_min_score_option(self, runner: CliRunner, db_path: str) -> None:
        _add_fact_with_obs(db_path)
        result = runner.invoke(
            main,
            ["--db", db_path, "decay", "myapp", "--min-score", "0.0", "--format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1

    def test_decay_json_recommendation_field(self, runner: CliRunner, db_path: str) -> None:
        _add_fact_with_obs(db_path)
        result = runner.invoke(
            main, ["--db", db_path, "decay", "myapp", "--format", "json"]
        )
        data = json.loads(result.output)
        for row in data:
            assert row["recommendation"] in {"ok", "re-validate", "archive"}
