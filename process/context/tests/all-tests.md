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

Last updated: 2026-11-21 (UPDATE PROCESS, Stage C1 closeout)

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

- `tests/test_app_smoke.py` uses `streamlit.testing.v1.AppTest` (loads the app, opens a catalog template, commission settings reach the result, days = 0 warns, vol = 0 errors with no chart, breakevens line shows all values; Stage A: scenarios expander structure, IV button sets `vol_pct`, no "today" content in the expander, full expected-value label; 29 tests). AppTest runs every tab body, cannot clear a `number_input` to None, so it does NOT prove cross-tab persistence or visual layout.
- Manual (user) checklist still covers visuals and cross-tab persistence of the Ajustes values: `.venv/bin/streamlit run app.py`.
- The engine import must not pull in Streamlit: checked in a fresh subprocess in `tests/test_analyze.py`.

### Test files (2742 passed + 3 skipped at Stage C1 close)

| File | Covers |
|---|---|
| `tests/test_pricing.py` | Black-Scholes (Hull, S=K=100), Greeks, put-call parity, q, edge cases, `default_premium` |
| `tests/test_legs_payoff.py` | per-leg and strategy P&L, `price_grid`, `position_greeks` |
| `tests/test_commissions.py` | per-contract/index fees, open/close rules, "today" vs expiry close fee |
| `tests/test_metrics.py` | max profit/loss, breakevens, "unlimited", hand-computed commission cases |
| `tests/test_validation.py` | blocking errors vs warnings, Spanish messages |
| `tests/test_analyze.py` | `analyze()` end to end, no NaN, engine imports without Streamlit |
| `tests/test_catalog.py` | 8 templates, `build_legs`, strike rounding tiers, book metrics per template |
| `tests/test_implied_vol.py` | IV round trip (ATM/OTM/ITM, sigma 1 %-300 %, 1 and 45 days), bounds, premium 0, days 0, stock leg, never raises |
| `tests/test_simulation.py` | exact PoP vs `scipy.integrate.quad`, N(d2) reference, PoP 0 and 1, Monte Carlo statistics, seed reproducibility, performance, exports |
| `tests/test_binomial.py` | CRR pricer: Hull references (7.4284, 4.4885), European tree vs BS, scaled-tolerance test of the averaged European pricer, early-exercise premium, parity bounds, grid vs scalar, Greeks, edge cases, timing and cache-equality tests |
| `tests/test_binomial_iv.py` | American IV round trip (price always; sigma only where vega > 0.01), identifiability/precision/vega-guard messages, Index/BS path equals Stage A IV, never raises, timing |
| `tests/test_pricing_model.py` | dispatcher truth table, canary (default Market is binomial), Index identical under both selectors, expiry regression (P&L, metrics, exact PoP 0.5721, MC seed 42 identical), "hoy" curve bounds, position Greeks, timing |
| `tests/test_app_smoke.py` | AppTest smoke of `app.py` (incl. Ajustes model radio, manual premium kept on toggle, reset-button labels, Index "no tiene efecto"; Stage C1: ticker cascade, real-leg picker, expiry-label regression) |
| `tests/test_datos_types.py` | OptionQuote/MarketSnapshot, error hierarchy, Spanish MSG_*, Protocol, network-block test |
| `tests/test_datos_filters.py` | liquidity rules with exact-border cases (EPS tolerance), dirty/duplicate rows, fixtures, thresholds in one place |
| `tests/test_datos_cache.py` | atomic write/read in `tmp_path`, `SPX.json` naming, corrupt/schema mismatch, partial-vs-rich rule, `complete` flag |
| `tests/test_datos_service.py` | FakeProvider service with injected clock: r/q conversion, window 7-120 borders, partial failures, first 429 stops requests, cache writes, `load_or_cache` |
| `tests/test_datos_yahoo.py` | YahooProvider with injected fake `yf_module`/`session` (no network) |
| `tests/test_datos_isolation.py` | only `datos/yahoo.py` imports yfinance/pandas; engine does not import `datos` |
| `tests/test_datos_live.py` | opt-in live test against Yahoo (skipped unless `LIVE_DATA=1`) |
| `tests/test_datos_tickers.py` | curated ticker list and `^SPX` mapping |
| `tests/test_datos_chain_picker.py` | real-leg picker: premium = mid, manual on strike edit |

