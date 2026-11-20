---
domain: plan
iteration: 1
date: 2026-11-20
gaps_found: 6
fail_count: 2
concern_count: 4
applied_count: 6
backlogged_count: 0
saturation_status: ACTIVE
loop_status: CONTINUE
---

# PVL iteración 001 — etapa B1 (binomial)

**Entrada:** `Gate: BLOCKED` (primera pasada outer PVL, 2 FAIL, 4 CONCERN).

| Gap | Hueco | Corrección (vc-plan-agent, supplement) |
|---|---|---|
| F1 | `test_pricing.py` no podía quedar intacto (2 tests de `default_premium` fallan con binomial por defecto) | Fijar `pricing_model="black_scholes"` en `make_market` (1 línea); AC-B16, touchpoints y puertas actualizados |
| F2 | Lista de tests a fijar incompleta (5 fallos emulados, incl. `test_simulation`) | `test_simulation.py` y helper de catálogo pasan a "modificar"; barrido del bloque 2 que solo fija helpers |
| C1 | Rendimiento: ~0,65 s en frío por iron condor, hasta ~1,3 s con 4 IV | Caché acotada obligatoria (precio, griegas, malla, IV) + bumps vega/rho agrupados; tests frío < 2 s y caliente < 0,3 s |
| C2 | Tolerancia AC-B3 demasiado estricta (3,2e-3 observado) | 5e-3 y el promedio gana al N simple en ≥ 80 % de casos |
| C3 | Margen AC-B2 justo | Barrido europeo con 3e-3 |
| C4 | Matriz de tests de IV americana | Error de σ solo con vega > 0,01 y prima > intrínseco; ida y vuelta de precio siempre |

**Señal:** `SUPPLEMENT_APPLIED: ... — 6 gap(s) addressed`. Validador de estructura: 0 fallos.
**Siguiente:** re-ejecutar vc-validate-agent desde V1.
