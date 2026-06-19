"""Bulk import/export of facts for sharing across deployments."""

from __future__ import annotations

import json

from clickproof.fact import FactObservation, UIFact
from clickproof.retriever import FactRetriever
from clickproof.scorer import FactScorer
from clickproof.store import FactStore


def export_facts(store: FactStore, app_name: str | None = None) -> str:
    """Export facts and observations as JSON.

    Args:
        store: An open FactStore to read from.
        app_name: If given, only export facts for this application.

    Returns:
        JSON string with keys ``version``, ``app_name``, ``facts``, ``count``.
    """
    facts = store.list_facts(app_name=app_name)
    entries = []
    for fact in facts:
        observations = store.get_observations(fact.id)
        entries.append(
            {
                "fact": fact.to_dict(),
                "observations": [obs.to_dict() for obs in observations],
            }
        )
    payload = {
        "version": "1.0",
        "app_name": app_name or "all",
        "facts": entries,
        "count": len(entries),
    }
    return json.dumps(payload, indent=2)


def import_facts(
    store: FactStore,
    json_str: str,
    merge_strategy: str = "upsert",
) -> int:
    """Import facts from JSON.

    Args:
        store: An open FactStore to write into.
        json_str: JSON string produced by :func:`export_facts`.
        merge_strategy: One of ``"upsert"``, ``"skip_existing"``, or
            ``"overwrite"``.  ``"upsert"`` and ``"overwrite"`` both call
            :meth:`FactStore.add_fact` (which is itself an upsert).
            ``"skip_existing"`` skips facts whose id is already in the store.

    Returns:
        Number of facts imported (observations are always imported alongside).

    Raises:
        ValueError: If *merge_strategy* is not a recognised value.
    """
    if merge_strategy not in {"upsert", "skip_existing", "overwrite"}:
        raise ValueError(
            f"Unknown merge_strategy {merge_strategy!r}. "
            "Choose 'upsert', 'skip_existing', or 'overwrite'."
        )

    data = json.loads(json_str)
    imported = 0

    for entry in data.get("facts", []):
        fact = UIFact.from_dict(entry["fact"])

        if merge_strategy == "skip_existing" and store.get_fact(fact.id) is not None:
            continue

        store.add_fact(fact)
        imported += 1

        for obs_dict in entry.get("observations", []):
            obs = FactObservation.from_dict(obs_dict)
            store.add_observation(obs)

    return imported


def export_bootstrap_pack(store: FactStore, app_name: str) -> str:
    """Export a 'bootstrap pack' — minimal JSON with top-scored facts for an app.

    Only facts with a score >= 0.5 are included, sorted by score descending,
    capped at the top 20.

    Args:
        store: An open FactStore to read from.
        app_name: Application whose facts to export.

    Returns:
        JSON string with keys ``version``, ``app_name``, ``bootstrap_pack``,
        ``facts``, ``count``.
    """
    scorer = FactScorer()
    retriever = FactRetriever(store, scorer)
    pairs = retriever.query(app_name=app_name, min_score=0.5)
    top = pairs[:20]

    payload = {
        "version": "1.0",
        "app_name": app_name,
        "bootstrap_pack": True,
        "facts": [fact.to_dict() for fact, _score in top],
        "count": len(top),
    }
    return json.dumps(payload, indent=2)
