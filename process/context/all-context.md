# laboratorio-opciones - All Context

Last updated: 2026-11-22 (UPDATE PROCESS, Stage C2 closeout)

This file is the root context entrypoint for the repo.

Use it for two things:

1. quick routing to the right context pack or root file
2. broad architecture and repository understanding

Start here before loading deeper context files.

---

## How This File Works (the `all-*.md` Convention)

Every `process/context/` directory has one `all-*.md` entrypoint that acts as an attachable quick router for that domain. This root file (`all-context.md`) is the top-level router. Context groups each have their own `all-{group}.md` entrypoint.

**The pattern:**

```
process/context/
  all-context.md                      <-- THIS FILE: root router
  planning/
    all-planning.md                   <-- group router for planning
    example-simple-prd.md             <-- deep doc within the group
    example-complex-prd.md            <-- deep doc within the group
  tests/
    all-tests.md                      <-- group router for tests
    debugging-and-pitfalls.md         <-- deep doc within the group
    e2e-tests.md                      <-- deep doc within the group
  database/
    all-database.md                   <-- group router for database
    schema-guide.md                   <-- deep doc within the group
    migration-procedures.md           <-- deep doc within the group
```

**How agents use it:**

1. Agent reads `all-context.md` first (this file)
2. Finds the relevant context group from the routing tables below
3. Reads that group's `all-{group}.md` entrypoint
4. Only then loads the specific deep doc needed

This layered routing keeps context windows small. Never load the whole `process/context/` tree.

**What each `all-{group}.md` must contain:**

