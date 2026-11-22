---
domain: plan
iteration: 1
date: 2026-11-21
plan: etapa-c2-historico-backtest_PLAN_21-11-26.md
gaps_found: 4
fail_count: 0
concern_count: 4
applied: 4
regression: false
loop_status: CONTINUE
---

# PVL iteración 001 — Etapa C2

Veredicto previo: Gate CONDITIONAL (0 FAIL, 4 CONCERN). Suplemento aplicado por vc-plan-agent.

| Gap | Sección | Corrección |
|---|---|---|
| C-V1 | Bloque 9 | `render_backtest` recibe `get_provider` (callable); el proveedor solo se crea al pulsar "Cargar histórico"; test que prohíbe construir YahooProvider sin botón |
| C-V2 | Bloque 3 | Tolerancias de oráculos medidas: GBM ≤ 0,05; regímenes de 504 sesiones, deciles n ≥ 100 dentro de 0,15, habilidad ≥ 0,03, Brier ±0,04; regla de ensanchar si el margen < 25 % |
| C-V3 | Bloques 5, 6, 9, 10, cierre | Huella sha256 de `.cache_datos` en lugar de `git status` (carpeta ignorada) |
| C-V4 | Bloque 4 | FakeProvider: `history_empty_symbols`, `history_fail_symbols`, `history_years` |

Siguiente: re-validar desde V1.
