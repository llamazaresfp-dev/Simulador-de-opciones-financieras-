---
name: etapa-a-montecarlo-iv PLAN
description: "Plan COMPLEX de la Etapa A (PoP exacta + Monte Carlo + volatilidad implícita) de Laboratorio de Opciones en 4 bloques secuenciales, cada uno terminado en pytest verde."
date: 20-11-26
status: completed
complexity: complex
spec: process/general-plans/completed/etapa-a-montecarlo-iv_20-11-26/etapa-a-montecarlo-iv_SPEC_20-11-26.md
---

# Plan: Etapa A — Monte Carlo + volatilidad implícita

**Date**: 20-11-26
**Complexity**: COMPLEX (un solo plan, un solo flujo de ejecución, 4 bloques secuenciales; no es phase program)
**Status**: ✅ VERIFIED (Etapa A completa, archivada 20-11-26)
**SPEC bloqueado**: `process/general-plans/completed/etapa-a-montecarlo-iv_20-11-26/etapa-a-montecarlo-iv_SPEC_20-11-26.md` (AC-A1..AC-A17, decisiones A1–A10, huecos A-G1..A-G6)
**Entorno**: Python 3.12.3, `.venv` (numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0); línea base: 479 tests en verde (HEAD 3fecb0f)

**TL;DR:** se añaden dos módulos puros (`opciones/implied_vol.py`, `opciones/simulation.py`) y funciones de validación/avisos, todo con tests, en los bloques 1–3; solo el bloque 4 toca `app.py` (un desplegable "Escenarios (Monte Carlo)" bajo las métricas + ajustes de simulaciones/semilla). No se modifica `analyze()`, `Analysis`, `metrics.py` ni el comportamiento del MVP. Cada bloque cierra con `.venv/bin/pytest -q` completo en verde.

**Clasificación de complejidad (mi decisión):** el INNOVATE recomendaba SIMPLE, pero el criterio de la skill (varios subsistemas, entrega por fases, motor + UI, bloques con puertas de verificación propias) apunta a COMPLEX. Se elige **COMPLEX estándar** (un solo archivo, un flujo de ejecución, mismo formato que el plan del MVP), **no** phase program: los 4 bloques son secuenciales, caben honestamente en un único archivo y no necesitan re-investigarse por separado.

## Overview

La Etapa A añade, siempre como herramienta de estudio: (1) un modelo de escenarios (precio final lognormal; neutral al riesgo por defecto, o con crecimiento esperado μ del usuario) que da la **PoP exacta** por fórmula y una **simulación Monte Carlo** (histograma, valor esperado no descontado, percentiles 5/50/95, PoP simulada como comprobación); (2) la **volatilidad implícita** de cada pata con prima editada a mano, con un botón "usar como volatilidad global". Todo vive en el Constructor, en un bloque desplegable bajo las métricas; el catálogo y los Ajustes de comisiones del MVP no cambian.

Contexto leído: `process/context/all-context.md`, `process/context/tests/all-tests.md` (router; sin docs de test más profundos), `process/development-protocols/plan-lifecycle.md`, `process/development-protocols/implementation-standards.md`, el SPEC, el motor `opciones/*.py`, `app.py`, `tests/test_app_smoke.py`, `tests/test_analyze.py` (test en subproceso de importación sin Streamlit).

## Quick Links

