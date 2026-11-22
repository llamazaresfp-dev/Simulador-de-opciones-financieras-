---
domain: plan
iteration: 2
date: 2026-11-21
plan: etapa-c2-historico-backtest_PLAN_21-11-26.md
gaps_found: 1
fail_count: 0
concern_count: 1
applied: 1
regression: false
loop_status: CONTINUE
---

# PVL iteración 002 — Etapa C2 (cambio del usuario)

El usuario rechazó la desviación (i) (descarga fija de 16 años). Nueva regla aplicada al plan y a 2 líneas del SPEC:

- "Cargar histórico" descarga los años elegidos + 1 de calentamiento (`start_for_years`, años de calendario).
- La caché se reutiliza si está al día y cubre el tramo pedido (`covers`, tolerancia 7 días o `requested_start` guardado ≤ inicio pedido).
- Calcular avisa y no calcula si el histórico cargado no cubre los años elegidos.
- Riesgos nuevos R16-R17 (una recarga con menos años sobrescribe una caché más larga: aceptado).

Siguiente: re-validar desde V1 (E-5 del contrato aún menciona 16 años).
