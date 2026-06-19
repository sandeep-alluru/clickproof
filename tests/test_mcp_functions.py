"""Tests for the MCP server helper functions (no mcp package required)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import clickproof.mcp_server as mcp_mod
from clickproof.store import FactStore


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / "test.db")
    monkeypatch.setenv("CLICKPROOF_DB", path)
    # Force the module-level default to reload for this test
    mcp_mod._DEFAULT_DB = path
    return path


class TestMcpAddUiFact:
    def test_add_returns_fact_dict(self, db_path: str) -> None:
        result = mcp_mod.add_ui_fact(
            app_name="myapp",
            app_version="1.0",
            element="save-btn",
            action="click",
            outcome="saves",
        )
        assert "id" in result
        assert result["app_name"] == "myapp"

    def test_add_persists_to_store(self, db_path: str) -> None:
        mcp_mod.add_ui_fact(
            app_name="myapp",
            app_version="1.0",
            element="save-btn",
            action="click",
            outcome="saves",
        )
        with FactStore(db_path) as store:
            facts = store.list_facts("myapp")
        assert len(facts) == 1


class TestMcpQueryFacts:
    def test_query_empty_returns_empty(self, db_path: str) -> None:
        result = mcp_mod.query_facts(app_name="myapp")
        assert result == []

    def test_query_returns_facts(self, db_path: str) -> None:
        # Add a fact and a confirming observation
        fact_dict = mcp_mod.add_ui_fact(
            app_name="myapp",
            app_version="1.0",
            element="save-btn",
            action="click",
            outcome="saves",
        )
        # Add observation to boost score above 0.5
        with FactStore(db_path) as store:
            from clickproof.fact import FactObservation

            obs = FactObservation(
                fact_id=fact_dict["id"],
                observed_at=time.time(),
                confirmed=True,
            )
            store.add_observation(obs)
            obs2 = FactObservation(
                fact_id=fact_dict["id"],
                observed_at=time.time(),
                confirmed=True,
            )
            store.add_observation(obs2)

        result = mcp_mod.query_facts(app_name="myapp", min_score=0.0)
        assert len(result) == 1
        assert "fact" in result[0]
        assert "score" in result[0]


class TestMcpBootstrapContext:
    def test_bootstrap_empty_store(self, db_path: str) -> None:
        result = mcp_mod.bootstrap_context(app_name="myapp")
        assert isinstance(result, str)

    def test_bootstrap_with_facts(self, db_path: str) -> None:
        mcp_mod.add_ui_fact(
            app_name="myapp",
            app_version="1.0",
            element="save-btn",
            action="click",
            outcome="saves",
        )
        result = mcp_mod.bootstrap_context(app_name="myapp", app_version="1.0")
        assert isinstance(result, str)


class TestMcpClickproofAddFact:
    def test_returns_id(self, db_path: str) -> None:
        result = mcp_mod.clickproof_add_fact(
            app_name="myapp",
            app_version="1.0",
            element="btn",
            action="click",
            outcome="ok",
        )
        assert "id" in result
        assert isinstance(result["id"], str)

    def test_with_context_and_confidence(self, db_path: str) -> None:
        result = mcp_mod.clickproof_add_fact(
            app_name="myapp",
            app_version="1.0",
            element="btn",
            action="click",
            outcome="ok",
            context="reports",
            confidence=0.8,
        )
        assert "id" in result


class TestMcpClickproofObserve:
    def test_observe_returns_id(self, db_path: str) -> None:
        add_result = mcp_mod.clickproof_add_fact(
            app_name="myapp",
            app_version="1.0",
            element="btn",
            action="click",
            outcome="ok",
        )
        obs_result = mcp_mod.clickproof_observe(
            fact_id=add_result["id"],
            confirmed=True,
        )
        assert "id" in obs_result
        assert isinstance(obs_result["id"], str)

    def test_observe_persists(self, db_path: str) -> None:
        add_result = mcp_mod.clickproof_add_fact(
            app_name="myapp",
            app_version="1.0",
            element="btn",
            action="click",
            outcome="ok",
        )
        fact_id = add_result["id"]
        mcp_mod.clickproof_observe(fact_id=fact_id, confirmed=True, agent_run_id="run-1")
        with FactStore(db_path) as store:
            obs = store.get_observations(fact_id)
        assert len(obs) == 1
        assert obs[0].confirmed is True


class TestMcpClickproofQuery:
    def test_query_returns_dict_with_facts_and_count(self, db_path: str) -> None:
        result = mcp_mod.clickproof_query(app_name="myapp")
        assert "facts" in result
        assert "count" in result
        assert result["count"] == 0

    def test_query_filters_by_min_score(self, db_path: str) -> None:
        mcp_mod.clickproof_add_fact(
            app_name="myapp",
            app_version="1.0",
            element="btn",
            action="click",
            outcome="ok",
        )
        # With min_score=0.0 we should get the fact
        result = mcp_mod.clickproof_query(app_name="myapp", min_score=0.0)
        assert result["count"] >= 1


class TestMcpClickproofBootstrap:
    def test_bootstrap_returns_context_dict(self, db_path: str) -> None:
        result = mcp_mod.clickproof_bootstrap(app_name="myapp")
        assert "context" in result
        assert isinstance(result["context"], str)

    def test_bootstrap_with_version(self, db_path: str) -> None:
        mcp_mod.clickproof_add_fact(
            app_name="myapp",
            app_version="2.0",
            element="btn",
            action="click",
            outcome="ok",
        )
        result = mcp_mod.clickproof_bootstrap(app_name="myapp", app_version="2.0")
        assert "context" in result
