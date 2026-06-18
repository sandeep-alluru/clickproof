"""FactStore — SQLite-backed persistence for UIFacts and FactObservations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from guiproof.fact import FactObservation, UIFact


class FactStore:
    """SQLite-backed store for UIFacts and observations.

    Args:
        path: Path to the SQLite database file. Use ":memory:" for an
              in-memory database (useful for testing).
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ui_facts (
                id          TEXT PRIMARY KEY,
                app_name    TEXT NOT NULL,
                app_version TEXT NOT NULL,
                element     TEXT NOT NULL,
                action      TEXT NOT NULL,
                outcome     TEXT NOT NULL,
                context     TEXT NOT NULL DEFAULT '',
                confidence  REAL NOT NULL DEFAULT 1.0,
                recorded_at REAL NOT NULL,
                extra       TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_facts_app
                ON ui_facts(app_name, app_version);

            CREATE TABLE IF NOT EXISTS fact_observations (
                id           TEXT PRIMARY KEY,
                fact_id      TEXT NOT NULL,
                observed_at  REAL NOT NULL,
                confirmed    INTEGER NOT NULL,
                agent_run_id TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (fact_id) REFERENCES ui_facts(id)
            );

            CREATE INDEX IF NOT EXISTS idx_obs_fact
                ON fact_observations(fact_id);
            """
        )
        self._conn.commit()

    # ── UIFact CRUD ───────────────────────────────────────────────────────────

    def add_fact(self, fact: UIFact) -> None:
        """Insert a UIFact. Silently ignores duplicates (same id)."""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO ui_facts
                (id, app_name, app_version, element, action, outcome,
                 context, confidence, recorded_at, extra)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                fact.recorded_at,
                "{}",
            ),
        )
        self._conn.commit()

    def get_fact(self, fact_id: str) -> UIFact | None:
        """Return a UIFact by id, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM ui_facts WHERE id = ?", (fact_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_fact(row)

    def list_facts(
        self,
        app_name: str | None = None,
        app_version: str | None = None,
    ) -> list[UIFact]:
        """Return all UIFacts, optionally filtered by app_name and/or app_version."""
        query = "SELECT * FROM ui_facts WHERE 1=1"
        params: list[str] = []
        if app_name is not None:
            query += " AND app_name = ?"
            params.append(app_name)
        if app_version is not None:
            query += " AND app_version = ?"
            params.append(app_version)
        query += " ORDER BY recorded_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_fact(r) for r in rows]

    # ── FactObservation CRUD ──────────────────────────────────────────────────

    def add_observation(self, obs: FactObservation) -> None:
        """Insert a FactObservation. Silently ignores duplicates (same id)."""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO fact_observations
                (id, fact_id, observed_at, confirmed, agent_run_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                obs.id,
                obs.fact_id,
                obs.observed_at,
                int(obs.confirmed),
                obs.agent_run_id,
            ),
        )
        self._conn.commit()

    def get_observations(self, fact_id: str) -> list[FactObservation]:
        """Return all observations for a given fact_id, ordered by observed_at."""
        rows = self._conn.execute(
            "SELECT * FROM fact_observations WHERE fact_id = ? ORDER BY observed_at ASC",
            (fact_id,),
        ).fetchall()
        return [self._row_to_obs(r) for r in rows]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> FactStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> UIFact:
        fact = UIFact(
            app_name=row["app_name"],
            app_version=row["app_version"],
            element=row["element"],
            action=row["action"],
            outcome=row["outcome"],
            context=row["context"],
            confidence=row["confidence"],
            recorded_at=row["recorded_at"],
        )
        # Override the auto-computed id with the stored one (should match, but be safe)
        fact.id = row["id"]
        return fact

    @staticmethod
    def _row_to_obs(row: sqlite3.Row) -> FactObservation:
        obs = FactObservation(
            fact_id=row["fact_id"],
            observed_at=row["observed_at"],
            confirmed=bool(row["confirmed"]),
            agent_run_id=row["agent_run_id"],
        )
        obs.id = row["id"]
        return obs
