---
domain: tests
iteration: 2
date: 2026-11-21
gaps_found: 1
fail_count: 1
concern_count: 0
applied_count: 1
backlogged_count: 0
saturation_status: ACTIVE
loop_status: CONTINUE
---

# EVL iteración 002 — etapa C1 (bloque 7)

**Contexto:** el bloque 7 pasó (2741 passed) hacia las 05:00 CET; la confirmación independiente, tras una pausa por límite de uso, encontró 23 fallos (`'2026-11-30 (9 días)' is not in list`). vc-debugger aisló la causa.

| Gap | Defecto | Corrección |
|---|---|---|
| F1 (C-V2) | El `format_func` del selector de vencimientos (`app.py:665`) llama a `days_until` → `current_time()`, que lee el reloj de `st.session_state`. AppTest vuelve a llamar a `format_func` fuera de la ejecución del script, donde `session_state` no funciona, y cae al reloj real. Pasaba mientras la fecha de Nueva York coincidía con el reloj fijado de los tests (20-11); falla desde la medianoche de NY | Calcular las etiquetas dentro de la ejecución y cerrar sobre ellas en `format_func` (ningún callback que Streamlit pueda ejecutar fuera del script debe leer el reloj de `session_state`); revisar el resto de `format_func` |

**Descartado:** la carpeta real `.cache_datos/` (AMZN, NVDA, 23:48–23:49 hora de NY) no influye; procede de una carga real de la app hecha por el usuario, no de los tests.
**Siguiente:** vc-execute-agent (supplement) y re-ejecución de vc-tester.
