---
name: context:all-tests
description: "Testing guide: pytest runner, commands, venv setup, float-comparison and financial-correctness test rules, known gaps."
date: 20-11-26
keywords: test, tests, pytest, verify, verification, venv, failing test, debug, gate
metadata:
  node_type: memory
  type: context
---

# laboratorio-opciones - All Tests

Last updated: 2026-11-20 (UPDATE PROCESS, MVP closeout)

Attach this file first when the task involves testing, verification, or test debugging.

This is the fast operator guide for the testing surface:

- which runner to use
- what command to start with
- how to quickly debug common failures
- which deeper file to read next

Do not load the whole `process/context/tests/` folder by default. Start here, then drill down.

---

## How This File Works

This is the `all-tests.md` entrypoint for the `tests/` context group. It follows the `all-*.md` routing convention:

1. Agents read `all-context.md` first and get routed here for testing tasks
2. This file gives quick decision rules and commands
3. For deeper details, agents follow the routing table below to specific docs

As the project grows, add deeper docs to this group (e.g., `e2e-tests.md`, `debugging-and-pitfalls.md`) and add routing entries below. This file stays the fast-start entrypoint.

---

## What This Covers

- test runner selection
- quick commands by package
- fast debugging procedures
- current testing gaps worth remembering

## Read This When

Use this file when you need to:

- run tests after implementation
- decide between test runners
- debug failing tests

## Quick Routing

No deeper test docs yet; the per-file table below is the map. Add routing entries here when deeper docs are created.

## Quick Decision Guide

### Use `pytest` for everything

- single runner for the whole project; tests live in `tests/`, named `test_*.py`
- engine (`opciones/`) is pure Python, so it is fully unit-testable without the UI
- financial correctness tests compare against known textbook values: payoff of each leg at expiry, max loss/profit of spreads, put-call parity, Black-Scholes reference prices and Greek signs

### Streamlit UI

- `tests/test_app_smoke.py` uses `streamlit.testing.v1.AppTest` (loads the app, opens a catalog template, commission settings reach the result, days = 0 warns, vol = 0 errors with no chart, breakevens line shows all values). AppTest runs every tab body, so it does NOT prove cross-tab persistence or visual layout.
- Manual (user) checklist still covers visuals and cross-tab persistence of the Ajustes values: `.venv/bin/streamlit run app.py`.
- The engine import must not pull in Streamlit: checked in a fresh subprocess in `tests/test_analyze.py`.

### Test files (479 tests at MVP close)

| File | Covers |
|---|---|
| `tests/test_pricing.py` | Black-Scholes (Hull, S=K=100), Greeks, put-call parity, q, edge cases, `default_premium` |
| `tests/test_legs_payoff.py` | per-leg and strategy P&L, `price_grid`, `position_greeks` |
| `tests/test_commissions.py` | per-contract/index fees, open/close rules, "today" vs expiry close fee |
| `tests/test_metrics.py` | max profit/loss, breakevens, "unlimited", hand-computed commission cases |
| `tests/test_validation.py` | blocking errors vs warnings, Spanish messages |
| `tests/test_analyze.py` | `analyze()` end to end, no NaN, engine imports without Streamlit |
| `tests/test_catalog.py` | 8 templates, `build_legs`, strike rounding tiers, book metrics per template |
| `tests/test_app_smoke.py` | AppTest smoke of `app.py` |

## Default Verification Order

Unless the task clearly needs a different path:

1. run the narrowest existing automated test
2. use unit/integration tests before browser tests
3. use end-to-end tests only when the real UI is the thing being verified

## Commands

```bash
.venv/bin/pytest                         # run all tests
.venv/bin/pytest tests/test_metrics.py   # single file (see file table for the others)
.venv/bin/pytest tests/test_app_smoke.py -q   # UI smoke (AppTest)
.venv/bin/pytest -k bull_spread -v       # tests matching a name
```

One-time environment setup (already done; repeat only to rebuild `.venv/`):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

| Package | Runner | Command |
|---|---|---|
| `opciones/` (engine) | pytest | `.venv/bin/pytest` |
| `app.py` (UI smoke) | pytest + AppTest | `.venv/bin/pytest tests/test_app_smoke.py -q` |

## Debugging Quick Reference

- **Always use `.venv/bin/...`:** system Python has no numpy/pytest. Never `pip install --user` or `--break-system-packages`.
- **Hand-computed commission cases:** the bull call spread 100@3 / 110@1 with default commissions has max loss -201.95 (just above S=100 the long call is strictly ITM and pays the 0.65 close fee); -201.30 is only P(100).
- **Float comparisons:** use `pytest.approx` / `numpy.testing.assert_allclose` for prices and Greeks, never `==`.
- **Imports:** run pytest from the repo root so `import opciones` resolves (`tests/__init__.py` exists).

## Known Gaps

- Cross-tab persistence of the Ajustes values and visual layout have no automated test (AppTest cannot cover lazy tabs/visuals); verified manually by the user at MVP close.
- Market-data code (v2) will need mocked yfinance responses; not designed yet.
- Resolved: engine tests exist (479); UI smoke test exists (former gap G3).
