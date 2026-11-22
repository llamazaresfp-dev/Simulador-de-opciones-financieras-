---
domain: plan
iteration: 3
date: 2026-11-21
plan: etapa-c2-historico-backtest_PLAN_21-11-26.md
gaps_found: 2
fail_count: 0
concern_count: 2
applied: 0
regression: false
loop_status: CONTINUE
---

# PVL iteración 003 — Etapa C2

Re-validación tras el cambio del usuario: Gate CONDITIONAL (0 FAIL, 2 CONCERN + 1 aviso).

| Gap | Corrección pedida |
|---|---|
| S-1 | Acotar la ventana W (10–250, por defecto 30), test de rango en el bloque 9, PD-14 "≈249–252 sesiones" |
| S-2 | `HistoryLoad.requested_start: date \| None` (caché antigua sin el campo); test en el bloque 6 |
| S-3 | Aviso: refrescar Resume ítem 3 y `## Next Step` |

Sin bloqueo entre AC-C2-4 y el aviso de cobertura (verificado). Siguiente: suplemento y re-validación desde V1.
