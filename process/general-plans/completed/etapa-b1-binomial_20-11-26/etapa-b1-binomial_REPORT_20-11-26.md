---
phase: etapa-b1-binomial-closeout
date: 2026-11-20
status: COMPLETE_WITH_GAPS
feature: none (general-plans)
plan: process/general-plans/completed/etapa-b1-binomial_20-11-26/etapa-b1-binomial_PLAN_20-11-26.md
---

# Informe de fase: Etapa B1, modelo binomial para opciones americanas (UPDATE PROCESS)

TL;DR: los 7 bloques están verificados, AC-B1..AC-B16 cumplidos, suite 2330 passed + 2 skipped, checklist manual de 8 ítems pasada por el usuario ("todo bien"). Clasificación: WITH_GAPS (2 huecos conocidos, ninguno bloquea). Plan archivado en `completed/`.

### What Was Done
- Motor: nuevo `opciones/binomial.py` (árbol CRR vectorizado, promedio N/N+1, `crr_price`, `crr_price_grid`, `crr_greeks`, memoización acotada); despachador en `pricing.py` (`uses_binomial`, `option_price`, `option_greeks`); `Market.pricing_model` ("binomial" por defecto o "black_scholes"); IV americana en `implied_vol.py` con reglas de identificabilidad y precisión; avisos por modelo en `validation.py`; exportaciones en `__init__.py`.
- UI: selector "Modelo de valoración" en Ajustes, etiquetas de origen de prima, caption del modelo activo. Tests nuevos: `test_binomial.py`, `test_binomial_iv.py`, `test_pricing_model.py`.
- Commits: SPEC+plan 1d62e31; bloque 1 3993b15 (1289 tests); bloque 2 48f7080 (1867); bloque 3 9316d45 (1929); bloque 4 a494c43 (2090); bloque 5 a9251f6 (2130); bloque 6 8fcdf05 (2194 + 2 skipped); bloque 7 0f28123 (2330 + 2 skipped).
- Cada bloque confirmado por una ejecución EVL independiente de vc-tester y aprobado por el usuario. PVL: primera pasada Gate BLOCKED (F1, F2, C1-C4) → 1 ciclo de suplemento → Gate PASS.
- Decisiones del usuario en EXECUTE: B7 (curva "hoy" 200/201); prueba escalada del pricer europeo; guarda de vega (< 1e-6); regla de precisión de IV (vega·0,05 < 0,005).

### What Was Skipped/Deferred
- Etapa B2 (comisión de cierre racional): diferida por el usuario; backlog `process/general-plans/backlog/close-fee-rational-close_20-11-26.md` con nota de las decisiones ya aceptadas (abandonar si valor ≤ comisión; patas cortas sin cambio; interruptor en Ajustes, activado por defecto).
- Siguiente etapa: C (datos reales/históricos).

### Test Gate Outcomes
- `.venv/bin/pytest -q`: 2330 passed, 2 skipped (EVL final, bloque 7). Cache equality, batched Greeks equal, timing AC-B13, edge cases AC-B14 y AppTest del selector: todos verdes.
- `requirements.txt` sin cambios; módulos `metrics.py`, `commissions.py`, `catalog.py`, `simulation.py`, `analyze()` intactos.
- Checklist manual de 8 ítems: OK por el usuario.
- Validadores (UPDATE PROCESS): `validate-all-context.mjs`, `validate-context-discovery.mjs`, `validate-plan-inventory.mjs`: ver resumen en el mensaje de entrega.

### Plan Deviations
- p fuera de [0,1] → límite determinista (no recorte); suelo intrínseco solo en mallas americanas; barrido europeo de un solo árbol limitado a σ ≤ 35 %, T ≤ 0,5 años (cubierto por la prueba escalada); exportaciones en el bloque 5; griegas de respaldo por desplazamientos de S/T cuando el árbol no se puede construir; IV americana llama a `crr_price` directamente; `functools` en la lista de imports permitidos; 2 skips legítimos; helpers de tests fijados a `pricing_model="black_scholes"` (una línea en `test_pricing.py`) sin cambiar números esperados; dos textos de avisos actualizados en el bloque 5.
- Rendimiento medido: prima 0,018 s; malla 401 puntos ~0,13-0,16 s; griegas/pata 0,047 s (agrupadas); IV americana ~0,18 s; iron condor `analyze` frío ~0,8 s, caliente 0,002 s.

### Test Infra Gaps Found
- Sin hueco de infraestructura nuevo; la persistencia entre pestañas y el diseño visual siguen siendo solo manuales (ya en Known Gaps).

### SPEC Achievement
AC-B1..AC-B16: todos **met** (criterios Fully-Automated por gates pytest verdes; Hybrid por gates automáticos más la checklist manual del usuario). Ningún criterio unmet ni basado solo en Known-Gap.

## SPEC Gaps
Ninguno de criterios. Huecos conocidos (no son criterios incumplidos): (1) el árbol recorta el put americano en K mientras la ruta sin volatilidad usa K·exp(−rT) > K para r < 0 en puts muy ITM a largo plazo (entradas exóticas; el valor del árbol es la cota americana correcta); (2) cada edición de spot/vol/días/strike es un `analyze` en frío de ~0,8 s para un iron condor de 4 patas (en caliente 0,002 s). Ambos documentados; sin stub de backlog separado (rendimiento aceptado por el usuario).

### Closeout Packet
1. Plan seleccionado: `process/general-plans/completed/etapa-b1-binomial_20-11-26/etapa-b1-binomial_PLAN_20-11-26.md` (antes en `active/`).
2. Clasificación: WITH_GAPS (EVL handoff: gates verdes; known_gaps: 2).
3. Qué se terminó: ver What Was Done.
4. Verificado vs no verificado: todo verificado; los 2 huecos son límites conocidos y aceptados.
4b. Validate-contract: VALIDATE ejecutado; `## Validate Contract` presente, Gate PASS tras 1 ciclo de suplemento.
5. Limpieza: contexto actualizado, plan cerrado, carpeta archivada; nota añadida al backlog de B2.
6. Siguiente estado válido: Etapa C (datos reales/históricos) como plan nuevo; B2 diferida.
7. Commit: commits de código ya hechos; los cambios de proceso de esta sesión son un commit de proceso aparte del orquestador (no se hizo commit aquí).
8. Regresión: plan único; suite completa 2330 passed + 2 skipped.
9. SPEC achievement: 16/16 met.

Drift score: (a) >=10 archivos +2, (d) carpeta de tarea archivada +1, (c) >=3 observaciones memorables +1 = 4 -> banda HIGH. Los 2 huecos no requieren código; sin archivos de harness/protocolo tocados.

### Forward Preview

#### Test Infra Found
Tests de tiempo con cotas holgadas, igualdad caché vs sin caché (1e-12), convención de fijar helpers a `pricing_model="black_scholes"`.

#### Blast Radius Changes
Tal como el plan; `functools` añadido al allowlist de imports de `binomial.py`.

#### Commands to Stay Green
`.venv/bin/pytest -q` (2330 passed + 2 skipped); `.venv/bin/pytest tests/test_app_smoke.py -q`.

#### Dependency Changes
Ninguna.

### Context Audit
- `process/context/all-context.md`: actualizado (estructura, API pública, comportamientos B1, decisiones B1-B7, huecos, estado).
- `process/context/tests/all-tests.md`: actualizado (3 archivos nuevos, 2330 + 2 skipped, convención de pines, tests de tiempo, huecos).
- `process/context/planning/all-planning.md`: revisado, sin cambios.
- Bloque de routing y descripciones de frontmatter sin cambios.
