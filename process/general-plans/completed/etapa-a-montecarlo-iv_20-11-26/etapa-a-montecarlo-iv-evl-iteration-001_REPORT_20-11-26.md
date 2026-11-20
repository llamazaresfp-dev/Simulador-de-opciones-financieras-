---
domain: tests
iteration: 1
date: 2026-11-20
gaps_found: 2
fail_count: 1
concern_count: 1
applied_count: 2
backlogged_count: 0
saturation_status: ACTIVE
loop_status: CONTINUE
---

# EVL iteración 001 — etapa A (bloque 4b)

**Contexto:** puertas del bloque 4b en verde (smoke 27/27, suite 908/908, confirmado por vc-tester). En la revisión visual del orquestador (navegador, 1280 px, long call con prima manual 3,00) aparecieron:

| Gap | Defecto | Corrección |
|---|---|---|
| E1 (FAIL, AC-A6) | La etiqueta del `st.metric` "Valor esperado (no descontado)" se trunca a "Valor esperado (no desconta…" en la fila de 4 columnas: la parte "no descontado" exigida por AC-A6 no se lee | vc-execute-agent (supplement): etiqueta legible completa + aserción |
| E2 (CONCERN, AC-A7) | El smoke test 4a "sin 'hoy' en el desplegable" solo pasa porque no hay patas manuales; el aviso de AC-A13 menciona "hoy" legítimamente | Acotar el test a resultados/métricas/gráfico y añadir variante con pata manual |

Botón "Usar como volatilidad global" verificado en el navegador: volatilidad 20 % → 24,81 %.
