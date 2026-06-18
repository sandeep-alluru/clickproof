"""FastAPI REST wrapper for clickproof.

Start:   uvicorn clickproof.api:app --reload
Install: pip install "clickproof[api]"
Docs:    http://localhost:8000/docs
"""

from __future__ import annotations

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
except ImportError as exc:
    raise ImportError(
        "API server requires: pip install 'clickproof[api]'"
    ) from exc

app = FastAPI(
    title="clickproof API",
    description="Persistent GUI behavioral facts for computer-use agents",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health() -> dict[str, str]:
    """Liveness probe."""
    from clickproof import __version__
    return {"status": "ok", "version": __version__}


# TODO: add your endpoints here following the openapi.yaml spec
