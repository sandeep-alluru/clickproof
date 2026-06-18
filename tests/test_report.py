"""Tests for report formatters."""

from __future__ import annotations

import io
import json

import pytest
from rich.console import Console

from guiproof.fact import UIFact
from guiproof.report import print_fact, print_facts, to_json, to_markdown
from guiproof.scorer import FactScore, FactScorer


@pytest.fixture
def sample_pair() -> tuple[UIFact, FactScore]:
    fact = UIFact(
        app_name="salesforce", app_version="2025.11",
        element="export-csv-button", action="click", outcome="opens-download-dialog",
    )
    scorer = FactScorer()
    score = scorer.score(fact, [])
    return fact, score


@pytest.fixture
def multiple_pairs() -> list[tuple[UIFact, FactScore]]:
    facts = [
        UIFact(app_name="app", app_version="1.0",
               element=f"btn-{i}", action="click", outcome="ok")
        for i in range(3)
    ]
    scorer = FactScorer()
    return [(f, scorer.score(f, [])) for f in facts]


def _make_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    con = Console(file=buf, highlight=False, no_color=True)
    return con, buf


class TestToJson:
    def test_returns_valid_json(
        self, sample_pair: tuple[UIFact, FactScore]
    ) -> None:
        result = to_json([sample_pair])
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_count_field(
        self, multiple_pairs: list[tuple[UIFact, FactScore]]
    ) -> None:
        result = to_json(multiple_pairs)
        parsed = json.loads(result)
        assert parsed["count"] == 3

    def test_facts_field(
        self, multiple_pairs: list[tuple[UIFact, FactScore]]
    ) -> None:
        result = to_json(multiple_pairs)
        parsed = json.loads(result)
        assert "facts" in parsed
        assert len(parsed["facts"]) == 3

    def test_fact_contains_app_name(
        self, sample_pair: tuple[UIFact, FactScore]
    ) -> None:
        result = to_json([sample_pair])
        parsed = json.loads(result)
        assert parsed["facts"][0]["fact"]["app_name"] == "salesforce"

    def test_score_contains_score_field(
        self, sample_pair: tuple[UIFact, FactScore]
    ) -> None:
        result = to_json([sample_pair])
        parsed = json.loads(result)
        assert "score" in parsed["facts"][0]["score"]

    def test_empty_list(self) -> None:
        result = to_json([])
        parsed = json.loads(result)
        assert parsed["count"] == 0
        assert parsed["facts"] == []


class TestToMarkdown:
    def test_contains_guiproof_header(
        self, sample_pair: tuple[UIFact, FactScore]
    ) -> None:
        md = to_markdown([sample_pair])
        assert "guiproof" in md

    def test_contains_table(
        self, sample_pair: tuple[UIFact, FactScore]
    ) -> None:
        md = to_markdown([sample_pair])
        assert "|" in md

    def test_contains_app_name(
        self, sample_pair: tuple[UIFact, FactScore]
    ) -> None:
        md = to_markdown([sample_pair])
        assert "salesforce" in md

    def test_count_line(
        self, multiple_pairs: list[tuple[UIFact, FactScore]]
    ) -> None:
        md = to_markdown(multiple_pairs)
        assert "3" in md

    def test_empty_list(self) -> None:
        md = to_markdown([])
        assert "guiproof" in md
        assert "0" in md


class TestPrintFacts:
    def test_prints_table_content(
        self, sample_pair: tuple[UIFact, FactScore]
    ) -> None:
        con, buf = _make_console()
        print_facts([sample_pair], console=con)
        output = buf.getvalue()
        assert "salesforce" in output or "export" in output

    def test_empty_list_prints_message(self) -> None:
        con, buf = _make_console()
        print_facts([], console=con)
        output = buf.getvalue()
        assert len(output) > 0

    def test_multiple_facts(
        self, multiple_pairs: list[tuple[UIFact, FactScore]]
    ) -> None:
        con, buf = _make_console()
        print_facts(multiple_pairs, console=con)
        output = buf.getvalue()
        assert len(output) > 20


class TestPrintFact:
    def test_prints_element(self, sample_pair: tuple[UIFact, FactScore]) -> None:
        fact, score = sample_pair
        con, buf = _make_console()
        print_fact(fact, score=score, console=con)
        output = buf.getvalue()
        assert "export-csv-button" in output

    def test_prints_without_score(
        self, sample_pair: tuple[UIFact, FactScore]
    ) -> None:
        fact, _ = sample_pair
        con, buf = _make_console()
        print_fact(fact, console=con)
        output = buf.getvalue()
        assert "salesforce" in output

    def test_prints_context_when_present(self) -> None:
        fact = UIFact(app_name="app", app_version="1.0",
                      element="btn", action="click", outcome="ok",
                      context="dashboard")
        con, buf = _make_console()
        print_fact(fact, console=con)
        output = buf.getvalue()
        assert "dashboard" in output