Notes: `test_validation.py` also covers `validate_simulation` and `scenario_warnings`; `test_analyze.py` checks that `opciones.implied_vol` and `opciones.simulation` import without Streamlit. Monte Carlo tests use tolerances of 4 standard errors and fixed seeds (deterministic, not flaky). Per-file commands: `.venv/bin/pytest tests/test_implied_vol.py -q`, `.venv/bin/pytest tests/test_simulation.py -q`.

**Pinning convention (Stage B1):** the default `Market.pricing_model` is `"binomial"`, so tests whose expected numbers assume Black-Scholes premiums for Acción/ETF pin their `Market` helpers with `pricing_model="black_scholes"` (test_pricing.py: one line in `make_market`; also test_legs_payoff, test_simulation, test_implied_vol, test_analyze, test_catalog, and the smoke test where concrete premiums are asserted). Never change an expected number to make a test pass; pin the helper instead. Also run the full suite when a cross-cutting default changes (the emulation during VALIDATE found 5 hidden failures).

**Timing tests (AC-B13):** loose `time.perf_counter` bounds: premium < 0.25 s, 401-point grid < 1.0 s, American IV < 2.0 s, iron condor `analyze` cold < 2.0 s and warm < 0.3 s. Cached results must equal uncached within 1e-12 and never return a shared mutable array. 2 legitimate skips (put at intrinsic; IV undefined).

**Offline rule and fixtures (Stage C1):** `tests/conftest.py` has an autouse fixture that blocks `socket.socket.connect` and `socket.getaddrinfo` (clear "red bloqueada en tests" error); `LIVE_DATA=1` lifts it and enables the live test. The suite also passes under `unshare -rn` (no network). Fixtures in `tests/fixtures/` re-recorded Saturday 21-11-26: real `aapl`, `spy`, `spx_weekend` (all bids 0); synthetic `spx`, `bid_zero`, `dirty`, `stale_last`, `edge_exact`. Date-dependent tests inject `today`/`now`; never read the real clock. `.cache_datos/` must not be created by tests (use `tmp_path`). 3 skips = 2 legitimate B1 skips + the opt-in live test.

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
.venv/bin/pytest tests/test_simulation.py -q  # exact PoP + Monte Carlo (likewise test_implied_vol.py)
.venv/bin/pytest tests/test_binomial.py tests/test_binomial_iv.py tests/test_pricing_model.py -q  # Stage B1
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
- **Reference numbers:** recompute from INNOVATE prototypes with the exact inputs; the catalog iron condor exact PoP is 0.5721 at Market(100, 0.25, 45 d, 0.04, 0.01) with default commissions.
- **Naming gotcha:** `from opciones import implied_vol` (the package attribute `opciones.implied_vol` is the function, not the module).
- **Float comparisons:** use `pytest.approx` / `numpy.testing.assert_allclose` for prices and Greeks, never `==`.
- **Imports:** run pytest from the repo root so `import opciones` resolves (`tests/__init__.py` exists).

## Known Gaps

- Cross-tab persistence of the Ajustes values and visual layout have no automated test (AppTest cannot cover lazy tabs/visuals); verified manually by the user at MVP close.
- Monte Carlo tests prove exactness against independent oracles, not that lognormal/Black-Scholes describe real markets (warnings only). Histogram clipping at percentiles 0.5-99.5 % is a presentation choice. No browser performance test (engine time only).
- Stage C1: the live test is opt-in only (`LIVE_DATA=1`), so Yahoo format changes are not caught by the normal suite; weekend/closed market leaves SPX with all bids 0 (no liquid options, by design); Yahoo is unofficial, ~15 min delayed, 429 limits (mitigated by cache and messages). Streamlit lesson: AppTest re-invokes `format_func` outside the script run, so it must not read `session_state` or the clock.
- Stage B1: the tree clips an American put at K while the no-vol path uses K*exp(-rT) > K for r < 0 on deep-ITM long-T puts (exotic inputs; no test asserts equality there); cold `analyze` of a 4-leg iron condor is ~0.8 s (only a regression bound, not a UX test). After engine changes restart any Streamlit dev server (stale imported modules) before manual checks.
- Resolved: engine tests exist (2742 passed + 3 skipped incl. Stage A, B1 and C1); UI smoke test exists (former gap G3).
