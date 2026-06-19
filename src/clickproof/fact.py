"""UIFact and FactObservation data models."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class UIFact:
    app_name: str
    app_version: str
    element: str
    action: str
    outcome: str
    context: str = ""
    confidence: float = 1.0
    id: str = field(init=False)

    def __post_init__(self) -> None:
        self.id = _sha16(
            f"{self.app_name}|{self.app_version}|{self.element}|{self.action}|{self.outcome}"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "element": self.element,
            "action": self.action,
            "outcome": self.outcome,
            "context": self.context,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UIFact":
        obj = cls(
            app_name=d["app_name"],
            app_version=d["app_version"],
            element=d["element"],
            action=d["action"],
            outcome=d["outcome"],
            context=d.get("context", ""),
            confidence=d.get("confidence", 1.0),
        )
        return obj


@dataclass
class FactObservation:
    fact_id: str
    observed_at: float
    confirmed: bool
    agent_run_id: str = ""
    id: str = field(init=False)

    def __post_init__(self) -> None:
        self.id = _sha16(f"{self.fact_id}|{self.observed_at}|{self.confirmed}")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "fact_id": self.fact_id,
            "observed_at": self.observed_at,
            "confirmed": self.confirmed,
            "agent_run_id": self.agent_run_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FactObservation":
        obj = cls(
            fact_id=d["fact_id"],
            observed_at=d["observed_at"],
            confirmed=bool(d["confirmed"]),
            agent_run_id=d.get("agent_run_id", ""),
        )
        return obj
