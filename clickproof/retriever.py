"""FactRetriever — retrieves relevant facts for an agent session."""

from __future__ import annotations

from clickproof.fact import UIFact
from clickproof.scorer import FactScore, FactScorer
from clickproof.store import FactStore


class FactRetriever:
    """Retrieves and ranks relevant UIFacts for an agent session start.

    Args:
        store: The FactStore to query.
        scorer: Optional FactScorer; a default one is created if not provided.
    """

    def __init__(self, store: FactStore, scorer: FactScorer | None = None) -> None:
        self._store = store
        self._scorer = scorer or FactScorer()

    def query(
        self,
        app_name: str,
        app_version: str | None = None,
        element: str | None = None,
        min_score: float = 0.5,
    ) -> list[tuple[UIFact, FactScore]]:
        """Return (fact, score) pairs sorted by score descending.

        Args:
            app_name: Required — filter by application name.
            app_version: Optional — filter to a specific version.
            element: Optional — filter to a specific element (substring match).
            min_score: Minimum score threshold; facts below this are excluded.
        """
        facts = self._store.list_facts(app_name=app_name, app_version=app_version)

        if element is not None:
            facts = [f for f in facts if element.lower() in f.element.lower()]

        scored: list[tuple[UIFact, FactScore]] = []
        for fact in facts:
            observations = self._store.get_observations(fact.id)
            fs = self._scorer.score(fact, observations)
            if fs.score >= min_score:
                scored.append((fact, fs))

        scored.sort(key=lambda pair: pair[1].score, reverse=True)
        return scored

    def bootstrap_context(self, app_name: str, app_version: str = "unknown") -> str:
        """Return a text summary of known facts for agent context injection.

        The returned string can be prepended to an agent's system prompt to
        give it a snapshot of what is known about the target application.

        Args:
            app_name: Application to summarize.
            app_version: Optional version to scope the summary.
        """
        pairs = self.query(app_name=app_name, app_version=app_version, min_score=0.0)

        if not pairs:
            return f"No known UI facts for {app_name!r} (version: {app_version!r})."

        lines: list[str] = [
            f"# clickproof: Known UI facts for {app_name!r} (version: {app_version!r})",
            f"# {len(pairs)} fact(s) retrieved, sorted by confidence\n",
        ]

        for fact, score in pairs:
            ctx = f" [{fact.context}]" if fact.context else ""
            lines.append(
                f"- [{score.score:.2f}] {fact.element} --{fact.action}--> {fact.outcome}{ctx}"
            )

        return "\n".join(lines)
