"""Tests for bulk import/export functionality."""

from __future__ import annotations

import json
import time

import pytest

from clickproof.bulk import export_bootstrap_pack, export_facts, import_facts
from clickproof.fact import FactObservation, UIFact
from clickproof.store import FactStore


def make_fact(app_name: str = "myapp", app_version: str = "1.0") -> UIFact:
    return UIFact(
        app_name=app_name,
        app_version=app_version,
        element="save-button",
        action="click",
        outcome="saves-document",
        context="editor",
        confidence=0.9,
    )


def make_obs(fact: UIFact, confirmed: bool = True) -> FactObservation:
    return FactObservation(
        fact_id=fact.id,
        observed_at=time.time(),
        confirmed=confirmed,
        agent_run_id="run-test",
    )


class TestExportFacts:
    def test_export_returns_valid_json(self) -> None:
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            result = export_facts(store)

        data = json.loads(result)
        assert data["version"] == "1.0"
        assert data["app_name"] == "all"
        assert data["count"] == 1
        assert len(data["facts"]) == 1
        assert data["facts"][0]["fact"]["id"] == fact.id

    def test_export_includes_observations(self) -> None:
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            obs = make_obs(fact)
            store.add_observation(obs)
            result = export_facts(store)

        data = json.loads(result)
        entry = data["facts"][0]
        assert len(entry["observations"]) == 1
        assert entry["observations"][0]["id"] == obs.id

    def test_export_empty_store(self) -> None:
        with FactStore(":memory:") as store:
            result = export_facts(store)

        data = json.loads(result)
        assert data["count"] == 0
        assert data["facts"] == []

    def test_export_filtered_by_app_name(self) -> None:
        with FactStore(":memory:") as store:
            fact_a = make_fact(app_name="alpha")
            fact_b = UIFact(
                app_name="beta",
                app_version="2.0",
                element="btn",
                action="click",
                outcome="ok",
            )
            store.add_fact(fact_a)
            store.add_fact(fact_b)
            result = export_facts(store, app_name="alpha")

        data = json.loads(result)
        assert data["app_name"] == "alpha"
        assert data["count"] == 1
        assert data["facts"][0]["fact"]["app_name"] == "alpha"

    def test_export_app_name_in_payload(self) -> None:
        with FactStore(":memory:") as store:
            result = export_facts(store, app_name="testapp")

        data = json.loads(result)
        assert data["app_name"] == "testapp"


class TestImportFacts:
    def test_import_upsert_imports_facts(self) -> None:
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            exported = export_facts(store)

        with FactStore(":memory:") as store2:
            count = import_facts(store2, exported)
            facts = store2.list_facts()

        assert count == 1
        assert len(facts) == 1
        assert facts[0].id == fact.id

    def test_import_also_imports_observations(self) -> None:
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            obs = make_obs(fact)
            store.add_observation(obs)
            exported = export_facts(store)

        with FactStore(":memory:") as store2:
            import_facts(store2, exported)
            obs_list = store2.get_observations(fact.id)

        assert len(obs_list) == 1
        assert obs_list[0].id == obs.id

    def test_import_skip_existing_skips_already_present(self) -> None:
        fact = make_fact()
        with FactStore(":memory:") as store:
            store.add_fact(fact)
            exported = export_facts(store)

        # Import into a store that already has the fact
        with FactStore(":memory:") as store2:
            store2.add_fact(fact)
            count = import_facts(store2, exported, merge_strategy="skip_existing")

        assert count == 0

    def test_import_skip_existing_imports_new_facts(self) -> None:
        fact_a = make_fact(app_name="alpha")
        fact_b = UIFact(
            app_name="beta",
            app_version="1.0",
            element="btn",
            action="click",
            outcome="ok",
        )
        with FactStore(":memory:") as store:
            store.add_fact(fact_a)
            store.add_fact(fact_b)
            exported = export_facts(store)

        with FactStore(":memory:") as store2:
            # Pre-seed only fact_a
            store2.add_fact(fact_a)
            count = import_facts(store2, exported, merge_strategy="skip_existing")

        # Only fact_b should have been imported
        assert count == 1

    def test_import_overwrite_strategy(self) -> None:
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            exported = export_facts(store)

        with FactStore(":memory:") as store2:
            count = import_facts(store2, exported, merge_strategy="overwrite")

        assert count == 1

    def test_import_unknown_strategy_raises(self) -> None:
        with FactStore(":memory:") as store:
            exported = export_facts(store)

        with FactStore(":memory:") as store2, pytest.raises(ValueError, match="merge_strategy"):
            import_facts(store2, exported, merge_strategy="bogus")

    def test_import_returns_count(self) -> None:
        with FactStore(":memory:") as store:
            for i in range(3):
                f = UIFact(
                    app_name="app",
                    app_version="1.0",
                    element=f"btn-{i}",
                    action="click",
                    outcome="ok",
                )
                store.add_fact(f)
            exported = export_facts(store)

        with FactStore(":memory:") as store2:
            count = import_facts(store2, exported)

        assert count == 3


class TestExportBootstrapPack:
    def test_bootstrap_pack_valid_json(self) -> None:
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            obs = make_obs(fact, confirmed=True)
            store.add_observation(obs)
            # Second observation to boost score above 0.5
            obs2 = make_obs(fact, confirmed=True)
            store.add_observation(obs2)
            result = export_bootstrap_pack(store, app_name="myapp")

        data = json.loads(result)
        assert data["version"] == "1.0"
        assert data["app_name"] == "myapp"
        assert data["bootstrap_pack"] is True
        assert "facts" in data
        assert "count" in data

    def test_bootstrap_pack_no_observations_included(self) -> None:
        with FactStore(":memory:") as store:
            fact = make_fact()
            store.add_fact(fact)
            obs = make_obs(fact, confirmed=True)
            store.add_observation(obs)
            obs2 = make_obs(fact, confirmed=True)
            store.add_observation(obs2)
            result = export_bootstrap_pack(store, app_name="myapp")

        data = json.loads(result)
        # Bootstrap pack entries are UIFact dicts (no 'observations' key)
        for entry in data["facts"]:
            assert "observations" not in entry
            # It's a flat fact dict
            assert "app_name" in entry

    def test_bootstrap_pack_empty_store(self) -> None:
        with FactStore(":memory:") as store:
            result = export_bootstrap_pack(store, app_name="myapp")

        data = json.loads(result)
        assert data["count"] == 0
        assert data["facts"] == []

    def test_bootstrap_pack_excludes_low_score_facts(self) -> None:
        """A fact with no observations has score < 0.5 after enough time — but a brand-new
        fact with confidence=1.0 and recorded_at=now scores near 1.0, so let's use
        a fact with 0 observations recorded long ago."""
        now = time.time()
        old_recorded = now - (86400 * 60)  # 60 days ago
        with FactStore(":memory:") as store:
            # Insert a fact directly so we can control recorded_at
            fact = UIFact(
                app_name="myapp",
                app_version="1.0",
                element="old-btn",
                action="click",
                outcome="ok",
                recorded_at=old_recorded,
            )
            store.add_fact(fact)
            result = export_bootstrap_pack(store, app_name="myapp")

        data = json.loads(result)
        # A 60-day-old fact with no observations should score below 0.5
        assert data["count"] == 0
