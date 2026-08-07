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

## Case GUI-MEMORY (farm) — MAJOR

**Source:** eagle-eyes `REAL_WORK_QUEUE` P1 — *re-discover UI every session*;
related to long-horizon computer-use agents (public ABSeeker / hierarchical
graph memory papers, Track B).

**What failed:**

Computer-use agents start each session **cold**: they ignore the durable
fact store and re-probe the same buttons/flows. `gate_facts` alone only
checks that the store is non-empty — it does not require the **session**
to *load* those facts into agent context.

**Product fix in this repo:**

| Control | API |
|---------|-----|
| Session load | `load_session_memory(store, app_name)` → `SessionMemory` |
| Usable count | `store_usable_count(store, app_name)` |
| Gate | `gate_session_memory(store, session, app_name=...)` |
| Skip load + known facts | **FAIL** (re-discover trap) |
| Empty store for app | **FAIL_LOUD** |
| Raise form | `assert_session_bootstrapped(...)` |

**Tests:** `tests/test_gui_memory.py`

**Non-Ornament:** Call `load_session_memory` at session start and
`gate_session_memory` before acting. Bootstrap text belongs in the agent
prompt (`SessionMemory.bootstrap_text`).

---

## Case INVISIBLE-INK — adversarial goals behind legitimate CUA tasks

**Source:** Track B research (`20260807T161233Z`):

| Case | Link / note |
|------|-------------|
| Invisible Ink Threats | arXiv 2608.02018 — adversarial goals behind legitimate tasks |
| Qwen-CUA / Screenshots or Tools? | computer-use agent eval (same session) |
| Cua / SpongeCake (HN) | computer-use runtimes |

**What fails:**

1. User task is benign (“close the cookie banner”).
2. UI injection or model drift proposes **delete / export / auth / transfer**.
3. Overlay/GUI gates only check *whether the click hit* — not whether the
   action is **in scope** of the declared task.

**Product in this repo:**

| Control | API |
|---------|-----|
| Risk classifier | `is_high_risk_cua_action` / `DEFAULT_HIGH_RISK_CUA_ACTIONS` |
| Task allowlist | `infer_allowlist_from_task` + explicit `allowed_actions` |
| Pre-exec gate | `gate_task_alignment(task, action, …)` |
| Target scope | `allowed_targets` for UI injection detours |
| Raise form | `assert_task_aligned(...)` |

**Rules (load-bearing):**

- Empty task/action → **FAIL_LOUD**
- High-risk action outside allowlist → **FAIL** (`human_required`)
- Action outside allowlist → **FAIL**
- Target outside `allowed_targets` → **FAIL**

**Tests:** `tests/test_invisible_ink.py`

**Non-Ornament:** Call `gate_task_alignment` **before** every high-risk CUA
tool/click. Pair with `gate_click_attempt` (hit/miss) and
`humanproof.gate_approval` for owner tokens. Hit success alone is not intent
alignment.

## Related queue IDs

- **OVERLAY-CLICK** — force/overlay miss invalidation (P1)
- **GUI-MEMORY** — this case (P1)
