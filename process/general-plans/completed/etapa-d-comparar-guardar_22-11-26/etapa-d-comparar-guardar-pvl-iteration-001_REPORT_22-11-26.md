---
domain: plan
iteration: 1
date: 2026-11-22
plan: etapa-d-comparar-guardar_PLAN_22-11-26.md
gaps_found: 4
fail_count: 0
concern_count: 4
applied: 4
regression: false
loop_status: CONTINUE
---

# PVL iteración 001 — Etapa D

Veredicto previo: Gate CONDITIONAL (0 FAIL, 4 CONCERN). Suplemento aplicado por vc-plan-agent.

| Gap | Corrección |
|---|---|
| S-1 | "Abrir con su mercado" escribe también las claves de widget `*_input` de Ajustes, `sv_*_input` y `cmp_selected_input`; los tests comprueban el valor del widget (DD-20) |
| S-2 | Límites de magnitud en `parse_strategy_json` (`BOUNDS`) y try/except en comparar/abrir; nunca NaN/inf hacia plotly (DD-21, DD-22) |
| S-3 | Test de aislamiento con recorrido `ast` de imports, no búsqueda de texto |
| S-4 | Curvas "hoy" en la rejilla propia de cada estrategia (1,58 s frente a 6,98 s); vencimiento en rejilla común (DD-23) |

Siguiente: re-validar desde V1.
