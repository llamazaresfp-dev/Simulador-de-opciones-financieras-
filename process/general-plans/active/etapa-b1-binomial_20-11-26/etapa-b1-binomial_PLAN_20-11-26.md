---
name: etapa-b1-binomial PLAN
description: "Plan COMPLEX de la Etapa B1 (modelo binomial CRR para opciones americanas de Acción/ETF, con Black-Scholes seleccionable) de Laboratorio de Opciones, en 7 bloques secuenciales cada uno cerrado con pytest verde."
date: 20-11-26
status: active
complexity: complex
spec: process/general-plans/active/etapa-b1-binomial_20-11-26/etapa-b1-binomial_SPEC_20-11-26.md
---

# Plan: Etapa B1 — Modelo binomial para opciones americanas

**Date**: 20-11-26
**Complexity**: COMPLEX (un solo plan, un solo flujo de ejecución, 7 bloques secuenciales; no es phase program)
**Status**: ⏳ PLANNED (plan escrito 20-11-26; pendiente VALIDATE y EXECUTE)
**SPEC bloqueado**: `process/general-plans/active/etapa-b1-binomial_20-11-26/etapa-b1-binomial_SPEC_20-11-26.md` (AC-B1..AC-B16, decisiones B1–B6, huecos B-G1..B-G8)
**Entorno**: Python 3.12.3, `.venv` (numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0); línea base: 910 tests en verde (HEAD 33228b1; sin cambios sin confirmar salvo esta carpeta de tarea con el SPEC)

**TL;DR:** un módulo puro nuevo `opciones/binomial.py` (árbol CRR vectorizado) y un despachador en `pricing.py` (`uses_binomial`, `option_price`, `option_greeks`) hacen que primas automáticas, curva "hoy", griegas e IV de **Acción/ETF** salgan del árbol americano; **Índice** sigue en Black-Scholes con números idénticos. `Market` gana el último campo `pricing_model` ("binomial" por defecto o "black_scholes"), con un `st.radio` en Ajustes. Al vencimiento (P&L, métricas, PoP exacta, Monte Carlo) nada cambia. Cada bloque cierra con `.venv/bin/pytest -q` completo en verde.

**Clasificación de complejidad (mi decisión):** COMPLEX estándar (un archivo, un flujo de ejecución, mismo formato que el plan de la Etapa A): hay varios subsistemas (motor, validación, interfaz, IV, tests), pero los 7 bloques son secuenciales (comparten `pricing.py`, `payoff.py` y `__init__.py`) y caben honestamente en un solo archivo; no es phase program.

## Overview

La Etapa B1 sustituye Black-Scholes por el modelo binomial de Cox-Ross-Rubinstein (ejercicio americano) en todo lo que valora una opción **antes del vencimiento** para Acción y ETF: prima automática, curva "hoy", griegas de la posición y volatilidad implícita. El usuario puede volver a Black-Scholes desde Ajustes para comparar (por defecto: binomial). Índice (europeo) no cambia. Lo que ocurre al vencimiento no depende del ejercicio anticipado y no se toca. Sigue siendo una herramienta de estudio, no asesoría.

Contexto leído: `process/context/all-context.md`, `process/context/tests/all-tests.md`, `process/development-protocols/plan-lifecycle.md`, `implementation-standards.md`, el SPEC, el plan de la Etapa A (formato), `opciones/*.py`, `app.py`, `tests/*` y los scripts de investigación `crr.py`, `p.py`, `p2.py` del scratchpad (solo referencia; no se copian tal cual).

## Quick Links

