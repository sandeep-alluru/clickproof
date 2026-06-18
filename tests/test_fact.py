"""Tests for UIFact and FactObservation data models."""

from __future__ import annotations

import time

from guiproof.fact import FactObservation, UIFact


class TestUIFact:
    """Tests for UIFact content-addressing and serialization."""

    def test_id_is_content_addressed(self) -> None:
        f1 = UIFact(
            app_name="salesforce", app_version="2025.11",
            element="export-csv-button", action="click", outcome="opens-download-dialog",
        )
        f2 = UIFact(
            app_name="salesforce", app_version="2025.11",
            element="export-csv-button", action="click", outcome="opens-download-dialog",
        )
        assert f1.id == f2.id

    def test_id_differs_for_different_element(self) -> None:
        f1 = UIFact(app_name="app", app_version="1.0",
                    element="btn-a", action="click", outcome="ok")
        f2 = UIFact(app_name="app", app_version="1.0",
                    element="btn-b", action="click", outcome="ok")
        assert f1.id != f2.id

    def test_id_differs_for_different_action(self) -> None:
        f1 = UIFact(app_name="app", app_version="1.0",
                    element="btn", action="click", outcome="ok")
        f2 = UIFact(app_name="app", app_version="1.0",
                    element="btn", action="hover", outcome="ok")
        assert f1.id != f2.id

    def test_id_differs_for_different_version(self) -> None:
        f1 = UIFact(app_name="app", app_version="1.0",
                    element="btn", action="click", outcome="ok")
        f2 = UIFact(app_name="app", app_version="2.0",
                    element="btn", action="click", outcome="ok")
        assert f1.id != f2.id

    def test_outcome_does_not_affect_id(self) -> None:
        """ID is based on app_name|app_version|element|action only."""
        f1 = UIFact(app_name="app", app_version="1.0",
                    element="btn", action="click", outcome="opens-dialog")
        f2 = UIFact(app_name="app", app_version="1.0",
                    element="btn", action="click", outcome="error:not-found")
        assert f1.id == f2.id

    def test_id_is_16_hex_chars(self) -> None:
        f = UIFact(app_name="app", app_version="1.0",
                   element="btn", action="click", outcome="ok")
        assert len(f.id) == 16
        assert all(c in "0123456789abcdef" for c in f.id)

    def test_to_dict_contains_all_fields(self) -> None:
        f = UIFact(
            app_name="gmail", app_version="unknown",
            element="compose-button", action="click", outcome="opens-compose-window",
            context="inbox", confidence=0.8,
        )
        d = f.to_dict()
        assert d["app_name"] == "gmail"
        assert d["app_version"] == "unknown"
        assert d["element"] == "compose-button"
        assert d["action"] == "click"
        assert d["outcome"] == "opens-compose-window"
        assert d["context"] == "inbox"
        assert d["confidence"] == 0.8
        assert "id" in d
        assert "recorded_at" in d

    def test_from_dict_round_trip(self) -> None:
        f = UIFact(
            app_name="gmail", app_version="2025.06",
            element="send-button", action="click", outcome="sends-email",
            confidence=0.95,
        )
        d = f.to_dict()
        f2 = UIFact.from_dict(d)
        assert f2.id == f.id
        assert f2.app_name == f.app_name
        assert f2.outcome == f.outcome
        assert f2.confidence == f.confidence

    def test_default_confidence_is_one(self) -> None:
        f = UIFact(app_name="app", app_version="1.0",
                   element="btn", action="click", outcome="ok")
        assert f.confidence == 1.0

    def test_default_context_is_empty(self) -> None:
        f = UIFact(app_name="app", app_version="1.0",
                   element="btn", action="click", outcome="ok")
        assert f.context == ""

    def test_repr_contains_key_info(self) -> None:
        f = UIFact(app_name="app", app_version="1.0",
                   element="btn", action="click", outcome="ok")
        r = repr(f)
        assert "app" in r
        assert "btn" in r

    def test_recorded_at_is_recent(self) -> None:
        before = time.time()
        f = UIFact(app_name="app", app_version="1.0",
                   element="btn", action="click", outcome="ok")
        after = time.time()
        assert before <= f.recorded_at <= after


class TestFactObservation:
    """Tests for FactObservation content-addressing and serialization."""

    def test_id_is_content_addressed(self) -> None:
        obs1 = FactObservation(fact_id="abc", observed_at=1000.0, confirmed=True)
        obs2 = FactObservation(fact_id="abc", observed_at=1000.0, confirmed=True)
        assert obs1.id == obs2.id

    def test_id_differs_for_different_confirmed(self) -> None:
        obs1 = FactObservation(fact_id="abc", observed_at=1000.0, confirmed=True)
        obs2 = FactObservation(fact_id="abc", observed_at=1000.0, confirmed=False)
        assert obs1.id != obs2.id

    def test_id_differs_for_different_fact(self) -> None:
        obs1 = FactObservation(fact_id="abc", observed_at=1000.0, confirmed=True)
        obs2 = FactObservation(fact_id="xyz", observed_at=1000.0, confirmed=True)
        assert obs1.id != obs2.id

    def test_to_dict_contains_all_fields(self) -> None:
        obs = FactObservation(fact_id="abc123", observed_at=1700000000.0,
                              confirmed=True, agent_run_id="run_001")
        d = obs.to_dict()
        assert d["fact_id"] == "abc123"
        assert d["confirmed"] is True
        assert d["agent_run_id"] == "run_001"
        assert "id" in d
        assert "observed_at" in d

    def test_from_dict_round_trip(self) -> None:
        obs = FactObservation(fact_id="abc123", observed_at=1700000000.0,
                              confirmed=False, agent_run_id="run_002")
        d = obs.to_dict()
        obs2 = FactObservation.from_dict(d)
        assert obs2.id == obs.id
        assert obs2.confirmed is False
        assert obs2.agent_run_id == "run_002"

    def test_default_agent_run_id_is_empty(self) -> None:
        obs = FactObservation(fact_id="abc", observed_at=1000.0, confirmed=True)
        assert obs.agent_run_id == ""

    def test_repr_contains_status(self) -> None:
        obs = FactObservation(fact_id="abc", observed_at=1000.0, confirmed=True)
        assert "confirmed" in repr(obs)
        obs2 = FactObservation(fact_id="abc", observed_at=1000.0, confirmed=False)
        assert "refuted" in repr(obs2)
