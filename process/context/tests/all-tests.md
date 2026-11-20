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

Last updated: 2026-11-20 (vc-setup STUDY)

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

(No deeper test docs yet. Add routing entries here as they are created.)

## Quick Decision Guide

### Use `pytest` for everything

- single runner for the whole project; tests live in `tests/`, named `test_*.py`
- engine (`opciones/`) is pure Python, so it is fully unit-testable without the UI
- financial correctness tests compare against known textbook values: payoff of each leg at expiry, max loss/profit of spreads, put-call parity, Black-Scholes reference prices and Greek signs

### Streamlit UI

- no automated UI tests in the MVP; verify manually with `.venv/bin/streamlit run app.py` once `app.py` exists

## Default Verification Order

Unless the task clearly needs a different path:

1. run the narrowest existing automated test
2. use unit/integration tests before browser tests
3. use end-to-end tests only when the real UI is the thing being verified

## Commands

```bash
.venv/bin/pytest                         # run all tests
.venv/bin/pytest tests/test_legs.py      # single file
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

## Debugging Quick Reference

- **Always use `.venv/bin/...`:** system Python has no numpy/pytest. Never `pip install --user` or `--break-system-packages`.
- **No tests collected:** pytest exits with code 5 while `tests/` is empty; that is expected, not a failure.
- **Float comparisons:** use `pytest.approx` / `numpy.testing.assert_allclose` for prices and Greeks, never `==`.
- **Imports:** run pytest from the repo root so `import opciones` resolves (`tests/__init__.py` exists).

## Known Gaps

- No tests exist yet (no engine code yet).
- No automated tests for the Streamlit UI (manual verification only in the MVP).
- Market-data code (v2) will need mocked yfinance responses; not designed yet.
