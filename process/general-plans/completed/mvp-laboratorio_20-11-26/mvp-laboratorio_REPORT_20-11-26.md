---
phase: mvp-laboratorio-closeout
date: 2026-11-20
status: COMPLETE
feature: none (general-plans)
plan: process/general-plans/completed/mvp-laboratorio_20-11-26/mvp-laboratorio_PLAN_20-11-26.md
---

# Phase report: MVP (v1) Laboratorio de Opciones (UPDATE PROCESS)

TL;DR: all 6 blocks verified, AC1-AC18 met, 479/479 tests, user manual checklist passed. Classification: Ready for UPDATE PROCESS archival. Plan archived to `completed/`.

### What Was Done
- Blocks 1-6 implemented: `models`, `pricing`, `commissions`, `payoff`, `metrics`, `validation`, `analyze()`, `catalog`, `app.py`, 8 test files. Commits: block1 5918b13 (23 tests), block2 ac75c6d (60), block3 ee8e46e (91), block4 ce52faf (166), block5 c7ac737 (473), block6 2c18510 (479); SPEC/plan c08f263.
- Each block confirmed by an independent vc-tester EVL run and approved by the user. EVL cycle 1 on block 6 fixed breakevens truncated by `st.metric` (AC12) with a regression AppTest.
- UPDATE PROCESS: plan statuses set to VERIFIED, bull-spread number corrected, backlog item created, `all-context.md` and `tests/all-tests.md` refreshed, task folder archived.

### What Was Skipped/Deferred
- Rational close fee at expiry (would change decision 6; user kept decision 6): `process/general-plans/backlog/close-fee-rational-close_20-11-26.md`.
- v2 roadmap (yfinance etc.) per `DISENO.md`: future plan, not backlog-stubbed here.

### Test Gate Outcomes
- `.venv/bin/pytest -q`: 479 passed. `.venv/bin/pytest tests/test_app_smoke.py -q`: 6 passed (EVL final, block 6).
- Manual 10-item checklist (Hybrid criteria AC1, AC3, AC9, AC14, AC16, AC17 + item 9 cross-tab persistence): all OK by the user.
- Validators (UPDATE PROCESS): `validate-all-context.mjs` 0 failures; `validate-context-discovery.mjs` 0 failures; `validate-plan-inventory.mjs` run.

### Plan Deviations
- Numeric correction: bull call spread (100@3 / 110@1, default commissions) max loss is -201.95, not -201.30 (just above S=100 the long call is strictly ITM and pays the 0.65 close fee; -201.30 is only P(100)). Plan text fixed; SPEC untouched (it does not contain the figure).
- Plan-unspecified choices accepted by the user: price grid spot +-30% widened 10% beyond outer strikes, 401 points; Greeks None when vol <= 0; strike step 10 above 1000; strike collision nudging in catalog; premium 0 allowed, strike > 0; negative rate/q allowed; commission_total = open + close (include_close); app starts with one ATM long call; stock reset button "↺ spot"; `persist_state` not used.

### Test Infra Gaps Found
- Cross-tab persistence and visual layout have no automated test (AppTest limitation); covered only by the manual checklist. No backlog stub: inherent to AppTest, recorded in `process/context/tests/all-tests.md` Known Gaps.

### SPEC Achievement
AC1-AC18: all **met** (each Fully-Automated criterion by a passing pytest gate; Hybrid criteria AC1, AC3, AC9, AC14, AC16, AC17 by passing automated gates plus the user's manual checklist). No unmet criteria; no Known-Gap-only criterion.

## SPEC Gaps
None.

### Closeout Packet
1. Selected plan path: `process/general-plans/completed/mvp-laboratorio_20-11-26/mvp-laboratorio_PLAN_20-11-26.md` (was `active/`).
2. Closeout classification: Ready for UPDATE PROCESS archival (EVL handoff: CLEAN).
3. What was finished: see What Was Done.
4. Verified vs unverified: everything verified; only cross-tab persistence is manual-only (user-verified).
4b. Validate-contract: VALIDATE run; `## Validate Contract` present, Gate PASS.
5. Cleanup: context files updated, backlog item written, plan checkboxes/status closed. Remaining: none.
6. Next valid state: new plan for roadmap v2 per `DISENO.md` (or the backlog close-fee item).
7. Commit checkpoint: source commits already made (block 1-6 commits); the process-artifact changes from this session are a separate process commit by the orchestrator.
8. Regression status: single plan, not a phase program; full suite 479/479 green.
9. SPEC achievement: see above (18/18 met).

Drift score: (a) >=10 files +2, (d) task folder archived + backlog note +1, (c) >=3 memory-worthy observations +1 = 4 -> HIGH band. "Strongly recommend UPDATE PROCESS -- harness/protocol files touched." (No harness/protocol files were actually touched in this repo's process; signal count driven by files touched and structural changes.)

### Forward Preview

#### Test Infra Found
`streamlit.testing.v1.AppTest` smoke tests (documented in all-tests.md).

#### Blast Radius Changes
Added vs plan: none beyond plan (`opciones/{models,pricing,commissions,payoff,metrics,validation,catalog,__init__}.py`, `app.py`, `tests/*`, `requirements.txt`).

#### Commands to Stay Green
`.venv/bin/pytest -q` (479 tests); `.venv/bin/pytest tests/test_app_smoke.py -q`.

#### Dependency Changes
Pinned: numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0.

### Context Audit
- `process/context/all-context.md`: updated (structure, API, run command, engine behaviours, outstanding work, routing block re-emitted).
- `process/context/tests/all-tests.md`: updated (8 test files, 479 tests, AppTest, per-file commands, Known Gaps).
- `process/context/planning/all-planning.md`: reviewed, unchanged (plan templates unaffected).
- Feature list sync: `process/features/` has only template/guide; no feature lists in CLAUDE.md/AGENTS.md to change.
