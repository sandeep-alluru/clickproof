"""SQLite-backed FactStore — persistent storage for UIFacts and FactObservations."""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from clickproof.fact import FactObservation, UIFact

_DDL = """
CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    app_name TEXT NOT NULL,
    app_version TEXT NOT NULL,
    element TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 1.0,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    fact_id TEXT NOT NULL,
    observed_at REAL NOT NULL,
    confirmed INTEGER NOT NULL,
    agent_run_id TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL
);
"""


class FactStore:
    """Context-manager-aware SQLite store for clickproof facts and observations."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "FactStore":
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._conn.commit()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("FactStore is not open — use it as a context manager")
        return self._conn

    # ------------------------------------------------------------------
    # Facts
    # ------------------------------------------------------------------

    def add_fact(self, fact: UIFact) -> None:
        """Upsert a UIFact by its id."""
        self._db.execute(
            """
            INSERT INTO facts (id, app_name, app_version, element, action, outcome, context, confidence, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                app_name    = excluded.app_name,
                app_version = excluded.app_version,
                element     = excluded.element,
                action      = excluded.action,
                outcome     = excluded.outcome,
                context     = excluded.context,
                confidence  = excluded.confidence,
                data        = excluded.data
            """,
            (
                fact.id,
                fact.app_name,
                fact.app_version,
                fact.element,
                fact.action,
                fact.outcome,
                fact.context,
                fact.confidence,
                json.dumps(fact.to_dict()),
            ),
        )
        self._db.commit()

    def get_fact(self, fact_id: str) -> Optional[UIFact]:
        row = self._db.execute(
            "SELECT data FROM facts WHERE id = ?", (fact_id,)
        ).fetchone()
        if row is None:
            return None
        return UIFact.from_dict(json.loads(row["data"]))

    def list_facts(self, app_name: Optional[str] = None) -> list[UIFact]:
        if app_name is None:
            rows = self._db.execute("SELECT data FROM facts").fetchall()
        else:
            rows = self._db.execute(
                "SELECT data FROM facts WHERE app_name = ?", (app_name,)
            ).fetchall()
        return [UIFact.from_dict(json.loads(r["data"])) for r in rows]

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------

    def add_observation(self, obs: FactObservation) -> None:
        """Insert an observation (observations are append-only)."""
        self._db.execute(
            """
            INSERT OR IGNORE INTO observations
                (id, fact_id, observed_at, confirmed, agent_run_id, data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                obs.id,
                obs.fact_id,
                obs.observed_at,
                int(obs.confirmed),
                obs.agent_run_id,
                json.dumps(obs.to_dict()),
            ),
        )
        self._db.commit()

    def list_observations(self, fact_id: str) -> list[FactObservation]:
        rows = self._db.execute(
            "SELECT data FROM observations WHERE fact_id = ? ORDER BY observed_at",
            (fact_id,),
        ).fetchall()
        return [FactObservation.from_dict(json.loads(r["data"])) for r in rows]
