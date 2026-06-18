"""Tests for the FastAPI server."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from guiproof.api import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


class TestHealth:
    def test_health_returns_200(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_status_ok(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.json()["status"] == "ok"

    def test_health_contains_version(self, client: TestClient) -> None:
        r = client.get("/health")
        assert "version" in r.json()


class TestAddFact:
    def test_add_fact_returns_200(self, client: TestClient, db_path: str) -> None:
        r = client.post("/fact", json={
            "app_name": "salesforce", "app_version": "2025.11",
            "element": "export-csv-button", "action": "click",
            "outcome": "opens-download-dialog", "db": db_path,
        })
        assert r.status_code == 200

    def test_add_fact_returns_id(self, client: TestClient, db_path: str) -> None:
        r = client.post("/fact", json={
            "app_name": "app", "app_version": "1.0",
            "element": "btn", "action": "click", "outcome": "ok",
            "db": db_path,
        })
        assert "id" in r.json()
        assert len(r.json()["id"]) == 16

    def test_add_fact_idempotent(self, client: TestClient, db_path: str) -> None:
        payload = {
            "app_name": "app", "app_version": "1.0",
            "element": "btn", "action": "click", "outcome": "ok",
            "db": db_path,
        }
        r1 = client.post("/fact", json=payload)
        r2 = client.post("/fact", json=payload)
        assert r1.json()["id"] == r2.json()["id"]


class TestAddObservation:
    def test_add_observation_returns_200(self, client: TestClient, db_path: str) -> None:
        r = client.post("/fact", json={
            "app_name": "app", "app_version": "1.0",
            "element": "btn", "action": "click", "outcome": "ok",
            "db": db_path,
        })
        fact_id = r.json()["id"]
        r2 = client.post("/observe", json={
            "fact_id": fact_id, "confirmed": True, "db": db_path,
        })
        assert r2.status_code == 200

    def test_add_observation_refuted(self, client: TestClient, db_path: str) -> None:
        r = client.post("/fact", json={
            "app_name": "app", "app_version": "1.0",
            "element": "btn", "action": "click", "outcome": "ok",
            "db": db_path,
        })
        fact_id = r.json()["id"]
        r2 = client.post("/observe", json={
            "fact_id": fact_id, "confirmed": False, "db": db_path,
        })
        assert r2.status_code == 200
        assert r2.json()["confirmed"] is False

    def test_observe_nonexistent_fact_returns_404(
        self, client: TestClient, db_path: str
    ) -> None:
        r = client.post("/observe", json={
            "fact_id": "nonexistent", "confirmed": True, "db": db_path,
        })
        assert r.status_code == 404


class TestQuery:
    def test_query_empty(self, client: TestClient, db_path: str) -> None:
        r = client.get("/query", params={"app_name": "salesforce", "db": db_path})
        assert r.status_code == 200
        assert r.json() == []

    def test_query_returns_facts(self, client: TestClient, db_path: str) -> None:
        client.post("/fact", json={
            "app_name": "salesforce", "app_version": "2025.11",
            "element": "export-csv-button", "action": "click",
            "outcome": "opens-download-dialog", "db": db_path,
        })
        r = client.get("/query", params={
            "app_name": "salesforce", "min_score": 0.0, "db": db_path,
        })
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_query_response_has_fact_and_score(
        self, client: TestClient, db_path: str
    ) -> None:
        client.post("/fact", json={
            "app_name": "app", "app_version": "1.0",
            "element": "btn", "action": "click", "outcome": "ok",
            "db": db_path,
        })
        r = client.get("/query", params={
            "app_name": "app", "min_score": 0.0, "db": db_path,
        })
        item = r.json()[0]
        assert "fact" in item
        assert "score" in item


class TestListFacts:
    def test_list_facts_empty(self, client: TestClient, db_path: str) -> None:
        r = client.get("/facts", params={"db": db_path})
        assert r.status_code == 200
        assert r.json() == []

    def test_list_facts_returns_all(self, client: TestClient, db_path: str) -> None:
        for i in range(3):
            client.post("/fact", json={
                "app_name": "app", "app_version": "1.0",
                "element": f"btn-{i}", "action": "click", "outcome": "ok",
                "db": db_path,
            })
        r = client.get("/facts", params={"db": db_path})
        assert len(r.json()) == 3


class TestBootstrap:
    def test_bootstrap_returns_200(self, client: TestClient, db_path: str) -> None:
        r = client.get("/bootstrap", params={"app_name": "salesforce", "db": db_path})
        assert r.status_code == 200

    def test_bootstrap_contains_context(self, client: TestClient, db_path: str) -> None:
        client.post("/fact", json={
            "app_name": "salesforce", "app_version": "2025.11",
            "element": "export-csv-button", "action": "click",
            "outcome": "opens-download-dialog", "db": db_path,
        })
        r = client.get("/bootstrap", params={
            "app_name": "salesforce", "app_version": "2025.11", "db": db_path,
        })
        assert r.status_code == 200
        data = r.json()
        assert "context" in data
        assert "salesforce" in data["context"]