- Scope (what the group covers and does NOT cover)
- Read-when rules (when an agent should load this group)
- Quick procedures or decision rules
- Source paths (list of deeper docs in the group)
- Update triggers (when to refresh this group's content)
- Routing to deeper docs within the group

---

## Quick Start

For most substantial tasks:

1. read this file first
2. choose the smallest relevant root file or context group from the tables below
3. only then load deeper files

---

## Current Root Entry Points

<!-- The two tables below (Root Entry Points + Context Groups) are GENERATED from each
     context doc's frontmatter by `discover-context.mjs --emit-routing`. Do NOT hand-edit
     between the GENERATED markers — your edits will be overwritten on the next rebuild.
     To change a row, edit the owning doc's frontmatter (description / keywords) and re-emit.
     `--check-routing` fails lint if this block drifts from the frontmatter on disk. -->

<!-- GENERATED:routing -->
| File | Read when |
|---|---|
| `process/context/all-context.md` | any substantial planning, research, review, or implementation task |
| `process/context/planning/all-planning.md` | Planning guide: plan shape calibration (simple vs complex), plan templates and where plans live. |
| `process/context/tests/all-tests.md` | Testing guide: pytest runner, commands, venv setup, float-comparison and financial-correctness test rules, known gaps. |

## Current Context Groups

| Group | Entry point | Scope |
|---|---|---|
| `planning/` | `process/context/planning/all-planning.md` | Planning guide: plan shape calibration (simple vs complex), plan templates and where plans live. |
| `tests/` | `process/context/tests/all-tests.md` | Testing guide: pytest runner, commands, venv setup, float-comparison and financial-correctness test rules, known gaps. |
<!-- /GENERATED:routing -->

## Task Routing Table

| If the task involves... | Start with |
|---|---|
| product scope, MVP features, roadmap, design decisions and their rationale | `DISENO.md` (repo root, Spanish) |
| architecture or stack questions | this file |
| testing or verification | `process/context/tests/all-tests.md` |
| creating a new plan | `process/context/planning/all-planning.md` |

## Context Group Lifecycle

Context groups are durable knowledge domains, not feature folders.

Create a group when:

- a topic has 3+ durable docs
- a single doc exceeds roughly 800 lines with separable subtopics
- multiple agents repeatedly need only one slice of a large context file
- the topic maps to a stable operational domain (tests, infra, database, auth, UI, workflows, etc.)

Do not create a group when:

- the content is a temporary report
- the content is a plan or execution artifact
- the topic is feature-specific and belongs in `process/features/...`

Move or split one group at a time. Use `all-{group}.md` entrypoints. Run the `audit-context` skill after every context organization change.

## Naming Convention

There are no `README.md` files inside `process/context/`.

Canonical entrypoints use `all-*.md`:

- root: `process/context/all-context.md`
- group: `process/context/{group}/all-{group}.md`

Each `all-{group}.md` file should act as the attachable quick router for that domain:

- tell the agent what the group covers
- give quick procedures and decision rules
- route to smaller deeper files

## Context Update Protocol

When durable project knowledge changes:

1. update the smallest relevant context file
2. update this file if routing, ownership, naming, or groups changed
3. update the owning `all-{group}.md` entrypoint when a group exists
4. run `audit-context`

---

## Repository Structure

MVP (v1), Stage A (Monte Carlo + implied volatility), Stage B1 (binomial American model), Stage C1 (live market data) and Stage C2 (historical data + PoP calibration backtest) implemented. Layout:

```
laboratorio-opciones/
  DISENO.md            -- design doc (Spanish): vision, MVP scope, decisions + rationale, roadmap
  requirements.txt     -- pinned dependencies (numpy, scipy, plotly, streamlit, pytest, yfinance 1.8.0, pandas 3.1.1)
  app.py               -- Streamlit web app (UI only, calls opciones/); 4 tabs: 📊 Catálogo / 🛠️ Constructor / ⚙️ Ajustes / 📈 Backtest (Stage C2);
                          user's visual redesign (22-11-26): emoji tab labels, catalog cards with coloured badges, ➕/➖/🔄 icons,
                          subheaders with divider, COLOR_SYSTEM/COLOR_STRATEGY/ICON_* constants (legs stay dicts, not Leg objects);
                          "Escenarios (Monte Carlo)" expander under the metrics, per-leg IV button, Ajustes "Simulación";
                          Stage B1: Ajustes "Modelo de valoración" radio (binomial / Black-Scholes), premium-origin captions, active-model caption
  opciones/            -- calculation engine (pure Python, no Streamlit imports, no I/O)
    __init__.py        -- public API: models, bs_price/bs_greeks/default_premium, validate_*, market_warnings,
                          TEMPLATES/build_legs, analyze() -> Analysis; Stage A additions: implied_vol, IVResult,
                          SimulationSettings, ScenarioResult, simulate_scenario, validate_simulation, scenario_warnings;
                          Stage B1 additions: crr_price, crr_price_grid, crr_greeks, option_price, option_greeks, uses_binomial
    models.py          -- Leg, Market (last field `pricing_model`: "binomial" default | "black_scholes"), CommissionSettings,
                          constants (MIN_VOL, OPTION_MULTIPLIER, DAYS_PER_YEAR, PRICING_*)
    pricing.py         -- Black-Scholes price + Greeks, default_premium; dispatcher uses_binomial / option_price / option_greeks
    binomial.py        -- CRR binomial tree (American), N/N+1 averaging, crr_price (500/501), crr_price_grid (200/201),
                          crr_greeks, bounded lru_cache memoisation; pure, does not import pricing.py
    commissions.py     -- open_fee, close_fee_expiry, close_fee_today
    payoff.py          -- pnl_expiry, pnl_today, position_greeks, price_grid
    metrics.py         -- exact max profit/loss, breakevens, "unlimited" detection (kink-based, no grid scan)
    validation.py      -- validate_market, validate_legs, market_warnings (Spanish messages)
    catalog.py         -- 8 strategy templates + build_legs
    implied_vol.py     -- implied_vol(leg, market) -> IVResult (brentq on Black-Scholes, or on crr_price for American Acción/ETF;
                          Spanish messages, never raises)
    simulation.py      -- exact_pop (lognormal closed form), SimulationSettings, simulate_scenario (Monte Carlo)
    calibration.py     -- Stage C2: pure numpy; decile binning, Wilson intervals, Brier, kurtosis/tails histogram helpers
    backtest.py        -- Stage C2: pure numpy, helpers on integer day numbers (first_analyzed_index -> (index, years_available, warning),
                          expiry_index -> None if no session in (t, t+H]) and run_backtest(template object, ...); forces Black-Scholes
  ui_backtest.py       -- Stage C2 Backtest tab (root, Streamlit): controls, "Cargar histórico", "Calcular", reliability chart, table, tails;
                          init_backtest_state(), build_tails_figure(z); no I/O or compute without button clicks
  datos/               -- Stage C1 live market data (top-level package, outside the engine; engine unchanged)
    types.py           -- OptionQuote, MarketSnapshot (flag `complete`); C2: PriceHistory, HistoryProvider Protocol (separate from MarketDataProvider)
    errors.py          -- DatosError hierarchy (NetworkError, RateLimitError, EmptyDataError) + Spanish MSG_* texts
    provider.py        -- MarketDataProvider Protocol (swappable provider)
    filters.py         -- LiquidityRules / DEFAULT_RULES (bid>0, ask>0, OI>=100, spread <=10% or <=0.10 when mid<1,
                          +-20% of spot, 7-120 days), clean_row, dedupe, filter_chain (pure, never raise)
    cache.py           -- .cache_datos/ (git-ignored), one JSON per label (SPX.json for ^SPX), schema_version, atomic write
    fake.py            -- FakeProvider (injected today/offsets, fixture-backed; used by tests); C2 params sigma/mu/seed/dividends/
                          irx_percent_series/history_empty_symbols/history_fail_symbols/history_years + history_calls
    service.py         -- load_with_notices / load_or_cache, injected today/now, partial-failure policy
    yahoo.py           -- YahooProvider; the ONLY module importing yfinance/pandas (params yf_module, session); C2 adds get_history
                          (SPX tries ^GSPC, ^SPX only on empty; ^IRX failure non-fatal)
    history_cache.py   -- Stage C2: .cache_datos/history/ (one file per ticker, own schema_version, atomic write, coverage-checked reuse)
    history_service.py -- Stage C2: clean_history (drops today's row, NaN, negatives, duplicates; dividends dated today or later), load with
                          years+1 warm-up, cache fallback offline, provider passed as a callable
    tickers.py         -- curated list: SPX->^SPX; SPY, QQQ, IWM; AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA; "Entrada manual"
  tests/               -- pytest suite (34 modules incl. conftest.py, __init__.py, synthetic.py; 3029 passed + 4 skipped; Stage C2 adds test_calibration, test_backtest_helpers, test_backtest, synthetic.py, test_datos_history_types/cache/service, test_datos_yahoo_history, test_app_backtest; Stage C1 adds test_datos_types/filters/cache/service/yahoo/isolation/live/tickers/chain_picker, tests/fixtures/, extended app smoke): test_pricing, test_legs_payoff,
                          test_commissions, test_metrics, test_validation, test_analyze, test_catalog,
                          test_implied_vol, test_simulation, test_binomial, test_binomial_iv, test_pricing_model, test_app_smoke (AppTest)
  process/             -- RIPER-5 harness: context, plans, development protocols
  .claude/ .codex/ .agents/  -- harness agents and skills (managed, do not edit)
```

Run the app: `.venv/bin/streamlit run app.py`. Engine entry point: `opciones.analyze(market, legs, settings)` returns an `Analysis` (grid, expiry_curve, today_curve, metrics, greeks, commission_total).

## Engine Behaviours Worth Knowing

- **Expiry vs "today" commissions:** the expiry curve charges the close fee only on strictly ITM option legs (so a jump of one fee appears just above/below a strike); the "today" curve charges open + close on every option leg when `include_close` is on (decisions 6 and 14 of the MVP plan). `commission_total = open + close` when `include_close`.
- **days = 0 is allowed** (info warning, "today" curve = intrinsic value, Greeks `None`, shown as "—"); blocking errors only for days < 0, vol < `MIN_VOL` (0.0001), negative/empty spot, strike, premium or quantity. Greeks are also `None` when vol <= 0.
- **Price grid:** spot ±30 %, widened 10 % beyond the outer strikes, 401 points; always includes each strike and strike ± 1e-9.
- **Catalog:** strike step by tier (0.5 below 25, 1 below 100, 2.5 below 250, 5 below 1000, 10 above 1000); colliding strikes are nudged apart. App starts with one ATM long call. Premium 0 and negative rate/q are allowed; strike must be > 0.
- **Premiums:** non-manual premiums are rewritten with the Black-Scholes value on every rerun; a manual edit sets `premium_manual` and is kept (button "↺ BS" resets, "↺ spot" resets the stock price).
- **Breakevens** are rendered on their own markdown line (not `st.metric`, which truncates long values).
- Backlog idea: charge the expiry close fee only if option value exceeds the fee -- `process/general-plans/backlog/close-fee-rational-close_20-11-26.md`.

## Stage A Behaviours Worth Knowing

- **Decisions A1-A11 (summary):** one lognormal terminal-price model; exact PoP (closed form over P&L > 0 intervals of `pnl_expiry`) shown next to the Monte Carlo PoP; risk-neutral drift `r - q` by default, optional user growth mu (-50 %..+100 %/yr, empty = neutral); n_paths integer 1,000..1,000,000 (default 100,000), seed integer 0..2^32-1 (default 42); expiry-only scope (nothing "today" in the scenarios block); expected value is undiscounted; IV only for option legs with a manual premium (button sets the global `vol_pct` via `on_click`); estimates and warnings are study aids, not advice. Full text: `process/general-plans/completed/etapa-a-montecarlo-iv_20-11-26/`.
- **Reference value:** catalog iron condor exact PoP at Market('Acción', 100, 0.25, 45, 0.04, 0.01) with default commissions is 0.5721 (not 0.5323; that came from a prototype with different inputs).
- **Histogram:** `_histogram` widens the range by 0.5 USD for constant/near-constant P&L (np.histogram would fail); displayed range is percentiles 0.5-99.5 %, statistics use all paths. `validate_simulation` rejects integers held as floats (1000.0).
- **Naming gotcha:** `opciones/__init__.py` exports the function `implied_vol`, which shadows the submodule attribute `opciones.implied_vol`. Use `from opciones import implied_vol`; the module is reachable via `sys.modules['opciones.implied_vol']`. `exact_pop` is not exported in `__init__`; import it from `opciones.simulation`.
- **Streamlit pitfalls:** `st.metric` truncates long labels/values (seen twice) -- keep long text in markdown/caption; change widget state only in `on_click` callbacks before render (else `StreamlitWidgetAlreadyInstantiatedError`).

## Stage B1 Behaviours Worth Knowing

- **Dispatcher:** `uses_binomial(market)` is true only for Acción/ETF with `pricing_model == "binomial"` (default); Índice always stays Black-Scholes with identical numbers. Premiums, the "hoy" curve, Greeks and implied volatility of Acción/ETF come from the American CRR tree; P&L at expiry, metrics, exact PoP and Monte Carlo are unchanged (the scenarios warning says only the European-style lognormal terminal model remains).
- **Decisions B1-B7 (summary):** CRR tree averaging N and N+1 steps (premium/Greeks 500/501, "hoy" grid 200/201 per B7); Black-Scholes selectable in Ajustes (manual premiums kept on toggle; reset button reads "↺ binomial" / "↺ BS" / "↺ spot"); tree Greeks from nodes (1,·),(2,·) with central vega/rho (unit "per 1 point"); active-model warnings (BS undervalues American puts, typical error 1-8 %, up to ~24 %); no new dependencies. Full text: `process/general-plans/completed/etapa-b1-binomial_20-11-26/`.
- **Edge handling:** p outside [0,1] -> deterministic limit (not clipping); intrinsic floor only on American grids; if the tree cannot be built Greeks fall back to S/T nudges (finite); `T <= 0` or `sigma <= 0` handled before the tree.
- **American IV rules:** brentq directly on `crr_price`; identifiability checked before brentq (premium = intrinsic -> not identifiable message; premium below intrinsic -> its own message; call premium >= S or put >= K -> "above" message); vega guard (vega < 1e-6 -> not identifiable); precision rule (sigma rejected when half a cent of premium would move sigma by more than 5 points, i.e. vega*0.05 < 0.005). Index or Black-Scholes keeps the Stage A IV path byte for byte.
- **Caching/performance:** pure bounded `functools.lru_cache` (256-512) on `crr_price`, `crr_greeks`, the grid helper (key includes `S_array.tobytes()`) and the American IV branch; cached equals uncached within 1e-12; vega/rho shift trees batched in one induction loop. Measured: premium 0.018 s, 401-point grid ~0.13-0.16 s, Greeks per leg 0.047 s, American IV ~0.18 s, 4-leg iron condor `analyze` cold ~0.8 s / warm 0.002 s.
- **Gotchas:** never export a function named `binomial` from `__init__.py` (it would shadow the submodule, same as `implied_vol`); Streamlit dev servers keep stale imported package modules, so restart the server after engine changes.
- **Known gaps:** the tree clips an American put at K while the no-vol path uses K*exp(-rT) > K for r < 0 on deep-ITM long-T puts (exotic inputs; the tree value is the correct American bound); every spot/vol/days/strike edit is a cold ~0.8 s `analyze` for a 4-leg iron condor.

## Stage C1 Behaviours Worth Knowing

- **Flow:** sidebar Tipo -> Ticker -> "Cargar datos" -> Vencimiento -> real-leg picker. Premium = mid of the chain row; IV shown is computed by the engine; Yahoo IV is reference only. Age text shows how old the data is. Editing the strike of a market leg turns it manual. "Entrada manual" keeps the old manual flow.
- **Liquidity filter (only liquid options shown):** rules live in one place (`LiquidityRules`, `DEFAULT_RULES`), comparisons use tolerance `EPS = 1e-9`. Raw-row contract: `kind, strike, bid, ask, oi` required; `last, volume, iv_yahoo` optional.
- **Cache rule:** a complete load always writes `.cache_datos/<LABEL>.json`; a partial load writes only if not poorer (through today's window) than the cached one (`MarketSnapshot.complete` flag). Reads re-apply filters and recompute days from the injected clock. The first 429 (`RateLimitError`) stops further requests; >=1 chain + 429 -> partial snapshot + notice, 0 chains -> error.
- **Manual live run (21-11-26):** SPY load used 25 HTTP requests; spot 689.81, r 0.04122, q 0.00791; 15 liquid expiries.
- **Offline tests:** autouse network block in `tests/conftest.py`; opt-in live test with `LIVE_DATA=1`. Full text: `process/general-plans/completed/etapa-c1-datos-directo_20-11-26/`.
- **Streamlit lessons:** AppTest re-invokes `format_func` outside the script run, so `format_func` must not read `session_state` or the clock (compute labels inside the script run); change widget state only in callbacks; restart the server after package changes.
- **Known gaps:** Yahoo is unofficial/fragile (~15 min delay, 429 limits; mitigated by cache and messages); live test is opt-in only, so Yahoo format changes are not caught by the normal suite; on weekends/closed market SPX has all bids 0 -> no liquid options (by design, message shown).

## Stage C2 Behaviours Worth Knowing

- **What it is:** a calibration study of the app's PoP, not real profitability (no historical option prices). For past dates t the backtest computes the exact Black-Scholes PoP of a template using only data <= t, then checks whether it won at t+H (last session on or before t+H calendar days, unadjusted close). Output: reliability chart (deciles, Wilson bars), per-bin table, Brier, N and effective N (~years analysed / H, windows overlap so it is an approximation), tails histogram, optional second line with historical mu (1-year window, data <= t).
- **Inputs per date:** realised vol = stdev of daily log returns of adjusted close over W sessions x sqrt(252) (W bound 10..250); r from ^IRX (percent -> fraction, non-fatal fallback to sidebar r with a notice); q = dividends of the previous 12 months / price (0 for the index). Dates failing market validation are skipped and counted; tail dates without expiry and early dates without a window are skipped.
- **Data flow:** "Cargar histórico" downloads the chosen years + 1 warm-up year (user change 21-11-26; fixed 16-year download rejected); cache reuse only if the cached file covers the request and is <= 1 market day old; offline falls back to the cache with its age; today's row is always dropped. Short history -> notice with real years. Cache in `.cache_datos/history/`.
- **State:** backtest state is cleared in `on_ticker_change`/`on_underlying_change`, NOT in `clear_loaded_data` (C1 "Cargar datos" also calls it). Result reused if parameters unchanged. Nothing heavy runs on opening the tab.
- **Oracles (40 synthetic years, iron condor, H=30, W=30, step 10):** GBM |mean PoP - observed| 0.008/0.028 (tol 0.05); regimes max decile dev (n>=100) 0.083/0.110 (<=0.15), skill 0.060/0.061 (>=0.03), |Brier - sum p(1-p)/N| 0.007/0.017 (<=0.04); jumps kurtosis 4.79, max dev 0.447. Timing: 499 dates 0.74 s BS, 1.33 s with mu line.
- **Visual redesign by the user (a29af3e):** its half-done dict->Leg refactor broke 48 tests; fixed by restoring dict legs, reverting engine `models.py`, restoring the breakevens line and reset button, dark-mode-safe colours, 6 label-only test edits. User's original kept at `~/proyectos-claude/backup-app-usuario-22-11-26/`.
- **Lessons:** AppTest runs every tab body, so tabs must do no I/O or compute without clicks; pass the provider as a callable (`data_provider()` builds YahooProvider and swallows exceptions; use a recording spy in tests); `.cache_datos` is git-ignored, so detect test leaks with a sha256 of `find .cache_datos -type f -printf '%p %s %T@\n' | sort` and re-baseline per session (the user's Streamlit servers write there); AI-assisted UI edits can silently refactor state, so run the full suite after visual changes.
- **Known gaps:** live Yahoo history (^GSPC/^SPX, ^IRX, max history) only checked by the user's manual run (opt-in live test not in suite); no historical implied vol (realised vol proxy mixes model error and volatility risk premium; VIX comparison deferred); overlapping windows make effective N approximate, and weekday-only `is_fresh` may refetch once after a market holiday. Full text: `process/general-plans/completed/etapa-c2-historico-backtest_21-11-26/`.

## Technology Stack

- **Language:** Python 3.12.3 (system interpreter, `/usr/bin/python3`)
- **Numerics:** numpy (vectorised P&L over price grids), scipy (`scipy.stats.norm` for Black-Scholes)
- **Charts:** plotly (interactive P&L curves)
- **Web UI:** Streamlit (pure-Python web app, simple styling by design)
- **Market data (Stage C1):** yfinance 1.8.0 + pandas 3.1.1 (free, ~15 min delayed; stocks, ETFs and index options), used only inside `datos/yahoo.py`
- **Tests:** pytest
- **Environment:** local virtualenv `.venv/` (git-ignored), created 2026-11-20. Installed: numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0, yfinance 1.8.0, pandas 3.1.1. Note: `pip install` needs network access outside the sandbox.
- **Version control:** git, single local branch `main`, no remote.

## Key Patterns and Conventions

**Core domain model:** a strategy is a list of *legs*. Each leg = kind (`call` / `put` / `stock`), side (+1 long / -1 short), strike, premium, quantity, expiry. Every metric is computed by evaluating legs individually and summing. Never hard-code a strategy's payoff; catalog strategies are just leg templates.

**Units:** option contracts use a multiplier of 100; stock legs use multiplier 1 with quantity in shares. US market only.

**Pricing:** exact intrinsic value at expiry; Black-Scholes (+ Greeks) before expiry. American CRR binomial tree for Acción/ETF by default (Black-Scholes selectable in Ajustes); Black-Scholes for indices (European). The UI flags the active model.

**Commissions:** configurable, defaults USD 0.65 per contract, extra USD 0.60 per contract on index options, charged on open and close by default. Subtracted from P&L, so they move breakevens.

**Layering:** `opciones/` is pure calculation (no Streamlit imports, no I/O); all network/cache I/O lives in `datos/` (only `datos/yahoo.py` imports yfinance/pandas); the Streamlit app only gathers inputs and draws. Keeps the engine testable.

**Naming / language:** identifiers (variables, functions, classes, modules' public API) in **English**; code comments and docstrings in **Spanish**. UI text in Spanish, keeping standard English option terms (call, put, strike, delta...).

**Pedagogy constraint:** the user is a Python beginner who wants to learn. Keep code simple and explicit (dataclasses, plain functions, numpy), avoid clever abstractions, deliver in small blocks with short, clear explanations.

**Not financial advice:** the app is a study/analysis tool; never present outputs as investment recommendations.

## Environment and Configuration

**Config files:** `requirements.txt` (pinned dependencies), `.gitignore` (includes `.cache_datos/`). No secrets. Env var `LIVE_DATA=1` enables the opt-in live test and lifts the test network block.

**Live data (C1):** yfinance needs no API key. Local cache in `.cache_datos/` (git-ignored). Index options (SPX as `^SPX`) may be empty/all-bid-0 when the market is closed; SPY/QQQ/IWM are the ETF equivalents.

## Source References

- `DISENO.md` -- product design doc (Spanish): scope, decisions and rationale
- `requirements.txt` -- pinned dependencies
- `opciones/__init__.py` -- engine public API
- `app.py` -- Streamlit UI
- `datos/` -- live market data package (Stage C1) and historical data (Stage C2)
- `ui_backtest.py` -- Backtest tab (Stage C2)

## Open Questions / Outstanding Work

- MVP (v1) complete and verified (plan archived in `process/general-plans/completed/mvp-laboratorio_20-11-26/`; AC1-AC18 met, 479 tests).
- Stage A (Monte Carlo + implied volatility) complete and verified (`process/general-plans/completed/etapa-a-montecarlo-iv_20-11-26/`; AC-A1..AC-A17 met, 910 tests).
- Stage B1 (binomial American model) complete and verified (`process/general-plans/completed/etapa-b1-binomial_20-11-26/`; AC-B1..AC-B16 met, 2330 passed + 2 skipped; closeout WITH_GAPS, see Stage B1 known gaps).
- Stage B2 (rational close fee at expiry) deferred by the user; backlog item stays: `process/general-plans/backlog/close-fee-rational-close_20-11-26.md` (accepted decisions: abandon if value <= fee, short legs unchanged, toggle in Ajustes default on).
- Stage C1 (live market data) complete and verified (`process/general-plans/completed/etapa-c1-datos-directo_20-11-26/`; AC-C1-1..AC-C1-16 met, 2742 passed + 3 skipped; closeout COMPLETE_WITH_GAPS, 3 known gaps, see Stage C1 behaviours).
- Stage C2 (historical underlying data + PoP calibration backtest) complete and verified (`process/general-plans/completed/etapa-c2-historico-backtest_21-11-26/`; AC-C2-1..AC-C2-17 met, 3029 passed + 4 skipped; closeout COMPLETE_WITH_GAPS, 3 known gaps; user manual checklist of 8 items OK 22-11-26).
- Next: Stage B2 (rational close fee, backlog) and optional Stage C3 (paid historical options); possible future work: VIX comparison, strategy replay.
- Default commission values are indicative; adjust to the user's real broker when known.

## Scan Metadata

- Generated: 2026-11-20; refreshed at Stage C2 closeout (Repo HEAD 4a21c2c at scan time, commit of closeout follows)
- Mode: UPDATE PROCESS refresh
- Package manager: pip + venv (requirements.txt)