- [Decisiones bloqueadas](#decisiones-bloqueadas-a1a11) · [Chosen Approach](#chosen-approach-y-por-qué-este-camino) · [Phase Completion Rules](#phase-completion-rules)
- [Acceptance Criteria](#acceptance-criteria) · [Touchpoints](#touchpoints) · [Public Contracts](#public-contracts) · [Blast Radius](#blast-radius)
- [Implementation Checklist (bloques 1–4)](#implementation-checklist) · [Verification Evidence](#verification-evidence) · [Matriz de trazabilidad](#matriz-de-trazabilidad-ac-a1ac-a17)
- [Risk Predictions](#risk-predictions) · [Out of Scope](#out-of-scope) · [Test Infra Improvement Notes](#test-infra-improvement-notes) · [Resume and Execution Handoff](#resume-and-execution-handoff) · [Validate Contract](#validate-contract)

## Status strip

| Bloque | Contenido | Estado |
|---|---|---|
| 1 | `implied_vol.py` + mensajes de IV + `tests/test_implied_vol.py` | ✅ VERIFIED (d7606f2, 651 tests) |
| 2 | PoP exacta (`simulation.py`) + `tests/test_simulation.py` | ✅ VERIFIED (55bdeea, 686 tests) |
| 3 | Monte Carlo + `ScenarioResult` + `validate_simulation` / `scenario_warnings` + tests | ✅ VERIFIED (3a Monte Carlo d46eddb, 836; 3b validación/avisos/exportaciones 9853668, 887) |
| 4 | UI `app.py` + smoke AppTest + pytest completo + checklist manual (ACs Hybrid) | ✅ VERIFIED (4a escenarios 9689b02, 900; 4b UI de IV + arreglo EVL f154272, 910) |

## Decisiones bloqueadas (A1–A11)

A1–A10 están en el SPEC (no se repiten; el SPEC manda). Decisión adicional confirmada por el usuario (20-11-26):

| # | Decisión |
|---|---|
| A11 | Rangos de entrada de la simulación: **n_paths** entero entre 1 000 y 1 000 000 (por defecto 100 000); **seed** entero entre 0 y 2³²−1 (por defecto 42); **μ** (crecimiento esperado anual del precio, comparable a r − q) entre −50 % y +100 % por año; vacío = neutral al riesgo. |

**Banderas sobre el SPEC (registradas):**
- **AC-A10, "volatilidad = 0":** ya la bloquea la validación de mercado del MVP (`validate_market`: vol < `MIN_VOL`). El bloque de escenarios muestra ese mensaje existente; no se crea un mensaje nuevo.
- **A1, etiqueta de μ:** el SPEC dice "rentabilidad esperada"; la etiqueta de UI será **"crecimiento esperado del precio (% anual), comparable a r − q"** para dejar claro que es el crecimiento del precio (no incluye el dividendo, igual que r − q).

## Chosen Approach y por qué este camino

**Chosen Approach (INNOVATE):** dos módulos puros nuevos en `opciones/` que **reutilizan** `pnl_expiry` y `compute_metrics` del MVP como fuente de verdad (sin tocarlos), una única llamada pública `simulate_scenario(...)` que devuelve PoP exacta + Monte Carlo en un `ScenarioResult`, y `implied_vol(leg, market)` que nunca lanza. `app.py` solo dibuja.

**Why This Over Alternatives:**
- *Solo Monte Carlo para la PoP* → ruido ±0,3 pp y no coincide con los quiebres exactos; se usa la fórmula exacta y MC como comprobación cruzada (A2).
- *Reimplementar el P&L dentro de la simulación* → duplicaría comisiones y la regla de cierre; se llama a `pnl_expiry` vectorizado una vez (0,018 s con 100 000).
- *Modificar `analyze()`/`Analysis` para incluir escenarios* → rompe contratos del MVP y fuerza recalcular MC en cada rerun aunque el desplegable esté cerrado; se mantiene aparte.
- *Reducción de varianza / caché* → complejidad innecesaria; 0,018 s por cálculo y resultados estables con semilla fija.
- *IV por Newton* → inestable con vega ≈ 0; `brentq` por intervalo tras comprobar límites sin arbitraje es robusto (A9).

**Key Constraints Accepted:**
- Nivel básico de Python: funciones cortas, dataclasses, comentarios/docstrings en español, identificadores en inglés.
- La lognormal subestima colas y BS aproxima americanas (A-G1, A-G2): se avisa, no se corrige.
- Una σ global no encaja con todos los strikes (A-G3): el botón de IV cambia primas automáticas y curva "hoy"; se avisa de forma prominente.
- Sin dependencias nuevas; `requirements.txt` sin cambios.
- Valor esperado no descontado (A-G5), etiquetado así.

## Arquitectura

```
app.py (solo dibuja)
   │ API pública
   ▼
opciones/__init__.py ── (MVP intacto) + implied_vol, IVResult, SimulationSettings,
   │                    ScenarioResult, simulate_scenario, validate_simulation, scenario_warnings
   ├─ implied_vol.py  implied_vol(leg, market) -> IVResult(vol | None, message | None)   [NUEVO, bloque 1]
   ├─ simulation.py   SimulationSettings, ScenarioResult, simulate_scenario               [NUEVO, bloques 2-3]
   ├─ validation.py   + validate_simulation, scenario_warnings                            [MODIFICAR, bloque 3]
   └─ reutiliza sin cambios: pricing.bs_price, payoff.pnl_expiry, metrics.compute_metrics
```

Flujo de `simulate_scenario(market, legs, settings, sim)`: `drift = sim.mu if sim.mu is not None else market.rate − market.q` → **PoP exacta**: fronteras = `[0] + strikes + compute_metrics(...).breakevens` (únicas, ordenadas); sondear `pnl_expiry` en el punto medio de cada intervalo (cola derecha en `último + max(último, 1)`); sumar diferencias de la CDF lognormal donde P&L > `ZERO_TOL` (1e-7), con cola superior hasta 1 → **Monte Carlo**: `rng = np.random.default_rng(seed)`, `z = rng.standard_normal(n)`, `S_T = S·exp((drift − σ²/2)T + σ√T·z)`, una llamada vectorizada a `pnl_expiry`, mismo criterio `> ZERO_TOL`, histograma de ~50 bins sobre el P&L recortado a los percentiles 0,5–99,5 % (los bins de los extremos acumulan las colas; los conteos suman `n`). CDF(x) = Φ((ln(x/S) − (drift − σ²/2)T)/(σ√T)), CDF(0) = 0.

Flujo de `implied_vol(leg, market)`, comprobaciones **en este orden**: pata de acción → mensaje; días = 0 → mensaje; prima ≤ 0 → mensaje; límites sin arbitraje estrictos (call: máx(S·e^(−qT) − K·e^(−rT), 0) < C < S·e^(−qT); put: máx(K·e^(−rT) − S·e^(−qT), 0) < P < K·e^(−rT)) → mensajes distintos para "por debajo" y "por encima"; `brentq(f, 1e-6, 10, xtol=1e-14, rtol=1e-14)` y, si lanza `ValueError`, mensaje. Nunca lanza excepciones.

## Phase Completion Rules

A phase is NOT complete until:

1. **Integration Test** - el bloque funciona con los anteriores y con los 479 tests del MVP (`.venv/bin/pytest -q` completo)
2. **Manual Test** - el usuario puede reproducir valores de referencia con `.venv/bin/python -c ...` (bloques 1–3) y la checklist manual (bloque 4)
3. **Data Verification** - valores de referencia calculados a mano o por fórmula (0,3392; 0,5721; N(d2)) y oráculos independientes (`scipy.integrate.quad`)
4. **Error Handling** - entradas inválidas devuelven mensajes en español, nunca NaN, infinitos ni excepciones hacia la UI
5. **User Confirmation** - el usuario dice "funciona"

Status: ⏳ PLANNED · 🔨 CODE DONE · 🧪 TESTING · ✅ VERIFIED · 🚧 BLOCKED.

Regla honesta: un bloque con tests verdes y sin revisión del usuario es `🔨 CODE DONE`, no `✅ VERIFIED`. Solo el usuario pasa un bloque a `✅ VERIFIED`. **Lección del MVP:** vc-execute-agent no puede escribir bajo `process/`; las actualizaciones de estado de los bloques en este plan y el reporte se hacen en UPDATE PROCESS.

Reporte por bloque (lo crea EXECUTE/UPDATE PROCESS, no este plan): `process/general-plans/completed/etapa-a-montecarlo-iv_20-11-26/etapa-a-montecarlo-iv_REPORT_20-11-26.md`.

## Acceptance Criteria

Se heredan literalmente **AC-A1..AC-A17 del SPEC** (no se reescriben). Interpretaciones fijadas por este plan:

- **AC-A8 / AC-A10 (rangos, decisión A11):** `validate_simulation` rechaza n_paths no entero o fuera de [1 000, 1 000 000], seed no entero o fuera de [0, 2³²−1] (bool no cuenta como entero), μ no numérica/NaN/inf o fuera de [−0,50, 1,00] (fracción anual); más los errores existentes de mercado (días = 0 → mensaje propio de escenarios, vol < `MIN_VOL` → mensaje existente de `validate_market`) y "sin patas".
- **AC-A10 (días = 0):** el MVP permite días = 0 (decisión 13); para escenarios es un error bloqueante con mensaje propio ("sin tiempo hasta el vencimiento no hay distribución"), sin tocar `validate_market`.
- **AC-A7:** el desplegable no contiene controles ni resultados "hoy" (la IV recalcula "hoy" solo vía `refresh_auto_prices` existente).
- **AC-A16:** el test en subproceso se extiende a `opciones.implied_vol` y `opciones.simulation`; `requirements.txt` sin cambios.

## Touchpoints

| Bloque | Archivo | Acción |
|---|---|---|
| 1 | `opciones/implied_vol.py` | crear (`IVResult`, `implied_vol`, constantes de mensajes) |
| 1 | `opciones/__init__.py` | modificar (exportar `implied_vol`, `IVResult`) |
| 1 | `tests/test_implied_vol.py` | crear |
| 2 | `opciones/simulation.py` | crear (`SimulationSettings`, función interna de PoP exacta, `ZERO_TOL`) |
| 2 | `tests/test_simulation.py` | crear (parte PoP exacta) |
| 3 | `opciones/simulation.py` | modificar (`ScenarioResult`, `simulate_scenario` con PoP exacta + MC, histograma) |
| 3 | `opciones/validation.py` | modificar (añadir `validate_simulation`, `scenario_warnings`; sin tocar lo existente) |
| 3 | `opciones/__init__.py` | modificar (exportar `SimulationSettings`, `ScenarioResult`, `simulate_scenario`, `validate_simulation`, `scenario_warnings`) |
| 3 | `tests/test_simulation.py`, `tests/test_validation.py` | modificar/ampliar |
| 3 | `tests/test_analyze.py` | modificar (subproceso sin Streamlit: añadir `opciones.implied_vol`, `opciones.simulation`) |
| 4 | `app.py` | modificar (estado `mu_pct`, `n_sims`, `seed`; desplegable; IV; ajustes) |
| 4 | `tests/test_app_smoke.py` | modificar (nuevos smoke tests) |
| Cierre | `process/context/all-context.md`, `process/context/tests/all-tests.md` | modificar en UPDATE PROCESS (no en EXECUTE de código) |

Solo lectura / sin tocar: `opciones/metrics.py`, `payoff.py`, `pricing.py`, `commissions.py`, `catalog.py`, `models.py`; `analyze()` y `Analysis` en `opciones/__init__.py`; `requirements.txt`; el SPEC.

## Public Contracts

| Elemento | Contrato |
|---|---|
| `implied_vol(leg, market) -> IVResult` | `IVResult(vol: float \| None, message: str \| None)`; exactamente uno de los dos es `None`; `vol` es fracción (0,25 = 25 %); nunca lanza; premio igual al precio del modelo → `abs(vol − market.vol) < 1e-9` |
| `SimulationSettings(n_paths=100_000, seed=42, mu=None)` | dataclass; `mu` es fracción anual (0,05 = 5 %) o `None` (= neutral al riesgo) |
| `ScenarioResult` | `pop_exact`, `pop_mc`, `mean_pnl`, `pnl_std`, `p5`, `p50`, `p95` (floats), `hist_counts`, `hist_edges` (arrays; `hist_counts.sum() == n_paths`), `n_paths` (int), `mu_used` (fracción anual realmente usada: μ o r − q); sin NaN ni infinitos |
| `simulate_scenario(market, legs, settings, sim) -> ScenarioResult` | PoP exacta + MC en una llamada; precondición: `validate_market`, `validate_legs` y `validate_simulation` devolvieron listas vacías; mismo `seed` y datos → resultado idéntico; cambiar `seed` cambia solo los campos MC, no `pop_exact` |
| `validate_simulation(market, legs, sim) -> list[str]` | errores en español (vacía = válido); nunca lanza |
| `scenario_warnings(market) -> list[str]` | avisos: modelo ≠ predicción, colas más gruesas que lognormal, americanas sesgan IV y simulación (Acción/ETF) o europeas (Índice), "no es asesoría" |
| `ZERO_TOL = 1e-7` (`simulation.py`) | umbral de "P&L > 0" compartido por PoP exacta y MC |

Sin cambios en `analyze()`, `Analysis`, `Metrics`, `Leg`, `Market`, `CommissionSettings`, CLI, red, ficheros ni formatos persistentes. UI: nuevas claves de `session_state`: `mu_pct`, `mu_pct_input`, `n_sims`, `n_sims_input`, `seed`, `seed_input`, `use_iv_{leg_id}` (botón).

## Blast Radius

- **Archivos:** 2 módulos nuevos + 3 existentes modificados (`__init__.py`, `validation.py`, `app.py`) + 2 archivos de tests nuevos + 3 existentes ampliados + 2 docs de contexto al cierre.
- **Clase de riesgo:** baja a nivel de despliegue (app local, sin red, sin secretos, sin dependencias nuevas); **media a nivel de corrección financiera** (probabilidades e IV que el usuario podría interpretar como predicción). Defensa: oráculos independientes (N(d2), `scipy.integrate.quad`, fórmula de EV del long call), tolerancias por EE y avisos visibles.
- **Acoplamiento:** `simulation.py` depende de `payoff`, `metrics`, `models`; `implied_vol.py` de `pricing` y `models`; ninguno importa Streamlit. Dirección única: nada del MVP importa los módulos nuevos salvo `__init__.py` (reexport) y `validation.py` (solo constantes si hacen falta).
- **Rendimiento:** UI recalcula la simulación en cada rerun dentro del desplegable (sin caché, ~0,02 s con 100 000 trayectorias en iron condor).
- **Rollback:** bloques aditivos; deshacer = borrar los módulos y revertir los reexports y el bloque de `app.py`. No hay migraciones.

## Implementation Checklist

Orden estricto; cada bloque termina con pytest verde. Reglas transversales: TDD (tests primero), funciones cortas, comentarios en español, `pytest.approx` en floats, ningún `print` en el motor, no modificar `analyze()`/`Analysis`/`metrics.py`.

### Bloque 1 — Volatilidad implícita (AC-A11, AC-A12, AC-A16 parcial)

**Explicación para el usuario:** la volatilidad implícita responde a "¿qué volatilidad tendría que haber para que Black-Scholes diera exactamente esta prima?". Construimos esa calculadora (un buscador de raíces) y, antes de usarla, comprobamos que la prima tiene sentido (por ejemplo, una prima de 0,00 no da una IV "falsa"). Si no se puede calcular, devuelve un mensaje en español en lugar de un número raro o un error. Los tests comprueban la ida y vuelta: precio → IV → precio.

- [x] Ejecutar `date +%d-%m-%y` y `.venv/bin/python -c "import numpy, scipy, plotly, streamlit, pytest; print(numpy.__version__, scipy.__version__, plotly.__version__, streamlit.__version__, pytest.__version__)"`; confirmar línea base `.venv/bin/pytest -q` → 479 passed.
- [x] Crear `opciones/implied_vol.py`: dataclass `IVResult(vol, message)`; constantes de mensaje en español (pata de acción, días = 0, prima ≤ 0, prima por debajo del límite inferior sin arbitraje, prima por encima del límite superior, fallo del buscador); `implied_vol(leg, market)` con las comprobaciones en el orden: acción → días = 0 → prima ≤ 0 → límites estrictos (call/put con `e^(−qT)`, `e^(−rT)`) → `scipy.optimize.brentq(f, 1e-6, 10, xtol=1e-14, rtol=1e-14)` con `f(σ) = bs_price(...) − prima`; `ValueError` → mensaje; nunca lanza. Datos no numéricos (None, NaN) → mensaje.
- [x] Modificar `opciones/__init__.py`: exportar `implied_vol` e `IVResult` (añadir a `__all__`; sin tocar `analyze()`/`Analysis`).
- [x] Crear `tests/test_implied_vol.py` (primero en rojo): ida y vuelta en rejilla ATM/OTM/ITM × σ ∈ {1 %, 5 %, 25 %, 100 %, 300 %} × T = 1 día (y T = 45 d) × call/put con `bs_price(σ) → implied_vol → |iv − σ| ≤ 1e-9` (AC-A11); prima igual al precio del modelo con `market.vol` → `abs(iv − market.vol) < 1e-9`; prima 0 muy OTM → `vol is None` con mensaje de prima ≤ 0 (no devuelve 1e-6); prima justo en el límite inferior y por debajo (put ITM con prima < intrínseco descontado) → mensaje "por debajo"; prima ≥ límite superior (call con prima ≥ S·e^(−qT); put con prima ≥ K·e^(−rT)) → mensaje "por encima"; días = 0 → mensaje; pata de acción → mensaje; mensajes de los distintos casos son distintos entre sí; entradas con q > 0 y r ≠ 0; nunca lanza (NaN, None, strike 0); `vol` y `message` mutuamente excluyentes.
- [x] Comando: `.venv/bin/pytest tests/test_implied_vol.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** todos los tests nuevos y los 479 del MVP verdes; ida y vuelta con error ≤ 1e-9; ningún camino de IV lanza una excepción.

### Bloque 2 — PoP exacta (AC-A1 parcial, AC-A2, AC-A3)

**Explicación para el usuario:** la probabilidad de beneficio exacta se calcula sin simular nada: buscamos los precios donde el resultado de la estrategia cruza el cero (los breakevens) y los strikes, partimos el eje de precios en tramos, miramos en qué tramos se gana dinero y sumamos la probabilidad lognormal de cada uno. Para un call largo debe coincidir con la fórmula N(d2) del libro (0,3392 en el caso de referencia).

- [x] Crear `opciones/simulation.py`: constante `ZERO_TOL = 1e-7`; dataclass `SimulationSettings(n_paths=100_000, seed=42, mu=None)`; función `exact_pop(market, legs, settings, sim)` (pública dentro del módulo, usada por `simulate_scenario` en el bloque 3): `drift = mu` si no es `None`, si no `rate − q`; fronteras = `[0]` + strikes + `compute_metrics(...).breakevens` (únicos, ordenados); sondeo de `pnl_expiry` en el punto medio de cada intervalo y en `último + max(último, 1)` para la cola derecha; sumar `CDF(b) − CDF(a)` donde P&L > `ZERO_TOL`, cola derecha hasta 1; `CDF(0) = 0`; `CDF(x) = Φ((ln(x/S) − (drift − σ²/2)T)/(σ√T))`. Resultado acotado a [0, 1].
- [x] Crear `tests/test_simulation.py` (primero en rojo), parte PoP exacta: long call ATM S=100, σ=25 %, 45 días, r=4 %, q=1 % → `pytest.approx(0.3392, abs=5e-4)` y igual a N(d2) evaluada en el breakeven de `compute_metrics` (AC-A2, también long put con N(−d2)); long straddle, iron condor (0,5721; corregido en UPDATE PROCESS, ver Lessons Learned), bull call spread, covered call y protective put vs integración independiente con `scipy.integrate.quad` de la densidad lognormal sobre `pnl_expiry > 0` (o rejilla densa como alternativa si `quad` es inestable en los saltos) con `abs=1e-6`; casos PoP = 0 (p. ej. short de beneficio imposible / comisiones que superan el beneficio) y PoP = 1 (estrategia siempre positiva); μ mayor → PoP del long call mayor (monotonía); modo neutral al riesgo usa `rate − q` y modo μ usa μ.
- [x] Comando: `.venv/bin/pytest tests/test_simulation.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** PoP exacta coincide con N(d2)/N(−d2) y con el oráculo independiente; extremos 0 y 1; 479 + nuevos verdes.

### Bloque 3 — Monte Carlo, `ScenarioResult`, validación y avisos (AC-A1, AC-A4, AC-A5, AC-A6, AC-A8, AC-A9, AC-A10, AC-A15, AC-A16)

**Explicación para el usuario:** la simulación lanza 100 000 "precios finales" posibles con una semilla fija (42), calcula el resultado de la estrategia en cada uno y resume: histograma, media (valor esperado, sin descontar) y percentiles 5/50/95. Su probabilidad de ganar debe parecerse a la exacta (una comprobación cruzada). Además añadimos las reglas que rechazan entradas absurdas con mensajes en español y los avisos de limitaciones del modelo.

- [x] Modificar `opciones/simulation.py`: dataclass `ScenarioResult` y `simulate_scenario(market, legs, settings, sim)`: PoP exacta (bloque 2) + MC (`rng = np.random.default_rng(sim.seed)`, `z = rng.standard_normal(n)`, `S_T = S·exp((drift − σ²/2)T + σ√T·z)`, una llamada vectorizada `pnl_expiry`); `pop_mc = mean(pnl > ZERO_TOL)`; `mean_pnl`, `pnl_std`, `p5/p50/p95` con `np.percentile`; histograma ~50 bins sobre el P&L recortado a sus percentiles 0,5–99,5 % (bins de los extremos recogen las colas; suma = `n_paths`); `mu_used`; sin NaN/inf; sin caché, sin reducción de varianza.
- [x] Modificar `opciones/validation.py`: añadir `validate_simulation(market, legs, sim)` (usa las reglas de [Acceptance Criteria](#acceptance-criteria): reutiliza `validate_market`/`validate_legs`; días = 0 mensaje propio; n_paths/seed/μ según A11; nunca lanza) y `scenario_warnings(market)` (modelo ≠ predicción; colas más gruesas; Acción/ETF: americanas sesgan IV y simulación, Índice: europeas; "no es asesoría"). No modificar funciones existentes.
- [x] Modificar `opciones/__init__.py`: exportar `SimulationSettings`, `ScenarioResult`, `simulate_scenario`, `validate_simulation`, `scenario_warnings`.
- [x] Ampliar `tests/test_simulation.py`: misma semilla → resultados idénticos; semilla distinta cambia MC y no `pop_exact` (AC-A8); defaults 100 000 / 42; PoP MC vs exacta dentro de `4·√(p(1−p)/n)` en las estrategias del catálogo (`TEMPLATES` + `build_legs`) (AC-A4); `p5 ≤ p50 ≤ p95`, dentro de [pérdida máx., beneficio máx.] cuando son finitos, `hist_counts.sum() == n_paths` (AC-A5); EV del long call = `100·prima·(e^{rT} − 1) − open_fee − close_fee·P(S_T>K)` dentro de 4·EE de `pnl_std/√n` (AC-A6); media de `S_T` ≈ `S·e^{(r−q)T}` en modo neutral (AC-A1; test sobre las muestras o sobre el estimador equivalente a `ScenarioResult` si no se exponen las muestras: acordar en EXECUTE sin ampliar la API pública más de lo estrictamente necesario) y μ distinto cambia resultados; sin NaN/inf en ningún campo con casos extremos (σ alta, T = 1 día); rendimiento: iron condor con 100 000 trayectorias en < 1 s (AC-A9).
- [x] Ampliar `tests/test_validation.py`: `validate_simulation` rechaza n_paths = 999, 1_000_001, 1.5, "a", True; seed = −1, 2³², 1.5, True; μ = −0,51, 1,01, NaN, inf, "a"; acepta límites 1 000, 1 000 000, 0, 2³²−1, μ = −0,5 y 1,0 y `None`; días = 0, vol = 0 (mensaje existente de `validate_market`), sin patas; lista vacía en caso válido; `scenario_warnings` por subyacente (Acción/ETF americanas, Índice europeas, siempre modelo/colas/no es asesoría) (AC-A15).
- [x] Ampliar `tests/test_analyze.py` (subproceso): `import opciones, opciones.implied_vol, opciones.simulation, sys; assert 'streamlit' not in sys.modules` con `subprocess.run([sys.executable, "-c", ...], check=True, cwd=REPO_ROOT)` (AC-A16).
- [x] Comando: `.venv/bin/pytest tests/test_simulation.py tests/test_validation.py tests/test_analyze.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** todo verde; PoP MC dentro de 4 EE del valor exacto en todo el catálogo; sin NaN/inf; rendimiento < 1 s; `requirements.txt` sin diff.

### Bloque 4 — Interfaz, smoke tests y revisión manual (AC-A5..A7, AC-A8, AC-A10, AC-A13, AC-A14, AC-A15, AC-A17; Hybrid)

**Explicación para el usuario:** en la pestaña Constructor, bajo las métricas, aparece un desplegable "Escenarios (Monte Carlo)" con la PoP exacta y la simulada una al lado de la otra, el histograma del resultado, el valor esperado (marcado "no descontado") y los percentiles. Para cada pata cuya prima editaste a mano verás su volatilidad implícita y un botón para usarla como volatilidad global (con el aviso de que eso cambia todas las primas automáticas y la curva "hoy"). El número de simulaciones y la semilla se editan en Ajustes. Al final te pido revisar a mano lo visual.

- [x] Antes de escribir: comprobación de solo lectura con `.venv/bin/python -c` (o AppTest mínimo) de que en streamlit 1.67 `st.number_input(value=None)` deja el campo vacío y devuelve `None`; si no se comporta así, fallback documentado: `st.text_input` con parseo a número y mensaje de error en español.
- [x] Modificar `app.py`: constantes de colores existentes reutilizadas (`COLOR_EXPIRY`, `COLOR_NEUTRAL`, `COLOR_BREAKEVEN`); `init_state` añade `mu_pct = None`, `n_sims = 100_000`, `seed = 42` con `setdefault`; funciones `sim_settings_from_state()` (μ en % → fracción) y `copy_setting` ya existente para `n_sims`/`seed` (widgets `n_sims_input`/`seed_input` en `render_settings`, sección nueva "Simulación (Etapa A)"), μ en el desplegable con patrón `mu_pct` + `mu_pct_input` (callback de copia).
- [x] En `render_builder`, rama de estrategia válida, tras `render_greeks(...)`: `render_scenarios(market, legs)` con `st.expander("Escenarios (Monte Carlo)")`: validar con `validate_simulation`; si hay errores, `st.error` por cada uno y sin resultados; si no, `simulate_scenario(...)`; mostrar PoP exacta y PoP simulada lado a lado (`st.metric`), etiqueta del escenario (neutral al riesgo / μ del usuario), "Valor esperado (no descontado)", p5/p50/p95, histograma plotly (colores del MVP, línea en cero, pie de figura indicando que los extremos acumulan las colas), `scenario_warnings` visibles. Sin controles ni resultados "hoy" (AC-A7).
- [x] Subsección IV dentro del desplegable: para cada pata con `premium_manual` de tipo opción: `implied_vol(leg, market)`; si `vol` → caption con la IV en % y `st.button("Usar como volatilidad global", key=f"use_iv_{leg_id}", on_click=use_iv_as_global, args=(iv,))` donde el callback hace `st.session_state["vol_pct"] = round(iv * 100, 2)` (en callback, **antes** de renderizar el widget; fijarlo después del render lanza `StreamlitWidgetAlreadyInstantiatedError`); si `message`, mostrarlo. Texto prominente (`st.warning`) junto a los botones: cambia todas las primas automáticas y la curva "hoy"; una σ global no encaja con todos los strikes. Las primas no manuales y "hoy" se recalculan con `refresh_auto_prices` existente (sin lógica nueva).
- [x] Ampliar `tests/test_app_smoke.py` (AppTest): el desplegable "Escenarios (Monte Carlo)" existe bajo las métricas y solo en la rama válida (no hay desplegable con errores de mercado/patas); la etiqueta contiene "(no descontado)"; no hay "hoy" dentro del desplegable (AC-A7); IV: con pata `premium_manual` aparece el botón `use_iv_{leg_id}`, al pulsarlo `session_state["vol_pct"]` toma `round(iv*100, 2)` y los resultados (p. ej. PoP) se recalculan; sin patas manuales no hay botón; mensaje de IV cuando prima fuera de límites; ajustes de `n_sims`/`seed` inválidos muestran mensaje en español sin excepción; días = 0 muestra mensaje de escenarios; MVP intacto (los smoke tests existentes siguen en verde).
- [x] Ejecutar gate completo: `.venv/bin/pytest tests/test_app_smoke.py -q` y luego `.venv/bin/pytest -q` (479 + nuevos, todo verde); `git diff requirements.txt` vacío (AC-A16).
- [x] **Checklist manual para el usuario** (`.venv/bin/streamlit run app.py`; cubre los ACs Hybrid): (1) el desplegable aparece bajo las métricas y no mueve gráfico/métricas/griegas (AC-A14); (2) PoP exacta y simulada visibles lado a lado y parecidas (AC-A4/A5); (3) histograma legible con línea en cero y pie explicando los extremos (AC-A5); (4) "Valor esperado (no descontado)" visible; percentiles p5/p50/p95 (AC-A6); (5) cambiar n_sims y semilla en Ajustes cambia el resultado simulado y no la PoP exacta; mismos valores → mismo resultado (AC-A8); (6) valores inválidos (n_sims = 500, semilla −1, μ = 150) muestran mensajes claros (AC-A10); (7) editar la prima de una pata → IV visible y botón "Usar como volatilidad global"; prima 0 o fuera de límites → mensaje claro (AC-A11/A12); (8) pulsar el botón cambia σ en la barra lateral, las primas automáticas y la curva "hoy", y el texto de aviso es prominente (AC-A13); (9) avisos de modelo/colas/americanas/no es asesoría visibles (AC-A15); (10) la persistencia entre pestañas (Catálogo/Constructor/Ajustes) conserva μ, n_sims y semilla (hueco A-G6, solo manual).
- **Pass criteria:** pytest completo verde; checklist manual aprobada por el usuario antes de marcar el bloque `✅ VERIFIED`.

## Verification Evidence

| Gate / Scenario | Strategy | Proves SPEC criterion |
|---|---|---|
| `.venv/bin/pytest tests/test_simulation.py -q`: media de S_T neutral ≈ S·e^{(r−q)T}; μ cambia PoP en el sentido esperado | Fully-Automated | AC-A1 |
| `.venv/bin/pytest tests/test_simulation.py -q`: PoP exacta long call = N(d2) (0,3392), long put = N(−d2) | Fully-Automated | AC-A2 |
| `.venv/bin/pytest tests/test_simulation.py -q`: PoP exacta de 5 estrategias vs `scipy.integrate.quad`; PoP = 0 y PoP = 1 | Fully-Automated | AC-A3 |
| `.venv/bin/pytest tests/test_simulation.py -q`: PoP MC vs exacta ≤ 4·EE en el catálogo | Fully-Automated | AC-A4 |
| `.venv/bin/pytest tests/test_simulation.py -q` (forma y rango de percentiles, suma del histograma) + smoke AppTest (histograma presente) + checklist manual ítems 2–3 | Hybrid | AC-A5 |
| `.venv/bin/pytest tests/test_simulation.py -q` (EV long call) + smoke AppTest (etiqueta "(no descontado)") + checklist manual ítem 4 | Hybrid | AC-A6 |
| `.venv/bin/pytest tests/test_app_smoke.py -q`: el desplegable no contiene controles ni resultados "hoy" | Fully-Automated | AC-A7 |
| `.venv/bin/pytest tests/test_simulation.py tests/test_validation.py -q` (semilla, defaults, rangos A11) + smoke AppTest + checklist manual ítems 5–6 | Hybrid | AC-A8 |
| `.venv/bin/pytest tests/test_simulation.py -q`: iron condor 100 000 trayectorias < 1 s | Fully-Automated | AC-A9 |
| `.venv/bin/pytest tests/test_validation.py -q` (días = 0, vol = 0, sin patas, μ/n/seed inválidos, sin NaN) + smoke AppTest (mensajes) | Hybrid | AC-A10 |
| `.venv/bin/pytest tests/test_implied_vol.py -q`: ida y vuelta ATM/OTM/ITM, σ 1 %–300 %, T = 1 día; prima = precio del modelo; solo patas `premium_manual` (smoke AppTest) | Fully-Automated | AC-A11 |
| `.venv/bin/pytest tests/test_implied_vol.py -q`: fuera de límites, prima 0, días 0, pata de acción; nunca lanza | Fully-Automated | AC-A12 |
| `.venv/bin/pytest tests/test_app_smoke.py -q`: botón fija `vol_pct` y recalcula; texto de aviso + checklist manual ítem 8 | Hybrid | AC-A13 |
| `.venv/bin/pytest tests/test_app_smoke.py -q`: estructura del desplegable bajo las métricas + checklist manual ítem 1 | Hybrid | AC-A14 |
| `.venv/bin/pytest tests/test_validation.py -q`: `scenario_warnings` según subyacente + checklist manual ítem 9 | Hybrid | AC-A15 |
| `.venv/bin/pytest tests/test_analyze.py -q` (subproceso sin Streamlit con los nuevos módulos) + `git diff requirements.txt` vacío | Hybrid | AC-A16 |
| `.venv/bin/pytest -q` completo desde la raíz (479 MVP + nuevos) | Fully-Automated | AC-A17 |

**Qué demuestra y qué NO demuestra (known gaps, residual):**
- Los tests demuestran exactitud de PoP/IV contra oráculos independientes, no que la lognormal o BS describan el mercado real (A-G1, A-G2: solo avisos).
- AppTest ejecuta todas las pestañas en cada ejecución: no prueba persistencia entre pestañas lazy ni lo visual (A-G6; checklist manual ítems 3 y 10). **Known-Gap, no apto para PASS por sí solo:** estas dos filas quedan condicionadas a la revisión manual del usuario, y se registra un stub de backlog para test visual si se desea.
- El histograma recortado a percentiles 0,5–99,5 % es una decisión de presentación; los percentiles y la media se calculan sobre todos los datos.
- No se verifica rendimiento en el navegador (solo tiempo del motor).

## Matriz de trazabilidad AC-A1..AC-A17

| AC | Bloque | proven by | strategy |
|---|---|---|---|
| AC-A1 | 2 + 3 | media-S_T-neutral + modo-μ-cambia-resultado (`tests/test_simulation.py`) | Fully-Automated |
| AC-A2 | 2 | pop-exacta-long-call-put-oráculo (`tests/test_simulation.py`) | Fully-Automated |
| AC-A3 | 2 | pop-exacta-multi-intervalo-vs-quad + pop-extremos-0-y-1 | Fully-Automated |
| AC-A4 | 3 | pop-mc-vs-exacta-catálogo | Fully-Automated |
| AC-A5 | 3 + 4 | estadísticos-mc-forma-y-rango; histograma (smoke + manual) | Hybrid |
| AC-A6 | 3 + 4 | valor-esperado-long-call-oráculo; etiqueta (smoke) | Hybrid |
| AC-A7 | 4 | alcance-solo-vencimiento (smoke AppTest) | Fully-Automated |
| AC-A8 | 3 + 4 | reproducibilidad-semilla-42 + parámetros-editables-y-validados; Ajustes (smoke + manual) | Hybrid |
| AC-A9 | 3 | rendimiento-iron-condor-100k | Fully-Automated |
| AC-A10 | 3 + 4 | validación-escenarios + sin-NaN-en-resultados; mensajes (smoke) | Hybrid |
| AC-A11 | 1 + 4 | iv-ida-y-vuelta + iv-igual-a-σ-global + iv-solo-patas-premium-manual | Fully-Automated |
| AC-A12 | 1 | iv-fuera-de-límites + iv-prima-cero + iv-días-0 + iv-pata-acción | Fully-Automated |
| AC-A13 | 4 | botón-fija-σ-global-y-recalcula (smoke); texto (smoke + manual) | Hybrid |
| AC-A14 | 4 | bloque-desplegable-bajo-métricas (smoke); disposición (manual) | Hybrid |
| AC-A15 | 3 + 4 | avisos-etapa-A-según-subyacente (test); presencia (manual) | Hybrid |
| AC-A16 | 3 + 4 | motor-importa-sin-Streamlit (subproceso) + requirements.txt sin diff | Hybrid |
| AC-A17 | 1–4 | `.venv/bin/pytest -q` al cierre de cada bloque | Fully-Automated |

## Risk Predictions

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| R1 | La PoP exacta falla con saltos de comisión en strikes (P&L cambia de signo justo en un strike) | Media | Los strikes están entre las fronteras y se sondea el punto medio de cada intervalo; oráculo independiente (`quad`/rejilla densa) y casos con comisión alta |
| R2 | `scipy.integrate.quad` inestable en los saltos del oráculo | Media | Integrar por intervalos entre fronteras o usar rejilla densa (fallback prevista) |
| R3 | `st.number_input(value=None)` no se comporta como se espera en streamlit 1.67 | Baja-Media | Comprobación de solo lectura al inicio del bloque 4; fallback con `st.text_input` + parseo |
| R4 | Fijar `vol_pct` tras renderizar el widget lanza `StreamlitWidgetAlreadyInstantiatedError` | Alta si se hace mal | Botón con `on_click` (el callback corre antes del rerun); verificado en AppTest 1.67; test smoke |
| R5 | Usuario interpreta PoP/EV como predicción o precio justo | Media | Etiquetas ("no descontado", escenario), avisos visibles (AC-A15), "no es asesoría" |
| R6 | La IV de una prima manual extrema da una σ que rompe el resto (σ > 300 %) | Baja | Rango de búsqueda 1e-6–10; la UI muestra el valor y el aviso de σ global; `validate_market` no impone tope (MVP) |
| R7 | Ruido de EE en tests estocásticos genera flakiness | Baja | Semilla fija; tolerancia 4·EE; rejillas fijas |
| R8 | Cada rerun recalcula MC dentro del desplegable | Baja | 0,018 s con 100 000; sin caché por decisión |
| R9 | El test de la media de S_T requiere acceder a las muestras que `ScenarioResult` no expone | Media | Verificar la media vía una función interna de muestreo (`_sample_terminal`) importable en tests, sin ampliar la API pública |

## Out of Scope

Regla de cierre racional de la comisión de cierre (backlog `process/general-plans/backlog/close-fee-rational-close_20-11-26.md`); modelo binomial / americanas exactas; datos de mercado en vivo y cadenas de opciones; MC o PoP para la curva "hoy"; reglas dependientes de la trayectoria; colas gruesas o volatilidad estocástica; comparador y guardado de estrategias; superficie/sonrisa de volatilidad; asesoría de inversión; reducción de varianza y caché de simulaciones; cualquier cambio a `analyze()`, `Analysis`, `metrics.py` o a las decisiones 1–14 del MVP.

## Dependencies

Sin dependencias nuevas: numpy 2.5.5 (`default_rng`), scipy 1.18.1 (`brentq`, `norm`, `integrate.quad` en tests), plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0. Bloques estrictamente secuenciales (comparten `__init__.py`): 3 usa la PoP exacta del 2; 4 usa todo lo anterior.

## Test Infra Improvement Notes

(none identified yet)

## Resume and Execution Handoff

1. **Plan file:** `process/general-plans/completed/etapa-a-montecarlo-iv_20-11-26/etapa-a-montecarlo-iv_PLAN_20-11-26.md` (execute-anchor).
2. **Last completed phase/step:** TODOS los bloques ✅ VERIFIED; plan archivado en `completed/` (ver Current Execution State).
3. **Validate-contract status:** PASS (ver Validate Contract; enmiendas A1-A8 vinculantes).
4. **Supporting context files loaded:** SPEC de la Etapa A; `process/context/all-context.md`; `process/context/tests/all-tests.md`; `process/development-protocols/plan-lifecycle.md`; `implementation-standards.md`; `opciones/*.py`; `app.py`; `tests/test_app_smoke.py`; `tests/test_analyze.py`.
5. **Next step for a fresh agent:** tras VALIDATE, ejecutar el bloque 1 (TDD: `tests/test_implied_vol.py` en rojo → `opciones/implied_vol.py`), gate `.venv/bin/pytest tests/test_implied_vol.py -q` y luego `.venv/bin/pytest -q`; no empezar un bloque con el anterior en rojo; marcar `CODE DONE`, nunca `VERIFIED` sin confirmación del usuario. Nota: vc-execute-agent no puede escribir bajo `process/`; los estados de bloque y el reporte se actualizan en UPDATE PROCESS.

Instrucciones para el agente de EXECUTE:
1. Bloques estrictamente en orden 1 a 4; cada uno cierra con su gate y `.venv/bin/pytest -q` completo.
2. TDD: tests primero (rojo), luego implementación; código simple, identificadores en inglés, comentarios en español.
3. No modificar `analyze()`, `Analysis`, `metrics.py`, `requirements.txt` ni comportamiento del MVP.
4. Bloque 4: comprobar `st.number_input(value=None)` en 1.67 antes de escribir; el botón de IV usa `on_click`.
5. EVL: un vc-tester independiente vuelve a ejecutar cada comando de gate.

## Validate Contract

Status: PASS
Date: 20-11-26
date: 2026-11-20
generated-by: outer-pvl
Pass: first (V1-V3 inline; no subagents; proportionate to a 4-block local project)

Parallel strategy: sequential
Rationale: blocks share `opciones/__init__.py` and each uses the previous one (2 needs 1's export slot, 3 needs 2's `exact_pop`, 4 needs all). No parallel EXECUTE.

Independent prototype evidence (`.venv/bin/python`, existing engine, nothing written to the repo):
- Long call ATM (S=100, sigma 25 %, 45 d, r 4 %, q 1 %, default commissions): breakeven 103.69052; exact PoP by the plan's boundary/midpoint algorithm 0.339215 = N(d2(b)) 0.339215 (MATCH 0.3392). Long put 0.350826 = N(-d2) (MATCH).
- Boundary/midpoint algorithm vs dense lognormal integration (z-grid): all 8 catalog templates x {Accion 100, Indice 4500} x {default fees, 5 USD/contract}: max |diff| about 1e-5 (grid resolution; MATCH within 1e-4). Commission jumps that flip sign exactly at a strike (short call K=105 prem 0.0095: P&L +0.30 / -0.35 across K; short put K=95): exact 0.711432 vs dense 0.711432 (MATCH). Iron condor at fees 0.65/5/20 matches; fee 60 gives PoP 0 (extreme 0 case reproduced); always-positive position gives 1.0.
- MC (100 000, seed 42) vs exact on all 32 template/market/fee combinations: |z| max 2.55 (< 4); no flakiness risk with fixed seed.
- Long-call EV: closed form 100*prem*(e^{rT}-1) - open - close*P(S_T>K) = 0.843504; numeric integration of the engine P&L = 0.843505 (exact match); MC -0.279, SE 1.76, z = -0.64 (inside 4 SE). The naive "- 1.3 commissions" variant gives 0.518, so the formula distinction is real but invisible to the MC test (4 SE is about 7 USD), see amendment A3.
- Mean S_T (seed 42): 100.336 vs S*e^{(r-q)T} 100.371, 1.2 SE (OK).
- mu monotone: PoP long call 0.123 / 0.324 / 0.376 / 0.828 for mu = -50 % / 0 / 10 % / 100 %.
- IV: on a grid of 2 kinds x T {1 d, 45 d} x K {70..130} x sigma {1 %..300 %}, brentq(1e-6, 10, xtol=rtol=1e-14) gives PRICE round trip error <= 3.9e-14 for every point inside the no-arbitrage bounds (AC-A11 as written in the SPEC: PASS). Premium 0, deep OTM call: brentq silently returns 1e-6 (the trap is real; bounds-first ordering rejects it as prem <= 0). Premium above the upper bound: brentq raises ValueError (turned into a message). 21 of 91 grid prices fall on/outside the float no-arbitrage bounds (deep ITM, tiny sigma): correctly "no IV".
- Streamlit 1.67 (AppTest.from_string, in-process, no server): `st.number_input(value=None, key=..., on_change=...)` renders and returns None; typing a value fires the callback; `st.expander` content (metric, warning, button) is visible to AppTest (`at.expander`, `at.metric`, `at.warning`, `at.button(key=...)`); `on_click` callback setting `st.session_state["vol_pct"]` works (20 -> 33.33, widget shows 33.33); setting it after the widget renders raises `StreamlitWidgetAlreadyInstantiatedError` (confirmed). No server was started.

Contract amendments (binding; they refine the plan text, the SPEC is untouched; each one resolves a CONCERN found in V3):
- A1 (IV round trip): the plan's block 1 test "|iv - sigma| <= 1e-9" is NOT achievable for deep ITM / short T (vega about 0: e.g. call K=90, T=1 d, sigma 25 % -> iv differs by 0.023 while the price error is 0). The primary assertion is the PRICE round trip, `abs(bs_price(iv) - premium) <= 1e-9` (observed 4e-14), per SPEC AC-A11. The `|iv - sigma| <= 1e-9` check applies only to ATM and OTM and to ITM within about 5 % of the money at T = 45 d; skip grid points where the premium is not strictly inside the no-arbitrage bounds (assert they yield a message, not a number).
- A2 (oracle tolerance): independent oracle for AC-A3 = `scipy.integrate.quad` of the lognormal density over intervals whose sign is decided by dense sampling of `pnl_expiry` (abs 1e-6), OR a dense z-grid (>= 400 001 points) with tolerance abs 1e-4 (observed diff up to 1e-5, so 1e-6 is not valid for a grid). Add the commission-jump cases (short call K=105 prem 0.0095; short put K=95 prem 0.0095; iron condor with 5 and 20 USD/contract) to the exact-PoP tests.
- A3 (EV test power): add a deterministic check of the EV formula against numeric integration of `pnl_expiry` (z-grid 2 000 001 points, abs 1e-3, reference 0.8435) in addition to the MC within 4 SE test; the MC test alone cannot tell the right formula from "- open - close".
- A4 (mu clearing): AppTest `set_value(None)` does NOT clear a number_input (verified), so "empty mu = risk neutral" cannot be driven by clearing in the smoke test. Test it by initialising `session_state["mu_pct"]` to None and to a value, and add manual checklist item 11: type a mu, then clear the field and confirm the scenario label returns to "neutral al riesgo".
- A5 (no min/max on Settings widgets): do not pass `min_value`/`max_value` to the `n_sims`, `seed` or mu widgets (or the Spanish validation messages become unreachable). Use `step=1` with integer defaults so Streamlit returns ints; `validate_simulation` rejects non-integers and bool.
- A6 (ZERO_TOL): `opciones/metrics.py` already defines `ZERO_TOL = 1e-7`. In `simulation.py` import it (`from .metrics import ZERO_TOL`) instead of redefining it (same value, no duplicate source of truth; importing does not modify metrics.py).
- A7 (block 4 size): block 4 is the largest; execute it as 4a (state, Settings widgets, scenarios expander with PoP/histogram/EV/percentiles/warnings, smoke tests, gate) and 4b (IV subsection, button, warning text, smoke tests, gate). Block 3 may likewise be done as 3a (MC + `ScenarioResult`) and 3b (validation, warnings, subprocess test); run the block gate between sub-steps.
- A8 (`_sample_terminal`): a private `_sample_terminal(market, sim, drift)` in `simulation.py`, imported by the test, is accepted (R9). It must be the same function `simulate_scenario` uses (no duplicated sampling code) and must not be exported in `__init__.py`.

Test gates (all run from repo root; each block also ends with `.venv/bin/pytest -q`; baseline 479 passed):

| criterion id | behavior | strategy | proving test / command | owner |
|---|---|---|---|---|
| AC-A11, AC-A12 | IV price round trip, = global sigma, premium 0 / bounds / days 0 / stock messages, never raises | Fully-Automated | `.venv/bin/pytest tests/test_implied_vol.py -q` then `.venv/bin/pytest -q` | block 1 |
| AC-A1 (exact part), AC-A2, AC-A3 | exact PoP: N(d2) 0.3392, N(-d2), 5 strategies vs oracle, jump cases, PoP 0 and 1, mu monotone | Fully-Automated | `.venv/bin/pytest tests/test_simulation.py -q` then `.venv/bin/pytest -q` | block 2 |
| AC-A1 (mean S_T), AC-A4, AC-A5 (engine), AC-A6 (engine), AC-A8 (engine), AC-A9, AC-A10 (engine) | seed 42 / 100 000 defaults, reproducibility, MC vs exact within 4 SE over `TEMPLATES`, percentile shape/range, hist sum, EV formula (MC + integration), no NaN/inf, iron condor < 1 s | Fully-Automated | `.venv/bin/pytest tests/test_simulation.py -q` | block 3a |
| AC-A8, AC-A10, AC-A15, AC-A16 (import) | `validate_simulation` ranges (A11), `scenario_warnings` by underlying, no-Streamlit subprocess for `opciones.implied_vol` and `opciones.simulation` | Hybrid | `.venv/bin/pytest tests/test_validation.py tests/test_analyze.py -q` then `.venv/bin/pytest tests/test_simulation.py tests/test_validation.py tests/test_analyze.py -q` then `.venv/bin/pytest -q`; manual item 9 | block 3b |
| AC-A5, AC-A6, AC-A7, AC-A8, AC-A10, AC-A14, AC-A15 (UI) | expander under metrics only in valid branch, "(no descontado)" label, no "hoy" inside, Settings n_sims/seed, Spanish messages | Hybrid | `.venv/bin/pytest tests/test_app_smoke.py -q` + manual checklist (items 1-6, 9-11, user-owned) | block 4a |
| AC-A11 (manual-only legs), AC-A12 (UI), AC-A13 | `use_iv_{leg_id}` button only for premium_manual option legs, sets `vol_pct = round(iv*100, 2)` and recomputes, warning text, message on out-of-bounds | Hybrid | `.venv/bin/pytest tests/test_app_smoke.py -q` + manual items 7-8 | block 4b |
| AC-A16 (requirements) | no dependency change | Hybrid | `git diff --stat requirements.txt` empty | block 4b |
| AC-A17 | whole suite green, 479 MVP + new | Fully-Automated | `.venv/bin/pytest -q` | every block |

Failing stubs (Fully-Automated rows; EXECUTE writes them first, TDD): in each test file add `def test_<scenario>(): pytest.fail("NOT IMPLEMENTED - TDD stub: <scenario>")` for every scenario in the block checklist, then replace with real assertions.

Dimension findings:
- Infra fit: PASS - pinned versions present in `.venv`; `scipy.optimize.brentq`, `scipy.stats.norm`, `scipy.integrate.quad` available; every gate command runs from repo root; touchpoints (`opciones/__init__.py`, `validation.py`, `app.py`, `tests/test_analyze.py` subprocess test) exist as described; `ZERO_TOL` already in `metrics.py` (A6).
- Test coverage: PASS (after amendments A1-A5) - AC-A1..AC-A17 and A1-A11 each trace to a block, test file and exact command (matrix above); Hybrid ACs carry the user-owned manual checklist; the two Known-Gaps (A-G6 cross-tab persistence, visuals) are named and cannot rest alone.
- Breaking changes: PASS - additive; `analyze()`, `Analysis`, `metrics.py`, `payoff.py`, `pricing.py` and MVP decisions 1-14 untouched; `validate_simulation` / `scenario_warnings` are new functions in `validation.py`.
- Security surface: PASS - local app, no network, secrets or file I/O; user inputs (n_paths, seed, mu) are range-validated (A11) and a seeded generator only; `subprocess.run` in the test runs a constant string.
- Block 1: PASS with A1. Block 2: PASS (algorithm confirmed by prototype, incl. commission jumps). Block 3: PASS with A2, A3, A6, A8. Block 4: PASS with A4, A5, A7 (Streamlit assumptions confirmed).

Known gaps (named residuals; none is a FAIL):
- A-G1 American bias of IV/MC, A-G2 thin tails, A-G3 one global sigma, A-G4 subjective mu, A-G5 undiscounted EV: warnings only (SPEC).
- A-G6: visual layout, histogram look and cross-tab persistence of mu / n_sims / seed are proven only by the user's manual checklist; AppTest executes all tabs and cannot clear a number_input.
- Browser performance is not measured (engine time only).
- The tests prove agreement with independent oracles, not that lognormal / Black-Scholes describe real markets.

Execute-agent instructions:
1. Blocks strictly 1 -> 2 -> 3 (3a, 3b) -> 4 (4a, 4b); run the block gate and then `.venv/bin/pytest -q` at each step; never start a step with the previous one red. Mark blocks `CODE DONE`, never `VERIFIED` without user confirmation.
2. TDD: failing stubs first, then implement; simple code (dataclasses, short functions), identifiers in English, comments and docstrings in Spanish, UI in Spanish. Apply amendments A1-A8.
3. Execute agents CANNOT write under `process/` (MVP lesson): do not edit this plan, the SPEC or the REPORT; status updates and the report are done in UPDATE PROCESS. Write only `opciones/implied_vol.py`, `opciones/simulation.py`, additions to `opciones/validation.py` and `opciones/__init__.py`, `app.py`, and the test files.
4. Do NOT modify `analyze()`, `Analysis`, `metrics.py`, `payoff.py`, `pricing.py`, `commissions.py`, `catalog.py`, `models.py`, `requirements.txt`, or any MVP behavior (decisions 1-14). Existing validation functions stay unchanged.
5. Order of IV checks is fixed: stock -> days = 0 -> premium <= 0 -> strict no-arbitrage bounds -> `brentq(1e-6, 10, xtol=1e-14, rtol=1e-14)`; `ValueError` becomes a Spanish message; never raise.
6. Block 4: set `st.session_state["vol_pct"]` only inside the `on_click` callback (never after the widget renders); `value=None` for the mu widget is confirmed to work in 1.67 (fallback text_input not needed).
7. If you start a Streamlit server for any check, wrap it in `timeout`, and stop it before finishing; prefer in-process AppTest. Leave no process running.
8. EVL: an independent vc-tester re-runs every gate command above and the final `.venv/bin/pytest -q`.

Plan updates applied: none by the validate agent (role writes only the contract); amendments A1-A8 are binding through this contract.

Gate: PASS
Accepted by: n/a - no FAILs; CONCERNs C1-C7 (IV sigma tolerance, oracle tolerance, EV test power, mu clearing, widget min/max, ZERO_TOL duplication, block size) are resolved by binding amendments A1-A8 inside this contract.

## Current Execution State

**COMPLETE (20-11-26).** Los bloques 1, 2, 3a, 3b, 4a y 4b están implementados, cada uno confirmado por una ejecución EVL independiente de vc-tester y aprobado por el usuario; checklist manual de 11 ítems completada por el usuario ("Todo bien"). AC-A1..AC-A17 cumplidos. Suite final: 910/910, smoke AppTest 29/29, `requirements.txt` sin cambios, módulos del MVP intactos.

| Bloque | Commit | Tests acumulados |
|---|---|---|
| 1 (IV) | d7606f2 | 651 |
| 2 (PoP exacta) | 55bdeea | 686 |
| 3a (Monte Carlo) | d46eddb | 836 |
| 3b (validación/avisos/exportaciones) | 9853668 | 887 |
| 4a (UI de escenarios) | 9689b02 | 900 |
| 4b (UI de IV + arreglo EVL) | f154272 | 910 |

SPEC/plan: f94f9b0. PVL: Gate PASS en la primera pasada con enmiendas vinculantes A1–A8 (A7 dividió los bloques 3 y 4 en 3a/3b y 4a/4b).

## Lessons Learned and Deviations (UPDATE PROCESS)

- **Corrección numérica del plan:** la PoP exacta del iron condor del catálogo con Market('Acción', 100, 0.25, 45, 0.04, 0.01) y comisiones por defecto es **0,5721** (exact_pop 0,572122; la forma cerrada y 1M de muestras MC coinciden), no 0,5323. Ese 0,5323 venía de un prototipo de INNOVATE con otras entradas (probablemente σ≈20 %, 90 días). Texto del plan corregido; las menciones históricas en el Validate Contract no se tocaron. Lección: las cifras de referencia de prototipos de INNOVATE deben recalcularse en PLAN/VALIDATE con las entradas exactas.
- **Desviaciones aceptadas:** `_histogram` ensancha el rango ±0,5 USD cuando el P&L es constante o casi constante (np.histogram fallaba); `MSG_INVALID_DATA` en `implied_vol`; `exact_pop` no se exporta en `__init__` (no está en Public Contracts; se importa de `opciones.simulation`); `validate_simulation` rechaza enteros guardados como float (1000.0); 3 smoke tests del MVP ajustados en 4a (número de gráficos 1→2; días=0 ahora muestra el error del escenario), juzgado legítimo por EVL; helper `leg_from_dict` en `app.py`.
- **EVL ciclo 1 (bloque 4b):** la etiqueta "Valor esperado (no descontado)" de `st.metric` se truncaba → pasó a su propia fila con caption; el smoke test "sin hoy" se acotó a resultados/métricas/gráficos/entradas (avisos excluidos) más una variante con pata manual. Arreglo aprobado por el usuario: se eliminó el aviso "no es asesoría" duplicado del desplegable de escenarios.
- **Lecciones:** `st.metric` trunca etiquetas/valores largos (visto dos veces: breakevens del MVP, etiqueta de VE aquí) → el texto largo va en markdown/caption; el estado de widgets de Streamlit solo se cambia con callbacks `on_click` antes del render (si no, `StreamlitWidgetAlreadyInstantiatedError`); AppTest ejecuta todas las pestañas y no puede vaciar un `number_input` a None.
- **Trampa de nombres:** `opciones/__init__.py` exporta la función `implied_vol`, que oculta el atributo de submódulo `opciones.implied_vol`; usar `from opciones import implied_vol`; el módulo está en `sys.modules['opciones.implied_vol']`.
- **Backlog:** `process/general-plans/backlog/close-fee-rational-close_20-11-26.md` se mantiene (Etapa B).

## Next Step

Etapa A cerrada. Siguiente: Etapa B según el roadmap (modelo binomial para opciones americanas) y, junto a ella, el ítem de backlog de comisión de cierre racional.

PHASE_COMPLETE: UPDATE PROCESS
