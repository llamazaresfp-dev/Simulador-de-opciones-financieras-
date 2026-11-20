---
phase: etapa-a-montecarlo-iv-closeout
date: 2026-11-20
status: COMPLETE
feature: none (general-plans)
plan: process/general-plans/completed/etapa-a-montecarlo-iv_20-11-26/etapa-a-montecarlo-iv_PLAN_20-11-26.md
---

# Phase report: Etapa A, Monte Carlo + volatilidad implícita (UPDATE PROCESS)

TL;DR: all blocks (1, 2, 3a, 3b, 4a, 4b) verified, AC-A1..AC-A17 met, 910/910 tests, smoke 29/29, user manual 11-item checklist passed ("Todo bien"). Classification: CLEAN, ready for archival. Plan archived to `completed/`.

### What Was Done
- New engine modules `opciones/implied_vol.py` and `opciones/simulation.py`; `validate_simulation` and `scenario_warnings` in `opciones/validation.py`; public API additions in `opciones/__init__.py`; `app.py` gained the "Escenarios (Monte Carlo)" expander, the per-leg IV button and Ajustes "Simulación"; new `tests/test_implied_vol.py` and `tests/test_simulation.py`.
- Commits: SPEC+plan f94f9b0; block 1 IV d7606f2 (651 tests); block 2 exact PoP 55bdeea (686); block 3a Monte Carlo d46eddb (836); block 3b validation/warnings/exports 9853668 (887); block 4a scenarios UI 9689b02 (900); block 4b IV UI + EVL fix f154272 (910).
- Each block confirmed by an independent vc-tester EVL run and approved by the user. PVL: first-pass Gate PASS with binding amendments A1-A8 (A7 split blocks 3 and 4 into 3a/3b and 4a/4b).
- UPDATE PROCESS: plan closed (status, checkboxes, Current Execution State, Lessons), iron condor reference corrected, `all-context.md` and `tests/all-tests.md` refreshed, task folder archived.

### What Was Skipped/Deferred
- Rational close fee at expiry stays in backlog (`process/general-plans/backlog/close-fee-rational-close_20-11-26.md`).
- Stage B (binomial model for American options): future plan per roadmap.

### Test Gate Outcomes
- `.venv/bin/pytest -q`: 910 passed (EVL final, block 4b). `.venv/bin/pytest tests/test_app_smoke.py -q`: 29 passed.
- `requirements.txt` unchanged; MVP modules untouched.
- Manual 11-item checklist: all OK by the user.
- EVL cycle 1 (block 4b): EV label truncated by `st.metric` (AC-A6) and over-wide no-"hoy" smoke test (AC-A7); both fixed, cycle 2 clean.
- Validators (UPDATE PROCESS): `validate-all-context.mjs` and `validate-context-discovery.mjs` 0 failures; `validate-plan-inventory.mjs` 0 failures (see session log).

### Plan Deviations
- Numeric correction: catalog iron condor exact PoP at Market('Acción', 100, 0.25, 45, 0.04, 0.01), default commissions, is 0.5721 (exact 0.572122; closed form and 1M-sample MC agree), not 0.5323 (INNOVATE prototype with different inputs, likely sigma ~20 %, 90 days). Plan text fixed; historical mentions in the Validate Contract left as is.
- Accepted: `_histogram` widens range +-0.5 USD for constant/near-constant P&L; `MSG_INVALID_DATA` in implied_vol; `exact_pop` not exported in `__init__`; integers held as floats (1000.0) rejected by `validate_simulation`; 3 MVP smoke tests adjusted in 4a (chart count 1 to 2, days=0 now shows the scenario error), judged legitimate by EVL; `leg_from_dict` helper in `app.py`.
- User-approved fix: duplicated "no es asesoría" notice removed from the scenarios expander.

### Test Infra Gaps Found
- Cross-tab persistence and visual layout still have no automated test (AppTest runs all tabs and cannot clear a `number_input` to None); covered by the manual checklist and recorded in `process/context/tests/all-tests.md` Known Gaps. No backlog stub.

### SPEC Achievement
AC-A1..AC-A17: all **met** (Fully-Automated criteria by passing pytest gates; Hybrid criteria AC-A5, AC-A6, AC-A8, AC-A10, AC-A13, AC-A14, AC-A15, AC-A16 by passing automated gates plus the user's manual checklist). No unmet criteria; no Known-Gap-only criterion.

## SPEC Gaps
None (known_gaps: none; follow_up_stubs: none).

### Closeout Packet
1. Selected plan path: `process/general-plans/completed/etapa-a-montecarlo-iv_20-11-26/etapa-a-montecarlo-iv_PLAN_20-11-26.md` (was `active/`).
2. Closeout classification: CLEAN (EVL handoff: CLEAN; gates green: full suite 910/910, smoke 29/29, requirements unchanged, MVP modules untouched).
3. What was finished: see What Was Done.
4. Verified vs unverified: everything verified; cross-tab persistence and visual layout are manual-only (user-verified).
4b. Validate-contract: VALIDATE run; `## Validate Contract` present, Gate PASS (amendments A1-A8).
5. Cleanup: context files updated, plan checkboxes/status closed, folder archived. Remaining: none.
6. Next valid state: new plan for Stage B (binomial model for American options), with the close-fee backlog item.
7. Commit checkpoint: source commits already made (see above); process-artifact changes from this session are a separate process commit by the orchestrator (not committed here).
8. Regression status: single plan, not a phase program; full suite 910/910 green.
9. SPEC achievement: 17/17 met.

Drift score: (a) >=10 files +2, (d) task folder archived +1, (c) >=3 memory-worthy observations +1 = 4 -> HIGH band. No harness/protocol files touched.

### Forward Preview

#### Test Infra Found
`streamlit.testing.v1.AppTest` smoke tests; MC tests with 4-SE tolerances and fixed seeds.

#### Blast Radius Changes
None beyond plan.

#### Commands to Stay Green
`.venv/bin/pytest -q` (910 tests); `.venv/bin/pytest tests/test_app_smoke.py -q`.

#### Dependency Changes
None.

### Context Audit
- `process/context/all-context.md`: updated (structure, public API, Stage A behaviours, naming gotcha, outstanding work, scan metadata).
- `process/context/tests/all-tests.md`: updated (10 test files, 910 tests, MC tolerances, per-file commands, known gaps).
- `process/context/planning/all-planning.md`: reviewed, unchanged.
- Routing block unchanged (frontmatter descriptions unchanged).
