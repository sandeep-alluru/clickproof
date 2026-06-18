# clickproof — Session Anchor

**Research spec:** `../tech-research/07-Computer-and-Browser-Use/meridian-an-open-protocol-for-persistent-cross-session-g/README.md`  
**One-liner:** Continuously-verified, version-pinned GUI behavioral facts for agents — skip re-discovery  
**Phase:** backlog  
**Stack:** Python, playwright, sqlite3 (stdlib), sentence-transformers  

## Key decisions
- Reframed from "crowdsourced OSM" (that framing died) to "freshness-verification pipeline"
- Focus: version-pinned freshness, NOT crowdsourcing
<!-- more decisions as sessions progress -->

## Next step
Read the research spec (especially the dossier reframe section), then design the app-version fingerprinting scheme.

## MVP definition
- `pip install clickproof` works
- Lightweight SDK that instruments Playwright agents to emit UI behavioral observations
- App-version fingerprinting via DOM structure hash
- SQLite-backed local knowledge store
- Query API: `clickproof.get_facts(app, min_confidence=0.8)`
- Demo: second Playwright run queries the store and skips re-discovery of known UI paths
- README with before/after latency comparison
