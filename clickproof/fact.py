"""UIFact and FactObservation data models — the content-addressed primitives of clickproof."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


def _sha16(text: str) -> str:
    """Return the first 16 hex chars of SHA-256(text)."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class UIFact:
    """A behavioral fact about a UI element in a specific app version.

    UIFacts are the atoms of clickproof. Two UIFacts with the same app_name,
    app_version, element, and action always have the same ID.

    Attributes:
        app_name: Application identifier, e.g. "salesforce", "gmail".
        app_version: Version string, e.g. "2025.11", "unknown".
        element: Semantic element description, e.g. "export-csv-button".
        action: What to do: "click", "type", "navigate".
        outcome: What happens: "opens-download-dialog", "error:not-found".
        context: Optional UI context, e.g. "reports-page".
        confidence: Initial confidence in [0.0, 1.0]. Default 1.0.
        recorded_at: Unix timestamp when this fact was recorded.
        id: Content-addressed identifier — SHA-256[:16] of
            "{app_name}|{app_version}|{element}|{action}".
    """

    app_name: str
    app_version: str
    element: str
    action: str
    outcome: str
    context: str = ""
    confidence: float = 1.0
    recorded_at: float = field(default_factory=time.time)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        self.id = _sha16(f"{self.app_name}|{self.app_version}|{self.element}|{self.action}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "element": self.element,
            "action": self.action,
            "outcome": self.outcome,
            "context": self.context,
            "confidence": self.confidence,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> UIFact:
        """Deserialize from a dict produced by to_dict()."""
        fact = cls(
            app_name=d["app_name"],
            app_version=d["app_version"],
            element=d["element"],
            action=d["action"],
            outcome=d["outcome"],
            context=d.get("context", ""),
            confidence=d.get("confidence", 1.0),
            recorded_at=d.get("recorded_at", 0.0),
        )
        return fact

    def __repr__(self) -> str:
        return (
            f"UIFact({self.id!r}: {self.app_name!r} v{self.app_version!r}"
            f" {self.element!r} --{self.action}--> {self.outcome!r})"
        )


@dataclass
class FactObservation:
    """An observation that confirms or refutes a UIFact.

    Attributes:
        fact_id: ID of the UIFact this observation pertains to.
        observed_at: Unix timestamp when this observation was made.
        confirmed: True = fact still holds; False = fact no longer holds.
        agent_run_id: Optional tracing identifier.
        id: Content-addressed identifier — SHA-256[:16] of
            "{fact_id}|{observed_at}|{confirmed}".
    """

    fact_id: str
    observed_at: float
    confirmed: bool
    agent_run_id: str = ""
    id: str = field(init=False)

    def __post_init__(self) -> None:
        self.id = _sha16(f"{self.fact_id}|{self.observed_at}|{self.confirmed}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "fact_id": self.fact_id,
            "observed_at": self.observed_at,
            "confirmed": self.confirmed,
            "agent_run_id": self.agent_run_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FactObservation:
        """Deserialize from a dict produced by to_dict()."""
        obs = cls(
            fact_id=d["fact_id"],
            observed_at=d["observed_at"],
            confirmed=d["confirmed"],
            agent_run_id=d.get("agent_run_id", ""),
        )
        return obs

    def __repr__(self) -> str:
        status = "confirmed" if self.confirmed else "refuted"
        return f"FactObservation({self.id!r}: fact={self.fact_id!r} {status})"
