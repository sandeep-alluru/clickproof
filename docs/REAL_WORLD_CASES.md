# Real-world cases driving clickproof

Mined from farm_memory (Qdrant) and public computer-use research (eagle-eyes Track B).

## Case OVERLAY-CLICK (farm) — CRITICAL

**Source:** Qdrant `farm_memory` failure/rule on **salluru-dev (X.COM Brand)** —
overlay `#layers` intercepts Playwright clicks; eagle-eyes `REAL_WORK_QUEUE` P1.

**What failed:**

1. X compose / article publish: `app-bar-close` and **publish-confirm** clicks
   never land — the overlay div (`#layers`) intercepts them.
2. Using Playwright **`force: true`** hits the overlay and **never throws**, so
   the agent reports success while the UI state is unchanged (draft not published,
   sheet not closed).
3. Stored GUI facts keep high confidence because no **refute** observation is
   written — next session reuses the same broken click path.

**Public twins:**

| Case | Mapping |
|------|---------|
| CUADebug (arXiv 2608.02643) | Diagnose/repair computer-use failures |
| Qwen-CUA (arXiv 2608.02352) | Native computer-use agents |
| Screenshots or Tools? (arXiv 2608.03327) | Multimodal context / tool-use eval |
| Cua / SpongeCake (HN) | Computer-use runtimes need miss signals |

**Product fix in this repo:**

| Control | API |
|---------|-----|
| Click report | `ClickAttempt` (`hit`, `force_used`, `overlay_intercepted`, `observed_effect`) |
| Miss kinds | `overlay_intercept`, `force_silent_no_effect`, `target_miss` |
| Record + decay | `apply_click_outcome(store, attempt)` — refute obs + confidence floor |
| Gate | `gate_click_attempt` — FAIL on miss; PASS only on hit + usable score |
| Store | `FactStore.set_confidence` for hard decay |
| Raise form | `assert_click_ok(...)` |

**Tests:** `tests/test_overlay_click.py`

**Non-Ornament:** Computer-use loops must report `observed_effect` / overlay
intercept after every click (especially when `force=True`) and call
`gate_click_attempt` before trusting the fact again.

---

## Related queue IDs

- **OVERLAY-CLICK** — this case (P1)
- **GUI-MEMORY** — re-discover UI every session (`gate_facts` partial)
