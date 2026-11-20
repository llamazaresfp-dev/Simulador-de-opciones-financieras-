# laboratorio-opciones - All Context

Last updated: 2026-11-20 (vc-setup STUDY)

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

Greenfield project: the design is written, no engine code yet. Planned layout (MVP):

```
laboratorio-opciones/
  DISENO.md            -- design doc (Spanish): vision, MVP scope, decisions + rationale, roadmap
  requirements.txt     -- Python dependencies (unpinned for now)
  opciones/            -- calculation engine (pure Python, no UI code)
    __init__.py
    (planned) legs/strategy, pricing (Black-Scholes + Greeks), metrics, commissions, catalog
  tests/               -- pytest suite for the engine
    __init__.py
  (planned) app.py     -- Streamlit web app (UI only, calls opciones/)
  process/             -- RIPER-5 harness: context, plans, development protocols
  .claude/ .codex/ .agents/  -- harness agents and skills (managed, do not edit)
```

## Technology Stack

- **Language:** Python 3.12.3 (system interpreter, `/usr/bin/python3`)
- **Numerics:** numpy (vectorised P&L over price grids), scipy (`scipy.stats.norm` for Black-Scholes)
- **Charts:** plotly (interactive P&L curves)
- **Web UI:** Streamlit (pure-Python web app, simple styling by design)
- **Market data (v2, not MVP):** yfinance (free, ~15 min delayed; US stocks, ETFs and index options SPX/NDX/RUT)
- **Tests:** pytest
- **Environment:** local virtualenv `.venv/` (git-ignored), created 2026-11-20. Installed: numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0. Note: `pip install` needs network access outside the sandbox.
- **Version control:** git, single local branch `main`, no remote.

## Key Patterns and Conventions

**Core domain model:** a strategy is a list of *legs*. Each leg = kind (`call` / `put` / `stock`), side (+1 long / -1 short), strike, premium, quantity, expiry. Every metric is computed by evaluating legs individually and summing. Never hard-code a strategy's payoff; catalog strategies are just leg templates.

**Units:** option contracts use a multiplier of 100; stock legs use multiplier 1 with quantity in shares. US market only.

**Pricing:** exact intrinsic value at expiry; Black-Scholes (+ Greeks) before expiry. Exact for European options (indices), an approximation for American (stocks/ETFs) -- the UI must flag this.

**Commissions:** configurable, defaults USD 0.65 per contract, extra USD 0.60 per contract on index options, charged on open and close by default. Subtracted from P&L, so they move breakevens.

**Layering:** `opciones/` is pure calculation (no Streamlit imports, no I/O); the Streamlit app only gathers inputs and draws. Keeps the engine testable.

**Naming / language:** identifiers (variables, functions, classes, modules' public API) in **English**; code comments and docstrings in **Spanish**. UI text in Spanish, keeping standard English option terms (call, put, strike, delta...).

**Pedagogy constraint:** the user is a Python beginner who wants to learn. Keep code simple and explicit (dataclasses, plain functions, numpy), avoid clever abstractions, deliver in small blocks with short, clear explanations.

**Not financial advice:** the app is a study/analysis tool; never present outputs as investment recommendations.

## Environment and Configuration

**Config files:** `requirements.txt` (dependencies), `.gitignore`. No env vars, secrets or external services in the MVP.

**v2 (planned):** yfinance needs no API key. Index option data (SPX/NDX/RUT) may be incomplete on Yahoo; fallback to equivalent ETFs (SPY/QQQ/IWM).

## Source References

- `DISENO.md` -- product design doc (Spanish): scope, decisions and rationale
- `requirements.txt` -- dependencies

## Open Questions / Outstanding Work

- Engine code not started: MVP implementation pending via RIPER-5.
- Default commission values are indicative; adjust to the user's real broker when known.

## Scan Metadata

- Generated: 2026-11-20
- HEAD: none (fresh repo, no commits yet)
- Mode: Flow A (new project), fresh scaffold
- Package manager: pip + venv (requirements.txt)
