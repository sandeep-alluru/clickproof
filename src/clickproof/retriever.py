"""FactRetriever — queries the store, scores facts, and builds agent context."""
from __future__ import annotations

from typing import Optional

from clickproof.fact import UIFact
from clickproof.scorer import FactScore, FactScorer
from clickproof.store import FactStore


class FactRetriever:
    def __init__(self, store: FactStore, scorer: FactScorer) -> None:
        self._store = store
        self._scorer = scorer

    def query(
        self,
        app_name: str,
        app_version: Optional[str] = None,
        min_score: float = 0.5,
    ) -> list[tuple[UIFact, FactScore]]:
        """Return (fact, score) pairs for *app_name*, filtered and sorted by score."""
        facts = self._store.list_facts(app_name=app_name)

        if app_version is not None:
            facts = [f for f in facts if f.app_version == app_version]

        results: list[tuple[UIFact, FactScore]] = []
        for fact in facts:
            obs = self._store.list_observations(fact.id)
            score = self._scorer.score(fact, obs)
            if score.score >= min_score:
                results.append((fact, score))

        results.sort(key=lambda pair: pair[1].score, reverse=True)
        return results

    def bootstrap_context(
        self,
        app_name: str,
        app_version: Optional[str] = None,
    ) -> str:
        """Return a markdown text block suitable for injection into an agent system prompt."""
        pairs = self.query(app_name=app_name, app_version=app_version, min_score=0.0)

        version_str = app_version if app_version else "all versions"
        lines: list[str] = [
            f"## Known UI facts for {app_name} {version_str}",
            "",
            "| Score | Element | Action | Outcome | Confirmed/Total |",
            "|-------|---------|--------|---------|-----------------|",
        ]
        for fact, score in pairs:
            lines.append(
                f"| {score.score:.3f} | {fact.element} | {fact.action} "
                f"| {fact.outcome} | {score.confirmed_count}/{score.observation_count} |"
            )

        if not pairs:
            lines.append("| — | No facts recorded yet | — | — | — |")

        return "\n".join(lines)