- [Decisiones bloqueadas](#decisiones-bloqueadas-b1b7) · [Chosen Approach](#chosen-approach-y-por-qué-este-camino) · [Arquitectura](#arquitectura) · [Phase Completion Rules](#phase-completion-rules)
- [Acceptance Criteria](#acceptance-criteria) · [Touchpoints](#touchpoints) · [Public Contracts](#public-contracts) · [Blast Radius](#blast-radius)
- [Implementation Checklist (bloques 1–7)](#implementation-checklist) · [Verification Evidence](#verification-evidence) · [Matriz de trazabilidad](#matriz-de-trazabilidad-ac-b1ac-b16)
- [Risk Predictions](#risk-predictions) · [Out of Scope](#out-of-scope) · [Test Infra Improvement Notes](#test-infra-improvement-notes) · [Resume and Execution Handoff](#resume-and-execution-handoff) · [Validate Contract](#validate-contract)

## Status strip

| Bloque | Contenido | Estado |
|---|---|---|
| 1 | `Market.pricing_model` + `opciones/binomial.py` (precio, malla) + `tests/test_binomial.py` | ⏳ PLANNED |
| 2 | Despachador en `pricing.py`, cableado de `default_premium`/`payoff`/catálogo, tests existentes fijados a BS, `tests/test_pricing_model.py` | ⏳ PLANNED |
| 3 | Griegas del árbol (`crr_greeks`) + `position_greeks` + tests | ⏳ PLANNED |
| 4 | IV americana en `implied_vol.py` + `tests/test_binomial_iv.py` | ⏳ PLANNED |
| 5 | Avisos según modelo (`validation.py`) + exportaciones en `__init__.py` + tests | ⏳ PLANNED |
| 6 | Interfaz `app.py` (selector, etiquetas, caption) + smoke AppTest | ⏳ PLANNED |
| 7 | Rendimiento (AC-B13), casos límite (AC-B14), pytest completo, checklist manual | ⏳ PLANNED |

## Decisiones bloqueadas (B1–B7)

B1–B6 están en el SPEC (no se repiten; el SPEC manda). Decisión adicional confirmada por el usuario (20-11-26):

| # | Decisión |
|---|---|
| B7 | La curva "hoy" de Acción/ETF con binomial **promedia los árboles de 200 y 201 pasos** (≈59 ms para 401 puntos; diferencia con la prima de 500/501 pasos en el spot ≈ 0,0004–0,002 USD por acción; cota de test AC-B7 ≈ 0,02 USD por acción). |

**Resoluciones de ambigüedades del SPEC (registradas, vinculantes para EXECUTE):**

| Punto | Resolución |
|---|---|
| AC-B7 "200 pasos" | Se interpreta con B7: `crr_price_grid` promedia N=200 y N=201. Test: en el spot, \|grid − `crr_price`(500/501)\| ≤ 0,02 por acción en una malla de casos suaves. |
| AC-B8 vega/rho | Desplazamiento **central** ±0,01 con el precio promediado, dividido entre 2 (unidad "por 1 punto"). Caso de referencia (put S=K=100, r=4 %, q=1 %, σ=25 %, T=0,5 años = 182,5 días; reproducido en el scratchpad): delta −0,4422, gamma 0,0233, theta −0,01564/día (ya verificados), **vega central ≈ 0,2764** (SPEC 0,2763; tolerancia abs 5e-3), **rho central ≈ −0,1949** (el SPEC cita −0,1897, probablemente de un desplazamiento unilateral; tolerancia abs 1e-2 frente al SPEC y se fija el valor medido en el test). Se documenta la diferencia en el informe. |
| AC-B10 límite superior | Americano: call < S, put < K (sin descontar; el árbol nunca supera esos valores). Límite inferior = intrínseco sin descontar (estricto). |
| Campo/valores | `Market.pricing_model: str = "binomial"` (último campo, tras `q`); valores `"binomial"` / `"black_scholes"`. |
| AC-B11 PoP 0,5721 | La PoP exacta depende de las primas **de las patas**, no del modelo. Medido: iron condor del catálogo con primas BS → 0,5721; con primas binomiales automáticas → ≈ 0,5726 (no es regresión). El test construye las patas **una vez con mercado fijado a BS** y evalúa `exact_pop`/`simulate_scenario` con `Market` de ambos modelos → 0,5721 y Monte Carlo semilla 42 idénticos. |

## Chosen Approach y por qué este camino

**Chosen Approach (INNOVATE):** `opciones/binomial.py` puro (sin importar `pricing.py`, sin ciclos) con `_crr_values` vectorizado sobre un array de spots (inducción hacia atrás en 2-D con potencias de `u` precalculadas) y tres funciones públicas (`crr_price`, `crr_price_grid`, `crr_greeks`). `pricing.py` actúa de despachador y es el **único** sitio que decide el modelo; `default_premium`, `leg_pnl_today`/`pnl_today`, `position_greeks` e `implied_vol` pasan por él. Los caminos de vencimiento (`leg_pnl_expiry`, T=0) siguen en `bs_price`. `app.py` solo añade un selector y etiquetas.

**Why This Over Alternatives:**
- *Reemplazar `bs_price` por el árbol en todas partes* → rompería Índice, los tests de Hull de BS y el comportamiento al vencimiento; el despachador mantiene BS intacto.
- *Elegir el modelo con un parámetro suelto en cada función* → obliga a propagarlo por 6 llamadas; un campo en `Market` viaja con los datos globales y no cambia las firmas existentes.
- *N=1000 sobre la malla* → 2,7 s: inviable (B-G1); 200/201 pasos para "hoy" y 500/501 para primas/griegas.
- *Griegas solo por recálculo* → delta/gamma/theta salen gratis de los nodos (1,·) y (2,·) del mismo árbol; solo vega/rho necesitan recalcular.
- *Un solver propio de IV americana con Newton* → inestable con vega ≈ 0; `brentq` sobre el precio del árbol tras comprobar límites e identificabilidad es robusto (mismo patrón que la Etapa A).
- *Leisen-Reimer u otros árboles* → fuera de alcance (SPEC).

**Key Constraints Accepted:**
- Nivel básico de Python: funciones cortas, dataclasses, comentarios/docstrings en español, identificadores en inglés.
- El árbol es una aproximación con oscilación residual aun promediando N/N+1 (B-G3); se avisa.
- Dividendos continuos solamente (B-G4); sin dependencias nuevas; `requirements.txt` sin cambios.

## Arquitectura

```
app.py (solo dibuja: radio "Binomial (americano)" / "Black-Scholes (europeo)", etiquetas, caption)
   │ API pública
   ▼
opciones/__init__.py ── (Etapa A intacta) + uses_binomial, option_price, option_greeks, crr_price, crr_price_grid, crr_greeks
   ├─ models.py      Market + pricing_model (último campo) + constantes PRICING_BINOMIAL / PRICING_BLACK_SCHOLES   [MODIFICAR, bloque 1]
   ├─ binomial.py    _crr_values, crr_price, crr_price_grid, crr_greeks (NO importa pricing.py)                    [NUEVO, bloques 1 y 3]
   ├─ pricing.py     bs_price/bs_greeks (intactos) + uses_binomial, option_price, option_greeks, default_premium    [MODIFICAR, bloques 2-3]
   ├─ payoff.py      leg_pnl_today → option_price; position_greeks → option_greeks; vencimiento sigue en bs_price [MODIFICAR, bloques 2-3]
   ├─ implied_vol.py rama americana (uses_binomial) + MSG_AMERICAN_*; rama europea sin cambios                    [MODIFICAR, bloque 4]
   └─ validation.py  avisos según modelo; validate_market rechaza pricing_model desconocido                      [MODIFICAR, bloque 5]
```

Flujo del árbol CRR (`_crr_values`): `dt = T/N`, `u = e^(σ√dt)`, `d = 1/u`, `p = (e^((r−q)dt) − d)/(u − d)`, descuento `e^(−r·dt)`. Hojas: `S·u^(2j−N)`, `j = 0..N`; hacia atrás: `V = disc·(p·V[j+1] + (1−p)·V[j])` y, si americano, `V = max(V, intrínseco del nodo)`. Vectorizado sobre un array de spots (matriz spots × nodos; potencias de `u` precalculadas una vez).

- **Guardas (sin NaN, sin excepciones):** `T ≤ 0` → intrínseco; `σ ≤ 0` → `max(intrínseco, límite forward determinista)`; `p` fuera de [0,1] (σ muy baja con `|r−q|√dt > σ`) → se recorta a [0,1]; si `u − d` es ~0 (σ√dt subdesbordado) → límite forward/intrínseco; desbordamiento de `u^N` con σ·√(T·N) enorme → exponente recortado o resultado acotado por el límite superior (call S, put K) y siempre finito; pasos limitados para vencimientos muy cortos: `N_efectivo = min(N, max(2, ceil(días·50)))` (y el promedio usa `N_efectivo` y `N_efectivo+1`); resultado de la malla con suelo en el intrínseco.
- **Promedios:** `crr_price` = media de N=500 y N=501; `crr_price_grid` = media de N=200 y N=201 (B7).
- **Griegas (`crr_greeks`)**: del árbol de cada N∈{500,501} (promediando): `delta = (V(1,1) − V(1,0))/(S·u − S·d)`, `gamma` con los tres nodos (2,·) (diferencia de deltas / media de los dos intervalos de S), `theta = (V(2,1) − V(0,0))/(2·dt)` por año → `/365` por día. `vega = (P(σ+0,01) − P(σ−0,01))/2` y `rho = (P(r+0,01) − P(r−0,01))/2` con el precio promediado; si `σ − 0,01 < MIN_VOL`: vega unilateral `P(σ+0,01) − P(σ)`. Con `T ≤ 0` o `σ ≤ 0` lanza `ValueError` (igual que `bs_greeks`), y `position_greeks` mantiene su comportamiento actual de devolver `None`.

Flujo de `implied_vol(leg, market)` con `uses_binomial(market)` (comprobaciones **en este orden**): acción → días = 0 → prima ≤ 0 → datos inválidos → límites americanos (inferior = intrínseco, estricto; superior = S call / K put) → identificabilidad → `brentq(f, VOL_LOW, VOL_HIGH, xtol=1e-8)` con `f(σ) = crr_price(σ) − prima`. Prima < intrínseco (fuera de tolerancia) → mensaje "por debajo del intrínseco"; prima ≤ intrínseco·(1+1e-6)+1e-9 o `f(VOL_LOW) ≥ 0` (precio plano en σ) → `MSG_AMERICAN_NOT_IDENTIFIABLE` ("No se puede identificar la IV: con esta prima el precio del modelo no depende de la volatilidad (ejercicio anticipado óptimo)."), comprobado **antes** de `brentq`; prima ≥ límite superior → mensaje existente "por encima"; `f(VOL_HIGH) < 0` o fallo de `brentq` → `MSG_SOLVER_FAILED`. Nunca lanza. La rama europea (Índice o `black_scholes`) queda idéntica a la Etapa A.

## Phase Completion Rules

A phase is NOT complete until:

1. **Integration Test** - el bloque funciona con los anteriores y con los 910 tests existentes (`.venv/bin/pytest -q` completo)
2. **Manual Test** - el usuario puede reproducir valores de referencia con `.venv/bin/python -c ...` (bloques 1–5) y la checklist manual (bloques 6–7)
3. **Data Verification** - valores de referencia de Hull (7,4284; 4,4885), BS N=1000 (6,2384 vs 6,2402) y griegas del put ATM recalculados **con los datos exactos** de cada test (lección de Etapa A: recalcular las cifras de referencia, no copiarlas de un prototipo con otras entradas)
4. **Error Handling** - entradas límite devuelven valores finitos o mensajes en español, nunca NaN, infinitos ni excepciones hacia la UI
5. **User Confirmation** - el usuario dice "funciona"

Status: ⏳ PLANNED · 🔨 CODE DONE · 🧪 TESTING · ✅ VERIFIED · 🚧 BLOCKED.

Regla honesta: un bloque con tests verdes y sin revisión del usuario es `🔨 CODE DONE`, no `✅ VERIFIED`. Solo el usuario pasa un bloque a `✅ VERIFIED`. **Lección del MVP/Etapa A:** vc-execute-agent no puede escribir bajo `process/`; las actualizaciones de estado de los bloques en este plan y el reporte se hacen en UPDATE PROCESS.

Reporte (lo crea EXECUTE/UPDATE PROCESS, no este plan): `process/general-plans/active/etapa-b1-binomial_20-11-26/etapa-b1-binomial_REPORT_20-11-26.md`.

## Acceptance Criteria

Se heredan literalmente **AC-B1..AC-B16 del SPEC** (no se reescriben). Interpretaciones fijadas por este plan (ver tabla de resoluciones arriba):

- **AC-B1:** referencias de Hull con el árbol **sin promediar** (`american=True`, N=2 y N=5) vía `_crr_values` (función interna importable en tests).
- **AC-B2:** "europeo → BS" usa `american=False`, N=1000 (tolerancia 2e-3 solo en el put de referencia S=K=100, r=4 %, q=1 %, σ=25 %, T=0,5 — error observado 1,745e-3; **3e-3** en el barrido de casos europeo vs BS); call americano q=0 = europeo (tolerancia 1e-9 sobre el mismo árbol); prima de ejercicio anticipado ≥ −1e-12 en la malla; put profundo ITM = intrínseco; límites de paridad americana `S·e^(−qT) − K ≤ C − P ≤ S − K·e^(−rT)` con tolerancia 1e-6 (el árbol promediado puede rozar el borde).
- **AC-B3:** "promedio reduce el error" se prueba con referencia de alta precisión (árbol europeo N=4000 o BS) sobre casos suaves: el promedio 500/501 supera al N solo en **≥ 80 %** de los casos del barrido (medido 22 de 24) y su error es ≤ **5e-3** frente a la referencia de 2000/2001 pasos o BS (peor medido 3,2e-3 en put K=110, σ=40 %, T=1 año).
- **AC-B7:** ver B7; además valor ≥ intrínseco − 1e-12 en toda la malla y sin NaN.
- **AC-B8:** ver tabla; `position_greeks` = suma de las de cada pata (con `size = side·quantity·multiplier`), `None` con días = 0 o vol ≤ 0 (igual que hoy).
- **AC-B9 / AC-B10:** ida y vuelta medida en precio (|crr_price(IV) − prima| ≤ 1e-6) y en σ (|IV − σ| ≤ 1e-4 **solo donde vega > 0,01 y prima > intrínseco·(1+1e-6)+1e-9**; el ida y vuelta en precio se afirma siempre; los casos de precio plano en σ (intrínseco) afirman `MSG_AMERICAN_NOT_IDENTIFIABLE`; el call ITM a 1 día (K=90, σ=25 %) es región mal condicionada/no identificable esperada: ida y vuelta en precio sí, error de σ hasta ≈ 0,15 permitido); `MSG_AMERICAN_NOT_IDENTIFIABLE` para prima = intrínseco (p. ej. put S=100, K=140, T=1 año, σ=20 %: precio = 40 = intrínseco).
- **AC-B11:** ver tabla (PoP 0,5721 con patas BS-fijadas y `Market` de ambos modelos).
- **AC-B12:** textos exactos en la sección de validación del bloque 5; se prueban por subcadena clave.
- **AC-B13 (cotas y mitigación obligatoria):** prima 500/501 < 0,25 s; curva "hoy" 401 puntos 200/201 < 1,0 s; IV americana < 2,0 s; iron condor de 4 patas `analyze()` en frío < 2,0 s (cota de regresión; presupuesto medido ≈ 0,65 s en frío, IV ≈ 0,15 s por resolución) y **segundo `analyze()` idéntico (caché caliente) < 0,3 s**. La memoización (`lru_cache` acotado) y los árboles de vega/rho agrupados son **obligatorios** (bloque 7), no contingentes; los tiempos frío/caliente se miden y se reportan.
- **AC-B15:** el test en subproceso se extiende a `opciones.binomial`; `requirements.txt` sin cambios (`git diff requirements.txt` vacío).
- **AC-B16:** los tests que suponían primas BS para Acción/ETF se fijan con `pricing_model="black_scholes"` en sus helpers `Market` (cambio explícito, listado en el informe con justificación). Los tests de referencia BS conservan sus valores esperados sin cambios; solo se fija el helper (`tests/test_pricing.py::make_market`, una línea; `git diff -U0 tests/test_pricing.py` solo cambia esa línea). Nunca se cambia un número esperado para que pase un test: solo se fijan helpers.

## Touchpoints

| Bloque | Archivo | Acción |
|---|---|---|
| 1 | `opciones/models.py` | modificar (`Market.pricing_model` como **último** campo; constantes `PRICING_BINOMIAL`, `PRICING_BLACK_SCHOLES`, `PRICING_MODELS`) |
| 1 | `opciones/binomial.py` | crear (`_crr_values`, `crr_price`, `crr_price_grid`; constantes de pasos) |
| 1 | `tests/test_binomial.py` | crear (oráculos AC-B1..AC-B3, AC-B7 parte pura) |
| 2 | `opciones/pricing.py` | modificar (`uses_binomial`, `option_price`; `default_premium` pasa por `option_price`; `bs_price`/`bs_greeks` intactos) |
| 2 | `opciones/payoff.py` | modificar (`leg_pnl_today` usa `option_price`; `leg_pnl_expiry` NO se toca) |
| 2 | `tests/test_pricing.py`, `tests/test_legs_payoff.py`, `tests/test_simulation.py`, `tests/test_catalog.py`, `tests/test_analyze.py`, `tests/test_implied_vol.py`, `tests/test_app_smoke.py` | modificar (fijar `pricing_model="black_scholes"` en los helpers `make_market`/`Market` donde se asumen primas BS; `test_pricing.py`: una sola línea en `make_market`, los tests Hull de `bs_price`/`bs_greeks` intactos; `test_simulation.py`: `test_long_put_matches_n_minus_d2` usa `build_legs` → `default_premium` (PoP 0,3497 binomial vs 0,3508 BS); `test_catalog.py`: el test del iron condor pasa por poco con binomial (4,8e-4 vs 5e-4), fijar su helper; verificar uno a uno) |
| 2 | `tests/test_metrics.py`, `tests/test_commissions.py`, `tests/test_validation.py` | verificar; modificar solo si fallan, solo fijando helpers y con justificación (previsto: `test_validation.py` en el bloque 5) |
| 2 | `tests/test_pricing_model.py` | crear (despachador, canario, Índice idéntico, BS fijado = Etapa A, regresión vencimiento/PoP/MC) |
| 3 | `opciones/binomial.py` | modificar (`crr_greeks`) |
| 3 | `opciones/pricing.py`, `opciones/payoff.py` | modificar (`option_greeks`; `position_greeks` lo usa) |
| 3 | `tests/test_binomial.py`, `tests/test_pricing_model.py` | ampliar (griegas) |
| 4 | `opciones/implied_vol.py` | modificar (rama americana, `MSG_AMERICAN_NOT_IDENTIFIABLE`, `MSG_AMERICAN_BELOW_INTRINSIC`) |
| 4 | `tests/test_binomial_iv.py` | crear |
| 5 | `opciones/validation.py` | modificar (`market_warnings`, `scenario_warnings` según modelo; `validate_market` rechaza `pricing_model` desconocido) |
| 5 | `opciones/__init__.py` | modificar (exportar `uses_binomial`, `option_price`, `option_greeks`, `crr_price`, `crr_price_grid`, `crr_greeks`; **no** exportar nada llamado `binomial`) |
| 5 | `tests/test_validation.py`, `tests/test_analyze.py` | modificar/ampliar (avisos; subproceso sin Streamlit con `opciones.binomial`) |
| 6 | `app.py` | modificar (`init_state`, `market_from_state`, radio en Ajustes, etiquetas "↺ binomial"/"↺ BS", caption del modelo activo) |
| 6 | `tests/test_app_smoke.py` | modificar/ampliar (selector) |
| 7 | `tests/test_binomial.py`, `tests/test_pricing_model.py` | ampliar (rendimiento, casos límite) |
| Cierre | `process/context/all-context.md`, `process/context/tests/all-tests.md` | modificar en UPDATE PROCESS (no en EXECUTE de código) |

Solo lectura / sin tocar: `opciones/metrics.py`, `commissions.py`, `catalog.py`, `simulation.py`; `analyze()` y `Analysis` en `opciones/__init__.py`; `requirements.txt`; el SPEC.

## Public Contracts

| Elemento | Contrato |
|---|---|
| `Market.pricing_model` | `str`, **último** campo con valor por defecto `"binomial"` (tras `q`); `"binomial"` / `"black_scholes"`. Los constructores existentes (posicionales y por nombre) siguen válidos. |
| `uses_binomial(market) -> bool` | True si y solo si `market.underlying in {"Acción","ETF"}` y `market.pricing_model == "binomial"`. Cualquier otra cosa (Índice, `black_scholes`, valor desconocido) → False. |
| `option_price(kind, market, strike, S=None, sigma=None)` | `S` por defecto `market.spot`; `sigma` por defecto `market.vol`; T = `market.T`. Binomial: `S` escalar → `crr_price` (500/501), `S` array → `crr_price_grid` (200/201, ≥ intrínseco). Si no, `bs_price`. Devuelve float o array como `bs_price`. |
| `option_greeks(kind, market, strike) -> dict` | Claves `delta, gamma, theta, vega, rho` y unidades de `bs_greeks` (theta por día; vega y rho por 1 punto). Lanza `ValueError` con T ≤ 0 o σ ≤ 0 (como `bs_greeks`). |
| `crr_price(kind, S, K, r, q, sigma, T, steps=500, american=True) -> float` | Promedio de N y N+1 pasos; guardas sin NaN. |
| `crr_price_grid(kind, S_array, K, r, q, sigma, T, steps=200, american=True) -> ndarray` | Promedio de N y N+1 sobre el array; suelo en el intrínseco. |
| `crr_greeks(kind, S, K, r, q, sigma, T) -> dict` | Ver Arquitectura. |
| `default_premium(kind, market, strike)` | Misma firma; devuelve la prima del modelo activo (0.0 ante datos inválidos, como hoy). |
| `implied_vol(leg, market) -> IVResult` | Misma firma; rama americana con `uses_binomial`; nunca lanza; nuevos mensajes `MSG_AMERICAN_NOT_IDENTIFIABLE`, `MSG_AMERICAN_BELOW_INTRINSIC`. |
| `market_warnings(market)`, `scenario_warnings(market)` | Misma firma; texto según modelo y subyacente (AC-B12). Índice sin cambios. |
| `analyze()`, `Analysis`, `pnl_expiry`, `compute_metrics`, `exact_pop`, `simulate_scenario` | **Sin cambios.** Con `pricing_model="black_scholes"` o Índice todos los números coinciden con la Etapa A. |
| `app.py` | Estado nuevo `pricing_model` (clave simple, por defecto `"binomial"`); widget `pricing_model_input`. |

## Blast Radius

- **Riesgo:** medio. Cambia el resultado numérico por defecto de Acción/ETF (primas automáticas, curva "hoy", griegas, IV), no la lógica de vencimiento. Superficie: 1 módulo nuevo, 5 módulos del motor modificados (`models.py`, `pricing.py`, `payoff.py`, `implied_vol.py`, `validation.py`), `__init__.py`, `app.py`, 4 archivos de test nuevos y ~8 de test modificados (incl. `test_pricing.py` y `test_simulation.py`, solo helpers).
- **No tocar:** `analyze()`/`Analysis`, `metrics.py`, `simulation.py`, `commissions.py`, `catalog.py`, `requirements.txt`; en `tests/test_pricing.py` solo se permite la línea del helper `make_market` (`pricing_model="black_scholes"`), cualquier ruta bajo `process/`, `.claude/`, `.codex/`, `.agents/`.
- **Efecto en cadena:** las primas automáticas de `build_legs` y `refresh_auto_prices` cambian de valor con el modelo por defecto; por eso la PoP exacta con primas binomiales automáticas se mueve ≈ 0,0005 (no es regresión). Las primas editadas a mano se conservan.
- **Rollback:** todo el trabajo se revierte quitando `binomial.py`, el despachador y el campo `pricing_model`; `pricing_model="black_scholes"` reproduce la Etapa A en tiempo de ejecución sin tocar código.

## Implementation Checklist

Orden estricto; cada bloque termina con pytest verde. Reglas transversales: TDD (tests primero, en rojo), funciones cortas, comentarios en español, `pytest.approx` en floats, ningún `print` en el motor, `binomial.py` NO importa `pricing.py`, no modificar `analyze()`/`Analysis`/`metrics.py`/`simulation.py`/`requirements.txt` (de `tests/test_pricing.py` solo la línea del helper `make_market`).

### Bloque 1 — Campo del modelo y precio binomial (AC-B1, AC-B2, AC-B3, AC-B7 parcial, AC-B15 parcial)

**Explicación para el usuario:** un árbol binomial es una "malla" de precios posibles de la acción: en cada paso el precio sube o baja una cantidad fija, y se calcula el valor de la opción yendo desde el vencimiento hacia hoy. En cada nodo, si ejercer ya vale más que esperar, se ejerce (eso es lo "americano"). Construimos esa malla con numpy, la comprobamos contra valores de libro (Hull) y contra Black-Scholes, y añadimos a `Market` un campo para elegir el modelo.

- [ ] Ejecutar `date +%d-%m-%y` y `.venv/bin/python -c "import numpy, scipy, plotly, streamlit, pytest; print(numpy.__version__, scipy.__version__, plotly.__version__, streamlit.__version__, pytest.__version__)"`; confirmar `.venv/bin/pytest -q` → 910 passed antes de tocar nada.
- [ ] Crear `tests/test_binomial.py` (en rojo): Hull `_crr_values('put', [50], 52, .05, 0, .30, 2, 2, True)` → 7,4284 y `('put',[50],50,.10,0,.40,5/12,5,True)` → 4,4885 (`pytest.approx(abs=5e-4)`); europeo N=1000 vs `bs_price` en el put de referencia (S=K=100, r=4 %, q=1 %, σ=25 %, T=0,5: tolerancia 2e-3; **recalcular** el valor con estas entradas exactas antes de fijar cifras); call americano con q=0 = europeo del mismo árbol (1e-9); prima de ejercicio anticipado ≥ −1e-12 en malla (call/put × S × K × T × σ × r × q); put profundo ITM = intrínseco; límites de paridad americana (1e-6); promedio N/N+1 reduce el error frente a un solo N en casos suaves (referencia: árbol europeo N=4000 o BS); `crr_price` usa 500/501 pasos y `crr_price_grid` 200/201 (verificable con constantes); `crr_price_grid` ≥ intrínseco y sin NaN; `T ≤ 0` → intrínseco; `σ ≤ 0` → `max(intrínseco, forward)`; `p` fuera de [0,1] (σ = 1e-6 con `r−q` grande) sin NaN; el motor importa sin Streamlit (parte de AC-B15, en el bloque 5 se amplía el subproceso).
- [ ] Modificar `opciones/models.py`: constantes `PRICING_BINOMIAL = "binomial"`, `PRICING_BLACK_SCHOLES = "black_scholes"`, `PRICING_MODELS`; añadir `pricing_model: str = PRICING_BINOMIAL` como **último** campo de `Market` (tras `q`) y documentarlo en el docstring.
- [ ] Crear `opciones/binomial.py` (docstring en español explicando CRR y el promedio N/N+1): `_crr_values(kind, S_array, K, r, q, sigma, T, N, american)` vectorizado sobre `S_array` (matriz spots × nodos, potencias de `u` precalculadas, `np.errstate` controlado), `_effective_steps(N, T)` (tope por vencimientos cortos), `crr_price` (escalar; promedio 500/501) y `crr_price_grid` (array; promedio 200/201; suelo en el intrínseco). Todas las guardas de la sección Arquitectura. NO importar `opciones.pricing`.
- [ ] Comando: `.venv/bin/pytest tests/test_binomial.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** tests nuevos verdes; 910 existentes verdes (el campo nuevo no cambia nada porque aún nadie lo lee); Hull con error ≤ 5e-4.

### Bloque 2 — Despachador y cableado de primas / curva "hoy" (AC-B4, AC-B5, AC-B7, AC-B11, AC-B16)

**Explicación para el usuario:** hasta ahora todo pasaba por Black-Scholes. Creamos un "interruptor" (`uses_binomial`) y una función única `option_price` que elige modelo según el subyacente y el ajuste. Las primas automáticas y la curva "hoy" pasan por ahí; el vencimiento no. Los tests viejos que daban por hecho Black-Scholes en acciones se fijan explícitamente a ese modelo, y añadimos un test "canario" que garantiza que, sin fijar nada, una acción usa el binomial.

- [ ] Modificar `opciones/pricing.py`: `uses_binomial(market)`, `option_price(kind, market, strike, S=None, sigma=None)` (S escalar → `crr_price`; array → `crr_price_grid`; si no → `bs_price`); `default_premium` pasa por `option_price` conservando su manejo de errores (`TypeError`, `ValueError`, no finito → 0.0). `bs_price`/`bs_greeks` sin cambios.
- [ ] Modificar `opciones/payoff.py`: `leg_pnl_today` usa `option_price(leg.kind, market, leg.strike, S_arr)`; `leg_pnl_expiry` queda con `bs_price(..., 0.0)`; ajustar docstrings.
- [ ] Fijar `pricing_model="black_scholes"` en los helpers `Market` que asumen primas BS para Acción/ETF: `tests/test_pricing.py` (`make_market`, **una línea**: sin ella fallan `test_default_premium_equals_bs_price` y `test_default_premium_reference_value`; los tests Hull de `bs_price`/`bs_greeks` y todos los valores esperados quedan intactos), `tests/test_legs_payoff.py` (helper de la línea ~21 y `Market` de la línea ~170), `tests/test_simulation.py` (`make_market`: `test_long_put_matches_n_minus_d2` obtiene PoP 0,3497 con primas binomiales vs 0,3508 fijado, porque `build_legs` usa `default_premium`; el comentario previo "no dependen de primas automáticas" era falso), `tests/test_implied_vol.py` (helper ~36), `tests/test_analyze.py` (helper `market()` ~35), `tests/test_catalog.py` (helper ~44; el test del iron condor pasa por poco con binomial, 4,8e-4 vs 5e-4: fijarlo igualmente), `tests/test_app_smoke.py` solo donde se afirmen primas concretas (la app por defecto usa binomial: `expected_iv_pct` ~373 debe fijarse al **mismo** modelo que la app que se prueba). Verificar y justificar caso por caso (`test_metrics.py`, `test_commissions.py` se esperan sin cambios).
- [ ] **Barrido con el despachador:** con el despachador ya cableado, ejecutar `.venv/bin/pytest -q` completo y corregir cualquier fallo restante por suposición BS **únicamente fijando helpers** (`pricing_model="black_scholes"`), **nunca** cambiando números esperados; listar cada test/helper fijado con su justificación en el informe del bloque (la emulación previa dio 5 fallos: 2 en `test_pricing.py`, 2 en `test_legs_payoff.py`, 1 en `test_simulation.py`).
- [ ] Crear `tests/test_pricing_model.py`: tabla de verdad de `uses_binomial` (Acción/ETF/Índice × modelos, valor desconocido → False); **canario**: `Market("Acción", ...)` sin `pricing_model` → `default_premium` = `crr_price` y ≠ `bs_price`; Índice con ambos selectores = `bs_price` exacto (primas, curva "hoy" y, tras el bloque 3, griegas); `black_scholes` en Acción/ETF = valores del motor BS existente (primas, `leg_pnl_today`); curva "hoy" binomial: en el spot |grid − `crr_price`| ≤ 0,02 por acción (B7), ≥ intrínseco, sin NaN; regresión de vencimiento: `pnl_expiry`, `compute_metrics` idénticos con ambos modelos y mismas patas; PoP exacta del iron condor del catálogo con patas construidas con mercado BS = 0,5721 evaluada con `Market` de **ambos** modelos; `simulate_scenario` con semilla 42 idéntico entre modelos.
- [ ] Comando: `.venv/bin/pytest tests/test_pricing_model.py tests/test_binomial.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** pytest completo verde; lista de tests modificados con su justificación anotada para el informe; ningún test de Índice cambia; `git diff -U0 tests/test_pricing.py` muestra únicamente la línea del helper (ningún valor esperado cambia en ningún test).

### Bloque 3 — Griegas del árbol y de la posición (AC-B8)

**Explicación para el usuario:** las griegas dicen cuánto cambia la prima si algo se mueve. Delta y gamma salen de los primeros nodos del árbol (cómo cambia el valor si el precio sube o baja); theta, de comparar el valor hoy con el valor dos pasos después. Vega y rho se obtienen "empujando" un poco la volatilidad o la tasa y volviendo a calcular. Las unidades son las de siempre: theta por día, vega y rho por 1 punto porcentual.

- [ ] Ampliar `tests/test_binomial.py` y `tests/test_pricing_model.py` (en rojo): caso de referencia put S=K=100, r=4 %, q=1 %, σ=25 %, T=182,5/365 con N=500/501: delta −0,4422, gamma 0,0233, theta −0,01564/día (abs 5e-4 en delta y theta, 2e-4 en gamma), vega central ≈ 0,2764 (abs 5e-3), rho central ≈ −0,1949 (abs 1e-2 frente al −0,1897 del SPEC; documentar la diferencia); signos y rangos (delta put ∈ [−1,0], delta call ∈ [0,1], gamma ≥ 0, vega ≥ 0) en una malla; **el árbol europeo ≈ BS** en griegas (rel ≲ 1e-2, `american=False` en un helper interno) para confirmar fórmulas; vega con `σ − 0,01 < MIN_VOL` usa la diferencia unilateral y es finita; `T ≤ 0` o `σ ≤ 0` → `ValueError`; `position_greeks` binomial = suma de patas con `size = side·quantity·multiplier` (la pata de acción solo aporta delta); días = 0 o vol ≤ 0 → `None`; Índice y BS fijado = `bs_greeks` exacto.
- [ ] Modificar `opciones/binomial.py`: `crr_greeks(kind, S, K, r, q, sigma, T)` (nodos (1,·) y (2,·) del árbol americano; promedio N=500/501; vega/rho centrales con el precio promediado; ver Arquitectura).
- [ ] Modificar `opciones/pricing.py` (`option_greeks`) y `opciones/payoff.py` (`position_greeks` pasa por `option_greeks`, manteniendo el control de `T ≤ 0`/`vol ≤ 0` → `None`).
- [ ] Comando: `.venv/bin/pytest tests/test_binomial.py tests/test_pricing_model.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** referencias dentro de tolerancia (con las cifras **recalculadas** y registradas en el test); `analyze().greeks` coherente con la suma de patas; suite completa verde.

### Bloque 4 — Volatilidad implícita americana (AC-B9, AC-B10)

**Explicación para el usuario:** la IV debe usar el mismo modelo que la prima. Con el árbol americano el "suelo" de una opción es su valor intrínseco, y un put muy dentro del dinero vale justo eso sin importar la volatilidad: ahí la IV no se puede identificar y la app lo dice en español en vez de inventar un número. Si la prima sí depende de σ, un buscador de raíces la encuentra.

- [ ] Crear `tests/test_binomial_iv.py` (en rojo): ida y vuelta prima del árbol → IV → prima del árbol en puts y calls ATM/OTM/ITM, σ ∈ {10 %, 25 %, 60 %}, T ∈ {1 d, 45 d, 1 año}: el ida y vuelta en **precio** (|Δprecio| ≤ 1e-6) se afirma siempre; el error en σ (|IV − σ| ≤ 1e-4) **solo donde vega > 0,01 y prima > intrínseco·(1+1e-6)+1e-9**; los casos de precio plano en σ (p. ej. puts ITM, S=100/K=110, igual al intrínseco) afirman `vol is None` y `MSG_AMERICAN_NOT_IDENTIFIABLE` en lugar de esperar ida y vuelta; el call ITM a 1 día (K=90, σ=25 %) es una región mal condicionada esperada (ida y vuelta en precio sí, σ desviada ≈ 0,15 con vega ≈ 0) y se documenta en el test; prima = `crr_price` con `market.vol` → IV ≈ `market.vol`; Índice o `black_scholes` → IV idéntica a `implied_vol` de la Etapa A (valores calculados con `bs_price`); prima = intrínseco (put S=100, K=140, T=1 año, σ=20 %) → `vol is None` y mensaje `MSG_AMERICAN_NOT_IDENTIFIABLE`; prima < intrínseco → `MSG_AMERICAN_BELOW_INTRINSIC`; prima ≥ S (call) o ≥ K (put) → mensaje "por encima"; días = 0, pata de acción, prima ≤ 0, datos no numéricos → mensajes de siempre; los mensajes son distintos entre sí; **nunca lanza** (NaN, None, strike 0, σ extremas); `vol` y `message` mutuamente excluyentes.
- [ ] Modificar `opciones/implied_vol.py`: nuevas constantes `MSG_AMERICAN_NOT_IDENTIFIABLE` (texto exacto del SPEC/INNOVATE) y `MSG_AMERICAN_BELOW_INTRINSIC`; `_american_bounds(kind, market, strike)`; rama `if uses_binomial(market)` tras las comprobaciones comunes (acción → días → prima → datos); identificabilidad **antes** de `brentq`; `brentq` sobre `crr_price` con `xtol=1e-8`; fallo de bracket o `ValueError` → mensaje; la rama europea queda byte a byte igual.
- [ ] Comando: `.venv/bin/pytest tests/test_binomial_iv.py tests/test_implied_vol.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** ningún camino de IV lanza excepción; la IV europea no cambia; suite completa verde.

### Bloque 5 — Avisos según modelo y exportaciones (AC-B12, AC-B15)

**Explicación para el usuario:** los avisos ahora dicen la verdad sobre el modelo activo: con binomial, que las primas son de un modelo americano aproximado; con Black-Scholes en acciones/ETF, que subvalora los puts americanos (error típico 1–8 %, medido hasta ~24 %); en índices, que son europeas. El aviso de escenarios aclara que solo queda el modelo lognormal de precio final, donde el ejercicio anticipado no importa al vencimiento.

- [ ] Actualizar `tests/test_validation.py` (en rojo): `market_warnings` — binomial activo (Acción/ETF) menciona modelo americano / aproximación binomial para primas, "hoy", griegas e IV; `black_scholes` (Acción/ETF) menciona que subvalora los puts americanos con "1–8 %" y "24 %"; Índice con cualquier selector = texto europeo existente; siempre "no es asesoría"/estudio y comisión de cierre; `scenario_warnings` — Acción/ETF dicen que solo queda el modelo lognormal de precio final de estilo europeo (ejercicio anticipado irrelevante al vencimiento) independientemente del selector; Índice sin cambios; `validate_market` rechaza un `pricing_model` desconocido con mensaje en español y acepta ambos válidos; cualquier test existente que afirme el texto antiguo de `MSG_AMERICAN`/`MSG_SCENARIO_AMERICAN` se actualiza de forma explícita (anotar en el informe).
- [ ] Modificar `opciones/validation.py`: nuevos textos (`MSG_BINOMIAL_ACTIVE`, `MSG_AMERICAN` actualizado para BS en Acción/ETF con "error típico 1–8 %, medido hasta ~24 %", `MSG_SCENARIO_AMERICAN` actualizado, `MSG_BAD_PRICING_MODEL`); `market_warnings` lee `getattr(market, "pricing_model", PRICING_BINOMIAL)`; mantiene "modelo ≠ predicción", colas gruesas y "no es asesoría".
- [ ] Modificar `opciones/__init__.py`: importar y exportar (`__all__`, orden alfabético) `crr_greeks`, `crr_price`, `crr_price_grid`, `option_greeks`, `option_price`, `uses_binomial`. **Nunca** una función llamada `binomial` (sombrearía el submódulo, mismo gotcha que `implied_vol`). Ampliar el test en subproceso de `tests/test_analyze.py` con `opciones.binomial` (sin Streamlit); `git diff requirements.txt` vacío.
- [ ] Comando: `.venv/bin/pytest tests/test_validation.py tests/test_analyze.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** avisos correctos por modelo y subyacente; motor importable sin Streamlit; suite completa verde.

### Bloque 6 — Interfaz, smoke tests y revisión manual (AC-B6, AC-B12 parcial, AC-B14 parcial; Hybrid)

**Explicación para el usuario:** en la pestaña Ajustes aparece una elección "Binomial (americano) / Black-Scholes (europeo)" con una frase que explica para qué sirve. Al cambiarla, se recalculan las primas automáticas, la curva "hoy" y las griegas; las primas que escribiste a mano se respetan. Con Índice la elección no tiene efecto y se indica. El botón de cada pata dice "↺ binomial" o "↺ BS" según el modelo activo.

- [ ] Ampliar `tests/test_app_smoke.py` (en rojo): por defecto `session_state["pricing_model"] == "binomial"` y las primas automáticas de una Acción coinciden con `default_premium` del motor con `Market` binomial; el radio `pricing_model_input` existe con las dos opciones; cambiarlo a Black-Scholes (AppTest `at.radio(key="pricing_model_input").set_value(...)`) recalcula las primas automáticas a los valores BS y **conserva** una prima manual; con Índice las primas no cambian al alternar y aparece el texto "no tiene efecto"; la etiqueta del botón de reset es "↺ binomial" / "↺ BS" / "↺ spot" según el caso; el caption del modelo activo y los avisos de `market_warnings` aparecen; sin excepciones en la app. Recordar que AppTest ejecuta todas las pestañas en cada ejecución y no puede vaciar un `number_input` a `None`.
- [ ] Modificar `app.py`: `init_state` → `st.session_state.setdefault("pricing_model", "binomial")` **antes** del primer render de la barra lateral; `market_from_state` pasa `pricing_model=st.session_state["pricing_model"]`; en la pestaña Ajustes (misma estructura que comisiones/simulación) un `st.radio("Modelo de valoración para Acción/ETF", ["binomial","black_scholes"], format_func=…("Binomial (americano)" / "Black-Scholes (europeo)"), key="pricing_model_input", on_change=copy_setting, args=("pricing_model",))`, con la clave simple persistida (valor inicial del widget desde `pricing_model`) y una frase de ayuda y otra que diga que Índice la ignora; botón de reset "↺ binomial" si `uses_binomial(market)`, "↺ BS" si no, "↺ spot" en acciones, con `help` coherente; el origen del caption de cada pata ("precio binomial" / "Black-Scholes" / "spot" / "manual"); caption del modelo activo en el Constructor (**no** `st.metric`: trunca textos largos); `refresh_auto_prices` sin cambios (mantiene primas manuales). El estado de widget solo cambia vía `on_click`/`on_change` (callbacks), nunca después de instanciar el widget.
- [ ] Comandos: `.venv/bin/pytest tests/test_app_smoke.py -q` y luego `.venv/bin/pytest -q`. Si se arranca un servidor para comprobar a mano, usar un puerto distinto de **8501** (hay una vista previa del usuario) y detenerlo al terminar.
- **Pass criteria:** smoke verde; suite completa verde; checklist manual entregada al usuario en el bloque 7. Estado máximo `🔨 CODE DONE` hasta la revisión del usuario.

### Bloque 7 — Rendimiento, casos límite, suite completa y checklist (AC-B13, AC-B14, AC-B16)

**Explicación para el usuario:** comprobamos que la app sigue siendo ágil (el árbol es mucho más caro que una fórmula) y que los casos raros (0 días, vencimientos de 1 día o de años, strikes lejanísimos, tasas negativas, prima 0) no producen números absurdos ni errores. Cerramos con la suite completa y una lista corta para que pruebes tú la app.

- [ ] Ampliar `tests/test_binomial.py`/`tests/test_pricing_model.py`/`tests/test_binomial_iv.py` (con `time.perf_counter`, cotas holgadas): prima 500/501 < 0,25 s; curva 401 puntos 200/201 < 1,0 s; IV americana < 2,0 s; `analyze()` de un iron condor de 4 patas (mercado Acción por defecto) < 2,0 s en frío (cota de regresión; presupuesto medido ≈ 0,65 s en frío, ≈ 1,3 s con 4 IV manuales sin caché, IV ≈ 0,15 s por resolución) y un **segundo `analyze()` idéntico (caché caliente) < 0,3 s**. **Medir además y anotar en el informe** los tiempos reales en frío y en caliente (prima, malla, griegas por pata, `analyze` del iron condor). Casos límite con ambos modelos, sin NaN/inf/excepción: días = 0 (intrínseco; griegas `None`), vol = `MIN_VOL`, 1 día, 10 años, strikes muy alejados (K = 1 y K = 10 000), `r` y `q` negativos y altos (p. ej. r = −5 %, q = 20 %), prima 0 (IV con mensaje), patas de acción (sin árbol), σ extrema (desbordamiento de `u^N`).
- [ ] **Mitigación de rendimiento (OBLIGATORIA, sustituye a la antigua contingencia C1):** (a) memoización pura (sin Streamlit) y acotada con `functools.lru_cache` (`maxsize` 256–512) sobre `crr_price`, `crr_greeks`, un ayudante de malla con clave `(kind, K, r, q, sigma, T, steps, american, S_array.tobytes())` (la clave de tupla/bytes hace hashable el array) y la rama americana de `implied_vol` con clave `(kind, strike, price, S, r, q, vol, T)`; los resultados con caché deben coincidir con los sin caché dentro de 1e-12 (test que compara ambos y que no se devuelve un array mutable compartido: copiar o marcar de solo lectura); (b) vega/rho: agrupar los árboles de desplazamiento (σ±, r±) en un solo bucle de inducción por N con arrays de `u`, `p`, `disc` (medido 35 ms vs ≈ 70 ms por pata); (c) los tests de tiempo del paso anterior (frío < 2,0 s, caliente < 0,3 s) son la guarda de regresión. Reportar qué se aplicó y los tiempos antes/después.
- [ ] Ejecutar `.venv/bin/pytest -q` completo desde la raíz (910 + nuevos, todos verdes) y `git diff -U0 -- requirements.txt tests/test_pricing.py` (`requirements.txt` vacío; `tests/test_pricing.py` solo la línea del helper `make_market`); anotar la lista de tests existentes modificados y su justificación.
- [ ] Entregar la **checklist manual** al usuario (puerto 8501 es suyo; EXECUTE no lo toca): 1) Acción por defecto: abrir Ajustes y ver el selector en "Binomial (americano)" con su explicación; 2) Constructor con un put ATM a ~6 meses: alternar a Black-Scholes y comprobar que la prima sube/baja de forma coherente (put binomial ≥ BS) y que los avisos cambian; 3) escribir una prima manual y alternar: se conserva y su botón dice "↺ binomial"/"↺ BS"; 4) Índice: el selector no cambia nada y lo indica; 5) la selección persiste al cambiar de pestaña; 6) un put muy ITM con prima = intrínseco muestra el mensaje "No se puede identificar la IV…"; 7) cambiar precio/strike/volatilidad se siente fluido; 8) el desplegable de escenarios dice que solo queda el modelo lognormal de estilo europeo y la PoP del iron condor sigue ≈ 0,57.
- [ ] Comando: `.venv/bin/pytest -q`.
- **Pass criteria:** suite completa verde; tiempos medidos reportados; ningún caso límite produce NaN/excepción; checklist entregada. Estado máximo `🔨 CODE DONE` hasta confirmación del usuario.

## Verification Evidence

| Gate / Scenario | Strategy | Proves SPEC criterion |
|---|---|---|
| `.venv/bin/pytest tests/test_binomial.py -q`: Hull put N=2 → 7,4284 y N=5 → 4,4885 (árbol sin promediar) | Fully-Automated | AC-B1 |
| `.venv/bin/pytest tests/test_binomial.py -q`: europeo → BS N=1000 (2e-3 en el put de referencia, 3e-3 en el barrido), call q=0 = europeo, prima de ejercicio anticipado ≥ 0, put profundo ITM = intrínseco, paridad americana | Fully-Automated | AC-B2 |
| `.venv/bin/pytest tests/test_binomial.py -q`: pasos 500/501 y 200/201; el promedio supera al N solo en ≥ 80 % de casos y error ≤ 5e-3 vs referencia 2000/2001 | Fully-Automated | AC-B3 |
| `.venv/bin/pytest tests/test_pricing_model.py -q`: canario (Acción sin fijar = binomial), Índice idéntico a BS con ambos selectores | Fully-Automated | AC-B4 |
| `.venv/bin/pytest tests/test_pricing_model.py tests/test_legs_payoff.py tests/test_implied_vol.py tests/test_catalog.py tests/test_analyze.py -q`: BS fijado = números de la Etapa A (primas, "hoy", griegas, IV) | Fully-Automated | AC-B5 |
| `.venv/bin/pytest tests/test_app_smoke.py -q`: selector recalcula primas automáticas y conserva manuales; Índice indica "sin efecto" + checklist manual ítems 1–5 | Hybrid | AC-B6 |
| `.venv/bin/pytest tests/test_pricing_model.py -q`: curva "hoy" 200/201 vs prima 500/501 (≤ 0,02), ≥ intrínseco, sin NaN | Fully-Automated | AC-B7 |
| `.venv/bin/pytest tests/test_binomial.py tests/test_pricing_model.py -q`: griegas del put de referencia, signos/rangos, suma de patas, europeo ≈ BS | Fully-Automated | AC-B8 |
| `.venv/bin/pytest tests/test_binomial_iv.py -q`: ida y vuelta, prima = precio del modelo, IV de Índice/BS = Etapa A | Fully-Automated | AC-B9 |
| `.venv/bin/pytest tests/test_binomial_iv.py -q`: prima = intrínseco, fuera de límites, días 0, pata de acción, nunca lanza | Fully-Automated | AC-B10 |
| `.venv/bin/pytest tests/test_pricing_model.py -q`: P&L/métricas al vencimiento idénticos, PoP 0,5721 con ambos modelos, Monte Carlo semilla 42 idéntico | Fully-Automated | AC-B11 |
| `.venv/bin/pytest tests/test_validation.py -q` (avisos por modelo y subyacente) + smoke AppTest (presencia) + checklist manual ítems 2 y 8 | Hybrid | AC-B12 |
| `.venv/bin/pytest tests/test_binomial.py tests/test_pricing_model.py tests/test_binomial_iv.py -q`: cotas de tiempo (prima, malla, IV, `analyze` iron condor en frío < 2 s y en caliente < 0,3 s) + tiempos medidos en el informe + checklist manual ítem 7 | Fully-Automated | AC-B13 |
| `.venv/bin/pytest tests/test_binomial.py tests/test_pricing_model.py tests/test_validation.py -q` (casos límite con ambos modelos, mensajes) + smoke AppTest | Hybrid | AC-B14 |
| `.venv/bin/pytest tests/test_analyze.py -q` (subproceso sin Streamlit con `opciones.binomial`) + `git diff requirements.txt` vacío | Hybrid | AC-B15 |
| `.venv/bin/pytest -q` completo desde la raíz (910 + nuevos) + `git diff -U0 tests/test_pricing.py` solo la línea del helper + lista justificada de tests actualizados (informe) | Fully-Automated | AC-B16 |

**Qué demuestra y qué NO demuestra (known gaps, residual):**
- Los tests demuestran exactitud del árbol contra libro (Hull), contra BS (límite europeo) y contra propiedades (Merton, paridad, ≥ intrínseco), **no** que el modelo describa el mercado real ni que coincida con la cotización de un bróker (B-G3, B-G4).
- AppTest ejecuta todas las pestañas en cada ejecución: no prueba persistencia entre pestañas lazy ni lo visual (B-G7; checklist manual ítems 1 y 5). **Known-Gap, no apto para PASS por sí solo:** AC-B6/AC-B12 quedan condicionados a la revisión manual del usuario.
- Las cotas de tiempo son holgadas por diseño (máquinas distintas); los tiempos reales se reportan, no se garantizan.
- Vega y rho dependen del tamaño del desplazamiento y heredan el ruido del árbol (B-G5): tolerancias razonables, no exactas.

## Matriz de trazabilidad AC-B1..AC-B16

| AC | Bloque(s) | Archivo(s) de test |
|---|---|---|
| AC-B1, AC-B2, AC-B3 | 1 | `tests/test_binomial.py` |
| AC-B4, AC-B5 | 2 | `tests/test_pricing_model.py` + tests existentes fijados a BS |
| AC-B6 | 6 (+7 manual) | `tests/test_app_smoke.py` |
| AC-B7 | 1–2 | `tests/test_binomial.py`, `tests/test_pricing_model.py` |
| AC-B8 | 3 | `tests/test_binomial.py`, `tests/test_pricing_model.py` |
| AC-B9, AC-B10 | 4 | `tests/test_binomial_iv.py`, `tests/test_implied_vol.py` |
| AC-B11 | 2 | `tests/test_pricing_model.py` |
| AC-B12 | 5–6 | `tests/test_validation.py`, `tests/test_app_smoke.py` |
| AC-B13 | 7 | `tests/test_binomial.py`, `tests/test_pricing_model.py`, `tests/test_binomial_iv.py` |
| AC-B14 | 7 (+6) | `tests/test_binomial.py`, `tests/test_pricing_model.py`, `tests/test_validation.py` |
| AC-B15 | 1, 5 | `tests/test_analyze.py` (subproceso) + revisión de diff |
| AC-B16 | 2, 7 | `.venv/bin/pytest -q` completo + informe |

## Risk Predictions

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| R1 | `analyze()` del iron condor en frío supera el presupuesto (≈ 0,65 s medido; ≈ 1,3 s con 4 IV manuales sin caché; ≈ 10 árboles por pata) | Media-Alta | Mitigación obligatoria en el bloque 7: `lru_cache` acotado (precio, griegas, malla, IV americana) + vega/rho agrupados; tests frío < 2 s y caliente < 0,3 s |
| R2 | Desbordamiento (`u^N`) o `p` fuera de [0,1] con σ extrema/tiny produce NaN/inf | Media | Guardas explícitas en `_crr_values` y tests de casos límite (σ 1e-6, σ 10, T largo, r−q grande) |
| R3 | Tests existentes con primas BS de Acción/ETF fallan al cambiar el modelo por defecto | Alta (esperada) | Fijar `pricing_model="black_scholes"` en los helpers (incl. `test_pricing.py` y `test_simulation.py`, solo el helper); barrido con el despachador en el bloque 2; lista justificada; Índice intacto |
| R4 | La PoP 0,5721 se "rompe" al cambiar las primas automáticas a binomiales | Media (malentendido) | El test construye las patas con primas BS y evalúa ambos modelos; documentado: con primas binomiales ≈ 0,5726 |
| R5 | La IV americana devuelve un número engañoso con prima = intrínseco (precio plano en σ) | Media | Identificabilidad comprobada **antes** de `brentq`; mensaje específico; test con precio plano |
| R6 | Oscilación del árbol hace la IV/griegas ruidosas (precio no monótono) | Baja-Media | Promedio N/N+1; tolerancias de ida y vuelta medidas en precio; `brentq` con bracket verificado |
| R7 | Cambiar el modelo no recalcula, o `StreamlitWidgetAlreadyInstantiatedError` | Media | Callbacks `on_change` que copian a clave simple (patrón de Ajustes); `refresh_auto_prices` ya recalcula; smoke AppTest |
| R8 | Ciclo de importación `binomial` ↔ `pricing` | Baja | `binomial.py` no importa `pricing.py`; solo `models` (MIN_VOL); verificado con el test de importación |
| R9 | Exportar un nombre `binomial` sombrea el submódulo | Baja | Exportar solo `crr_*`, `option_*`, `uses_binomial` |
| R10 | Cifras de referencia copiadas de un prototipo con otras entradas | Media | Recalcular con las entradas exactas de cada test (lección Etapa A); referencia de griegas fijada: S=K=100, r=4 %, q=1 %, σ=25 %, T=0,5 |

## Out of Scope

Comisión de cierre racional al vencimiento (Etapa B2, ciclo aparte; backlog `process/general-plans/backlog/close-fee-rational-close_20-11-26.md` se mantiene y la decisión 6 del MVP sigue); árboles más precisos (Leisen-Reimer); dividendos discretos; datos de mercado en vivo y cadenas de opciones (Etapa C); cambios en Monte Carlo, PoP o métricas al vencimiento; cambios en el comportamiento de Índice; superficie/sonrisa de volatilidad, colas gruesas, reglas dependientes de la trayectoria; asesoría de inversión; cambios en `analyze()`/`Analysis` o en las decisiones 1–14 del MVP y A1–A11 de la Etapa A.

## Dependencies

Sin dependencias nuevas: numpy 2.5.5 (inducción vectorizada), scipy 1.18.1 (`brentq`, `norm`), plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0. Bloques estrictamente secuenciales (comparten `pricing.py`, `payoff.py`, `__init__.py`): 2 usa el precio del 1; 3 usa el árbol y el despachador; 4 usa `crr_price` y `uses_binomial`; 5 usa los textos del modelo; 6 usa todo.

## Test Infra Improvement Notes

(none identified yet)

## Resume and Execution Handoff

1. **Plan file:** `process/general-plans/active/etapa-b1-binomial_20-11-26/etapa-b1-binomial_PLAN_20-11-26.md` (execute-anchor).
2. **Last completed phase/step:** PLAN escrito (20-11-26); ningún bloque ejecutado; `## Validate Contract` escrito (Gate: PASS).
3. **Validate-contract status:** written 2026-11-20 (outer-pvl, Gate: PASS, tras 1 ciclo de suplemento PVL).
4. **Supporting context files loaded:** SPEC de la Etapa B1 (`process/general-plans/active/etapa-b1-binomial_20-11-26/etapa-b1-binomial_SPEC_20-11-26.md`); `process/context/all-context.md`; `process/context/tests/all-tests.md`; `process/development-protocols/plan-lifecycle.md`; `implementation-standards.md`; plan de la Etapa A (formato); `opciones/*.py`; `app.py`; `tests/*`; scripts de investigación en el scratchpad (`crr.py`, `p.py`, `p2.py`, solo referencia).
5. **Next step for a fresh agent:** tras VALIDATE, ejecutar el bloque 1 (TDD: `tests/test_binomial.py` en rojo → `Market.pricing_model` + `opciones/binomial.py`), gate `.venv/bin/pytest tests/test_binomial.py -q` y luego `.venv/bin/pytest -q`; no empezar un bloque con el anterior en rojo; marcar `CODE DONE`, nunca `VERIFIED` sin confirmación del usuario.

**Instrucciones para el agente de EXECUTE (lecciones del MVP y la Etapa A, vinculantes):**
1. Bloques estrictamente en orden 1 a 7; cada uno cierra con su gate y `.venv/bin/pytest -q` completo.
2. TDD: tests primero (rojo), luego implementación; código simple, identificadores en inglés, comentarios y docstrings en español.
3. **Los agentes de EXECUTE no pueden escribir bajo `process/`:** no editar este plan ni crear el reporte; los estados de bloque, el informe (lista de tests actualizados con justificación y tiempos medidos) y las actualizaciones de contexto se hacen en UPDATE PROCESS. Devolver esa información en el mensaje final.
4. **No modificar módulos no tocados** (`metrics.py`, `commissions.py`, `catalog.py`, `simulation.py`, `analyze()`/`Analysis`, `requirements.txt`). En `tests/test_pricing.py` solo se permite la línea del helper `make_market` (`pricing_model="black_scholes"`). Cambiar solo los tests listados en Touchpoints, solo fijando helpers (nunca números esperados), y justificar cada uno.
5. **Servidores:** si se arranca alguno (smoke manual), usar un puerto distinto de **8501** (vista previa del usuario: nunca tocarla ni detenerla) y **detener** el que se haya arrancado antes de terminar.
6. `st.metric` trunca textos largos (visto dos veces): el caption del modelo activo y los avisos van en `st.caption`/markdown, no en `st.metric`.
7. El estado de un widget solo cambia desde callbacks `on_click`/`on_change` (antes del render); si no, `StreamlitWidgetAlreadyInstantiatedError`.
8. AppTest ejecuta todas las pestañas en cada ejecución y no puede vaciar un `number_input` a `None`; no escribir tests que dependan de ello.
9. **Recalcular las cifras de referencia con las entradas exactas** de cada test antes de fijarlas (no copiar de un prototipo con otras entradas); registrar en el test el valor medido y la tolerancia.
10. `binomial.py` no importa `pricing.py`; no exportar nada llamado `binomial` en `__init__.py`; `from opciones import implied_vol` sigue siendo la forma correcta de importar la función.
11. EVL: un vc-tester independiente vuelve a ejecutar cada comando de gate.

## Validate Contract

Status: PASS
Date: 20-11-26
date: 2026-11-20
generated-by: outer-pvl
supersedes: 2026-11-20 (outer-pvl) — first-pass contract (Gate: BLOCKED); PVL supplement cycle 1 applied F1, F2, C1-C4 and re-validation confirms them resolved

Parallel strategy: sequential
Rationale: signal score 2/7 (dominant: more than 5 files touched); blocks share `pricing.py`, `payoff.py`, `__init__.py`, so a single vc-execute-agent (opus) runs blocks 1-7 in order; EVL = independent vc-tester re-running every gate command.

Test gates (all commands from repo root; EXECUTE and EVL run the exact commands):

| criterion id | behavior | strategy | proving test | gap-resolution |
|---|---|---|---|---|
| AC-B1 | CRR tree reproduces Hull (7.4284 N=2, 4.4885 N=5, unaveraged) | Fully-Automated | `.venv/bin/pytest tests/test_binomial.py -q` | B |
| AC-B2 | European tree = BS (2e-3 reference put, 3e-3 sweep), call q=0 = European, early-exercise premium >= 0, deep ITM put = intrinsic, parity bounds | Fully-Automated | `.venv/bin/pytest tests/test_binomial.py -q` | B |
| AC-B3 | N/N+1 averaging: error <= 5e-3, beats single N in >= 80 % of cases | Fully-Automated | `.venv/bin/pytest tests/test_binomial.py -q` | B |
| AC-B4, AC-B5 | dispatcher; canary (Acción default = binomial); Índice and BS-pinned = Stage A numbers | Fully-Automated | `.venv/bin/pytest tests/test_pricing_model.py tests/test_legs_payoff.py tests/test_implied_vol.py tests/test_catalog.py tests/test_analyze.py -q` | B |
| AC-B7 / B7 | "today" grid 200/201 within 0.02 of 500/501 premium at spot, >= intrinsic, no NaN | Fully-Automated | `.venv/bin/pytest tests/test_pricing_model.py tests/test_binomial.py -q` | B |
| AC-B8 | Greeks (put S=K=100, r 4 %, q 1 %, sigma 25 %, T 0.5: delta -0.4422, gamma 0.0233, theta -0.01564, vega 0.2764, rho -0.1949 central), signs, European tree ~ BS, position sum | Fully-Automated | `.venv/bin/pytest tests/test_binomial.py tests/test_pricing_model.py -q` | B |
| AC-B9, AC-B10 | American IV: price round trip always, sigma round trip only where vega > 0.01 and premium > intrinsic*(1+1e-6)+1e-9, flat cases -> MSG_AMERICAN_NOT_IDENTIFIABLE, never raises | Fully-Automated | `.venv/bin/pytest tests/test_binomial_iv.py tests/test_implied_vol.py -q` | B |
| AC-B11 | expiry P&L, metrics, exact PoP 0.5721 (legs built with BS market), Monte Carlo seed 42 identical across models | Fully-Automated | `.venv/bin/pytest tests/test_pricing_model.py -q` | B |
| AC-B12 | warnings per model/underlying | Hybrid | `.venv/bin/pytest tests/test_validation.py tests/test_app_smoke.py -q` + manual checklist items 2, 8 | D |
| AC-B6 | selector recalculates auto premiums, keeps manual, Índice "no tiene efecto", reset label | Hybrid | `.venv/bin/pytest tests/test_app_smoke.py -q` + manual checklist items 1-5 | D |
| AC-B13 | premium < 0.25 s, grid < 1.0 s, IV < 2.0 s, iron-condor `analyze()` cold < 2.0 s and warm < 0.3 s (bounded pure `lru_cache` + batched vega/rho mandatory) | Fully-Automated | `.venv/bin/pytest tests/test_binomial.py tests/test_pricing_model.py tests/test_binomial_iv.py -q` | B |
| AC-B14 | edge cases both models without NaN/exception | Hybrid | `.venv/bin/pytest tests/test_binomial.py tests/test_pricing_model.py tests/test_validation.py tests/test_app_smoke.py -q` | B |
| AC-B15 | engine imports without Streamlit incl. `opciones.binomial`; requirements unchanged | Hybrid | `.venv/bin/pytest tests/test_analyze.py -q` + `git diff -- requirements.txt` empty | B |
| AC-B16 | full suite green; `tests/test_pricing.py` diff = only the `make_market` pin line | Fully-Automated | `.venv/bin/pytest -q` + `git diff -U0 -- requirements.txt tests/test_pricing.py` | A |

Failing stubs (Fully-Automated rows; TDD, replace with real tests in each block):
`test("should reproduce Hull N=2/N=5 unaveraged", () => { throw new Error("NOT IMPLEMENTED — TDD stub: AC-B1") })` and analogous stubs for AC-B2, B3, B4/B5, B7, B8, B9/B10, B11, B13, B16 (the blocks' "tests first, red" step is the stub).

Legacy line form:
- Block 1: [Fully-automated: `.venv/bin/pytest tests/test_binomial.py -q`, then `.venv/bin/pytest -q`]
- Block 2: [Fully-automated: `.venv/bin/pytest tests/test_pricing_model.py tests/test_binomial.py -q`, then `.venv/bin/pytest -q`]
- Block 3: [Fully-automated: `.venv/bin/pytest tests/test_binomial.py tests/test_pricing_model.py -q`, then `.venv/bin/pytest -q`]
- Block 4: [Fully-automated: `.venv/bin/pytest tests/test_binomial_iv.py tests/test_implied_vol.py -q`, then `.venv/bin/pytest -q`]
- Block 5: [Hybrid: `.venv/bin/pytest tests/test_validation.py tests/test_analyze.py -q`, then `.venv/bin/pytest -q`; `git diff -- requirements.txt` empty]
- Block 6: [Hybrid: `.venv/bin/pytest tests/test_app_smoke.py -q`, then `.venv/bin/pytest -q`; manual checklist]
- Block 7: [Fully-automated: `.venv/bin/pytest -q`; `git diff -U0 -- requirements.txt tests/test_pricing.py`]

Per-block gate summary: each block passes only when its command is green AND the full `.venv/bin/pytest -q` (910 + new) is green; max status `CODE DONE` until the user confirms.

Dimension findings (re-validation V1-V7, PVL cycle 1):
- Infra fit: PASS — `binomial.py` imports only `models`; no cycle; no exported `binomial`; radio/`on_change` pattern and `setdefault` before sidebar verified earlier; unchanged by the supplement.
- Test coverage: PASS — F1 (one-line `make_market` pin in `tests/test_pricing.py`) and F2 (`test_simulation.py`, `test_legs_payoff.py` lines ~21/~170, `test_implied_vol.py`, `test_catalog.py`, `test_analyze.py`) are in AC-B16, Touchpoints, Blast Radius, Block 2, Block 7 and EXECUTE instruction 4. Emulation: scratch copy of the repo with the CRR dispatcher (`pricing_model` field) and exactly those helper pins -> 910 passed, 0 failed (before pins: 5 failures).
- Breaking changes: PASS — Índice and `black_scholes` paths byte-identical by construction; expiry/PoP/Monte Carlo untouched.
- Security surface: PASS — no I/O, secrets or dependencies.
- Performance (AC-B13): PASS — C1 resolved: bounded pure `lru_cache` (maxsize 256-512, no Streamlit, array keyed by `tobytes()`, no shared mutable array returned) + batched vega/rho are mandatory in Block 7 with cold < 2.0 s and warm < 0.3 s tests (prototype: 0.65 s cold, IV 0.15 s/solve).
- AC-B3 tolerance: PASS — C2 resolved (5e-3, >= 80 % of cases).
- AC-B2 tolerance: PASS — C3 resolved (3e-3 sweep, 2e-3 reference put only).
- IV round trip: PASS — C4 resolved (sigma assertion gated on vega > 0.01 and premium > intrinsic; flat cases assert not-identifiable message; price round trip always).
- Section feasibility Blocks 1-7: PASS — reference values reused and unchanged (Hull 7.42840/4.48846; Greeks -0.44217/0.023314/-0.015628/0.27639/-0.19487; grid gap <= 9.6e-3; PoP 0.572122 BS-premiums / 0.572599 binomial).

Open gaps: none blocking. Known-Gap residual (named, justified, gap-resolution D): AC-B6/AC-B12 UI persistence across tabs and visuals are not provable by AppTest (manual checklist items 1, 5, 2, 8).

What this coverage does NOT prove:
- Model fidelity to real markets or broker quotes (B-G3, B-G4: discrete dividends, no smile); tree oscillation residual after N/N+1 averaging.
- Vega/rho are bump-size dependent and inherit tree noise (B-G5); tolerances reasonable, not exact.
- AppTest runs all tabs each run: tab-persistence of the selector, visual rendering and `st.caption` layout are not proven.
- Timing bounds are machine-dependent; measured cold/warm times are reported, not guaranteed.
- `exact_pop`/Monte Carlo are shown independent of the model only for the catalog iron condor and seed 42, not for every strategy.
- American IV for flat-in-sigma premiums returns a message, not a number (by design).

Gate: PASS
Accepted by: n/a (Gate PASS, no accepted concerns); Known-Gap residuals above are on record and conditioned on the user's manual checklist, not on this gate.

Execute-agent instructions:
1. Blocks strictly 1 to 7; TDD (red first); each block closes with its gate and the full `.venv/bin/pytest -q`.
2. EXECUTE agents cannot write under `process/`, `.claude/`, `.codex/`, `.agents/`: block status, report and context updates belong to UPDATE PROCESS; return in the final message the list of modified existing tests with justification, measured cold/warm timings, which caches/batching were applied, and the rho/vega note (central -0.1949 vs SPEC -0.1897 = one-sided bump).
3. Pin only helpers (`pricing_model="black_scholes"`); never change expected numbers; `tests/test_pricing.py` diff is the single `make_market` line. Do not modify `metrics.py`, `commissions.py`, `catalog.py`, `simulation.py`, `analyze()`/`Analysis`, `requirements.txt`.
4. Port 8501 is the user's preview: never touch it; start no server for gates (use AppTest); stop any other server you start.
5. `st.metric` truncates: use `st.caption`/markdown. Widget state changes only in `on_change`/`on_click`; `setdefault("pricing_model","binomial")` before the first sidebar render. AppTest runs all tabs and cannot blank a `number_input`.
6. Recompute every reference number with each test's exact inputs before pinning. `binomial.py` must not import `pricing.py`; no export named `binomial`; `exact_pop(market, legs, settings, sim)` needs a `SimulationSettings`.
7. Caches must be pure (no Streamlit), bounded, and equal to uncached results within 1e-12.
8. EVL: an independent vc-tester re-runs every gate command above.

## Autonomous Goal Block

SESSION GOAL: Etapa B1 — binomial CRR model for American Acción/ETF options (blocks 1-7)
Charter + umbrella plan: N/A — single plan (`process/general-plans/active/etapa-b1-binomial_20-11-26/etapa-b1-binomial_PLAN_20-11-26.md`)
Autonomy: blocks run in order without approval pauses; irreversible actions hard-stop; subagent delegation mandatory.
Hard stops: touching port 8501; editing `metrics.py`/`commissions.py`/`catalog.py`/`simulation.py`/`analyze()`/`requirements.txt`; changing an expected number to make a test pass (only pin helpers; `tests/test_pricing.py` one line); writing under `process/`, `.claude/`, `.codex/`, `.agents/` from EXECUTE; any block started with the previous one red.
Next phase: EXECUTE: process/general-plans/active/etapa-b1-binomial_20-11-26/etapa-b1-binomial_PLAN_20-11-26.md (block 1)
Validate contract: inline in plan (`## Validate Contract`, Gate: PASS)
Execute start: `.venv/bin/pytest tests/test_binomial.py -q` then `.venv/bin/pytest -q` | manual checklist (Block 7) | high-risk pack: no

## Next Step

PLAN completo. Siguiente: ENTER VALIDATE MODE (vc-validate-agent) sobre este plan; solo tras `Gate: PASS` y la orden explícita "ENTER EXECUTE MODE" ejecutar el bloque 1 con vc-execute-agent (RIPER-5; en Cursor Plan mode, importar el Implementation Checklist).

PHASE_COMPLETE: PLAN
