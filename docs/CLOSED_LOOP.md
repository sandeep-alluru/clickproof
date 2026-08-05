# Closed loop — `clickproof`

**Status:** wired (eagle-eyes / 2026-08-05)  
**Owner loop:** L3 computer-use only

## Load-bearing job

Content-addressed GUI behavioral facts for computer-use

## Reader (implemented)

```python
from clickproof import gate_facts, assert_usable_facts, gate_click_attempt, ClickAttempt

# Empty store / list → FAIL_LOUD (exit 2)
# facts present but none usable above min_score → FAIL (exit 1)
# usable facts → PASS (exit 0)
out = gate_facts(path_or_store_or_list, min_score=0.5)
assert_usable_facts([...])  # raises ClosedLoopError unless ok

# OVERLAY-CLICK: force/overlay miss invalidates fact confidence
out = gate_click_attempt(store, ClickAttempt(
    fact_id=f.id, target_element=f.element,
    hit=False, force_used=True, overlay_intercepted=True,
))
```

Module: `clickproof.closed_loop` · API: `gate_facts`, `gate_click_attempt`,
`apply_click_outcome`, `ClickAttempt`

## Who reads the output?

Computer-use agent / CI / eagle-eyes before trusting GUI facts for action selection

## What outcome changes?

Block on empty fact DB; block or warn when all scores are below min_score (decay)

## When NOT to use (anti-ornament)

Never treat an empty fact store as silent PASS / "no constraints"

## Non-Ornament checklist

- [x] Reader implemented in library (`closed_loop.gate_facts`)
- [x] Empty/wrong output fails loudly (exit 2)
- [x] Not exposed as free MCP in product agents
- [ ] Linked gap IDs in mem0 when improving
- [ ] eagle-eyes dogfood exercises `gate_facts` (optional next)

## Related failures (farm memory)

- 2026-07-22 MCP buffet trim: write-only tools removed from Foundry framework
- D-FOGHORN: misuse of append-only fact log as current state
- Dual-path mem0: never rely on MCP-only for critical memory

## Daily rotation note

Prefer small daily commits that keep the gate covered and used by readers.

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2
