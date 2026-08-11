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

---

## Case CVE / GeoReward — contextual variable overestimation (arXiv 2608.04504)

**Source:** Track B research (`20260809T041233Z`) —
[GeoReward: Mitigating Contextual Variable Overestimation](https://arxiv.org/abs/2608.04504).

**What fails:**

1. Multimodal / CUA agents overestimate dominant visual-textual cues (product,
   dense image patches) and **ignore sparse** market/region/locale variables.
2. Choices **collapse** to the same output across distinct geographic contexts.
3. Hit/miss click gates and task allowlists do not check context attendance.

**Product in this repo:**

| Control | API |
|---------|-----|
| Decision type | `ContextDecision` |
| Analysis | `analyze_cve` → `CVEReport` |
| Key helpers | `is_sparse_context_key`, `context_fingerprint` |
| Gate | `gate_context_variables(...)` |
| Raise form | `assert_context_variables_ok` |

**Rules (load-bearing):**

- Empty decision / missing required sparse keys → **FAIL_LOUD**
- Sparse present but not attended / dominant-only → **FAIL**
- Cross-context collapse (same choice across markets) → **FAIL**
- Sparse attended, distinct per-context choices → **PASS**

**Tests:** `tests/test_context_vars.py`

**Non-Ornament:** Call `gate_context_variables` before accepting market/locale-
sensitive creatives or GUI paths. Pair with `gate_click_attempt` and
`gate_task_alignment`.

---

## Case STEPJACK — multi-step indirect prompt injection (arXiv 2608.06477)

**Source:** Track B research (`20260810T041230Z`) —
[StepJack: Benchmarking Computer-Use Agent Safety Against Multi-Step Indirect
Prompt Injection](https://arxiv.org/abs/2608.06477v1).

**What fails:**

1. Adversarial goals are **decomposed** into innocuous-looking sub-steps and
   planted across a **chain of pages** on the CUA navigation path.
2. Single-step `gate_task_alignment` (INVISIBLE-INK) only sees one action —
   cumulative copy→paste, off-domain hops, and page-planted phrases slip through.
3. Agents claim task-complete after a multi-page trajectory that embeds injection.

**Product in this repo:**

| Control | API |
|---------|-----|
| Step type | `NavStep` |
| Analysis | `analyze_multi_step_chain` → `StepJackReport` |
| Phrase / host helpers | `detect_injection_phrases`, `hosts_from_task` |
| Gate | `gate_multi_step_chain(steps, task, …)` |
| Raise form | `assert_multi_step_ok` |

**Rules (load-bearing):**

- empty task / claim complete with zero steps → **FAIL_LOUD**
- high-risk step not in task allowlist → **FAIL**
- injection phrases in page snippets → **FAIL**
- off-domain hosts outside task/allowlist → **FAIL**
- cumulative soft patterns (copy→paste, fill→submit, …) → **FAIL**
- optional `max_decomposition_depth` exceed → **FAIL**
- clean in-domain chain → **PASS**

**Tests:** `tests/test_stepjack.py`

**Non-Ornament:** Call `gate_multi_step_chain` on multi-page CUA trajectories
before accepting task-complete. Pair with per-step `gate_task_alignment` and
`gate_click_attempt`.

---

## Case SYNCHAIN — self-synthesized poisoned artifacts (arXiv 2608.06862)

**Source:** Track B research backlog (`20260810T161237Z` / prior; session
`20260811T001239Z` hit arxiv_error) —
[SynChain: Inducing Computer-Use Agent Systems to Construct Their Own Attack
Chains](https://arxiv.org/abs/2608.06862v1).

**What fails:**

1. CUAs persist **skills** and **memory** entries across sessions.
2. Malicious influence is embedded in **auto-synthesized** artifacts that look
   benign, survive state updates, and skip one-shot vetting.
3. STEPJACK/INVISIBLE-INK gate live steps; they do not gate **loaded artifact**
   integrity before reuse.

**Product in this repo:**

| Control | API |
|---------|-----|
| Artifact type | `PersistentArtifact` |
| Fingerprint | `artifact_content_fingerprint` |
| Analysis | `analyze_artifact_integrity` → `ArtifactIntegrityReport` |
| Gate | `gate_artifact_integrity(...)` |
| Raise form | `assert_artifacts_ok` |

**Rules (load-bearing):**

- claim loaded + empty inventory → **FAIL_LOUD**
- auto-synthesized without `vetted` → **FAIL**
- content fingerprint mismatch → **FAIL**
- injection/poison phrases in body → **FAIL**
- high-risk templates in unvetted/benign-wrapped skills → **FAIL**
- vetted clean artifacts → **PASS**

**Tests:** `tests/test_synchain.py`

**Non-Ornament:** Call `gate_artifact_integrity` before loading skill/memory
into a CUA session. Pair with `gate_session_memory` and `gate_multi_step_chain`.

## Related queue IDs

- **OVERLAY-CLICK** — force/overlay miss invalidation (P1)
- **GUI-MEMORY** — session bootstrap (P1)
- **INVISIBLE-INK** — single-step task alignment (P1)
- **CVE** — contextual variable overestimation
- **STEPJACK** — multi-step injection chain
- **SYNCHAIN** — persistent artifact poison (this section)
