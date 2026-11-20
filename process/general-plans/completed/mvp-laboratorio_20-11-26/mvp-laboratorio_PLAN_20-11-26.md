---
name: mvp-laboratorio PLAN
description: "Plan COMPLEX de implementación del MVP v1 de Laboratorio de Opciones en 6 bloques secuenciales, cada uno terminado en pytest verde."
date: 20-11-26
status: completed
complexity: complex
spec: process/general-plans/completed/mvp-laboratorio_20-11-26/mvp-laboratorio_SPEC_20-11-26.md
---

# Plan: MVP (v1) de Laboratorio de Opciones

**Date**: 20-11-26
**Complexity**: COMPLEX (un solo plan, un solo flujo de ejecución, 6 bloques secuenciales)
**Status**: ✅ VERIFIED (MVP completo, archivado 20-11-26)
**SPEC bloqueado**: `process/general-plans/completed/mvp-laboratorio_20-11-26/mvp-laboratorio_SPEC_20-11-26.md` (AC1–AC18, decisiones 1–12, huecos G1–G5)
**Entorno**: Python 3.12.3, `.venv` (numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0)

**TL;DR:** se construye primero un motor puro (`opciones/`, sin Streamlit) en 5 bloques con tests, y solo en el bloque 6 la interfaz `app.py`. Cada bloque termina con `.venv/bin/pytest -q` en verde antes de pasar al siguiente. Las dos decisiones nuevas del usuario (13: días = 0 permitido; 14: comisión de cierre en la curva "hoy") están integradas.

## Overview

Se implementa el MVP descrito en el SPEC: introducir a mano precio, volatilidad, días, tipo de interés y dividendo; montar patas (call, put, acción); ver P&L "hoy" y "al vencimiento", métricas exactas (beneficio máx., pérdida máx., breakevens, "ilimitado"), griegas de la posición, comisiones configurables y un catálogo de 8 estrategias. El motor es un paquete Python plano `opciones/` (sin Streamlit ni I/O); la UI es un único `app.py` en la raíz con tres pestañas (Catálogo, Constructor, Ajustes).

Contexto leído: `process/context/all-context.md`, `process/context/tests/all-tests.md` (router; no hay docs de test más profundos todavía), `process/development-protocols/plan-lifecycle.md`, `process/development-protocols/implementation-standards.md`, `DISENO.md`, y el SPEC.

## Quick Links

- [Decisiones bloqueadas](#decisiones-bloqueadas-1-14)
- [Chosen Approach / Why This Over Alternatives](#chosen-approach-y-por-qué-este-camino)
- [Phase Completion Rules](#phase-completion-rules)
- [Acceptance Criteria](#acceptance-criteria)
- [Touchpoints](#touchpoints) · [Public Contracts](#public-contracts) · [Blast Radius](#blast-radius)
- [Implementation Checklist (bloques 1–6)](#implementation-checklist)
- [Verification Evidence](#verification-evidence) · [Matriz de trazabilidad AC](#matriz-de-trazabilidad-ac1ac18)
- [Risk Predictions](#risk-predictions) · [Out of Scope](#out-of-scope)
- [Test Infra Improvement Notes](#test-infra-improvement-notes) · [Resume and Execution Handoff](#resume-and-execution-handoff) · [Validate Contract](#validate-contract)

## Status strip

| Bloque | Contenido | Estado |
|---|---|---|
| 1 | `models.py` + `pricing.py` + tests + `requirements.txt` | ✅ VERIFIED |
| 2 | `payoff.py` + `commissions.py` + tests | ✅ VERIFIED |
| 3 | `metrics.py` + tests | ✅ VERIFIED |
| 4 | `validation.py` + `analyze()` + tests | ✅ VERIFIED |
| 5 | `catalog.py` + tests | ✅ VERIFIED |
| 6 | `app.py` + smoke AppTest + revisión manual Hybrid | ✅ VERIFIED |

## Decisiones bloqueadas (1–14)

Las decisiones 1–12 están en el SPEC (no se repiten aquí; el SPEC manda). Decisiones adicionales del usuario posteriores al SPEC (20-11-26):

| # | Decisión |
|---|---|
| 13 | **Días al vencimiento = 0 está PERMITIDO** con un aviso informativo: las curvas se calculan (la curva "hoy" iguala el valor intrínseco) y las griegas se muestran como "—". Errores bloqueantes solo para: días < 0; volatilidad <= 0 (con un suelo pequeño, p. ej. vol >= 0,01 %); spot, strike, prima o cantidad negativos o vacíos. *(Esto refina decisión 10 y AC1: AC1 ya no trata días = 0 como error.)* |
| 14 | La curva **"hoy"** resta comisión de apertura **más** comisión de cierre en cada pata de opción cuando "incluir cierre" está activo (liquidación hoy; sin excepción por "sin valor"). La curva **al vencimiento** mantiene la decisión 6: sin comisión de cierre en patas que vencen sin valor (incluido S = K). |

Interpretación fijada para el tope de vol: constante `MIN_VOL = 0.0001` (0,01 % expresado como fracción) en `models.py`; `vol < MIN_VOL` → error bloqueante. Constante `MAX_VOL` no se introduce en el MVP (YAGNI).

## Chosen Approach y por qué este camino

**Chosen Approach (INNOVATE):** paquete plano `opciones/` con módulos pequeños de una sola responsabilidad y una API pública mínima en `opciones/__init__.py`; el motor calcula todo (incluidas comisiones) en una única función de P&L por pata que es la fuente de verdad para gráfico y métricas; `app.py` solo dibuja y recoge entradas.

**Why This Over Alternatives:**
- *Subpaquetes o clases con herencia (Option, Stock, Strategy)* → más archivos y conceptos para un principiante; una sola `Leg` con `kind` y `side` es más fácil de leer y de testear.
- *Métricas por muestreo numérico del gráfico (máx./mín. del array, breakevens por interpolación)* → inexacto en los saltos de comisión y en los strikes; las métricas exactas por tramos usan la misma función de P&L y heredan comisiones sin duplicar lógica.
- *Streamlit con widgets de tabla editable (`st.data_editor`)* → no permite botones por fila ni el indicador `premium_manual`; filas de widgets por pata dan control total.
- *Tests de UI solo manuales (G3 original)* → G3 queda resuelto con `streamlit.testing.v1.AppTest` como smoke test; lo visual sigue siendo revisión manual.

**Key Constraints Accepted:**
- Nivel básico de Python: sin metaclases, sin decoradores propios, funciones cortas; identificadores en inglés, comentarios/docstrings en español.
- La comisión de cierre crea un **salto** en el P&L al vencimiento en cada strike (la opción deja de estar "ITM estricta"); se acepta y se documenta en pantalla.
- Black-Scholes aproxima las americanas (G2) y G1 (recargo de índices 0,60 USD) queda sin verificar contra un broker real; ambos se muestran como avisos/valores configurables.
- Pestañas Streamlit perezosas (lazy): el estado crítico no puede vivir solo en widgets de una pestaña (ver bloque 6).
- Un único vencimiento común; sin datos de mercado en vivo.

## Arquitectura del motor

```
app.py (UI Streamlit, raíz)
   │  usa solo la API pública
   ▼
opciones/__init__.py  ── validate_market, validate_legs, default_premium,
   │                      catalog access, analyze(market, legs, settings) -> Analysis
   ├─ models.py       Leg, Market, CommissionSettings, constantes
   ├─ pricing.py      bs_price (vectorizado en S), bs_greeks, default_premium
   ├─ commissions.py  open_fee, close_fee_expiry, close_fee_today
   ├─ payoff.py       pnl por pata/estrategia al vencimiento y hoy, position_greeks, price_grid
   ├─ metrics.py      métricas exactas al vencimiento (tramos lineales)
   ├─ validation.py   mensajes en español + avisos Acción/ETF/Índice
   └─ catalog.py      Template (8) + textos en español + build_legs
```

Flujo de datos de `analyze()`: `Market + legs + settings` → `price_grid` → `pnl_expiry` (suma de patas, con comisiones) y `pnl_today` (BS + comisiones decisión 14) → `metrics` (solo al vencimiento) → `position_greeks` (hoy) → `Analysis` (grid, expiry curve, today curve, metrics, position Greeks, commission total). Sin entradas válidas, la UI no llama a `analyze()`.

## Phase Completion Rules

A phase is NOT complete until:

1. **Integration Test** - Works with other system pieces (cada bloque se prueba junto a los anteriores con `.venv/bin/pytest -q`)
2. **Manual Test** - User can perform the action (bloque 6; en los bloques 1–5 el usuario puede reproducir los valores de referencia en la consola de Python con `.venv/bin/python -c ...`)
3. **Data Verification** - State/values confirmed (valores de libro: Hull, casos de comisiones calculados a mano; no hay base de datos)
4. **Error Handling** - Failure cases handled gracefully (entradas inválidas devuelven mensajes, nunca NaN ni excepciones sin control hacia la UI)
5. **User Confirmation** - User says "it works"

Status meanings:
- ⏳ PLANNED - Not started
- 🔨 CODE DONE - Written but not E2E tested
- 🧪 TESTING - Currently being tested
- ✅ VERIFIED - Tested AND confirmed working
- 🚧 BLOCKED - Has issues

After each phase (block), document in the block's report (`process/general-plans/completed/mvp-laboratorio_20-11-26/mvp-laboratorio_REPORT_20-11-26.md`, creado por EXECUTE; no por este plan):
- [x] What was tested manually
- [x] Values verified (consola `.venv/bin/python -c ...` + salida de pytest)
- [x] Errors encountered and fixed
- [x] User confirmation received

Regla honesta de estado: un bloque con tests verdes y sin que el usuario lo haya revisado es `🔨 CODE DONE`, no `✅ VERIFIED`. Solo el usuario pasa un bloque a `✅ VERIFIED`.

## Acceptance Criteria

Se heredan literalmente **AC1–AC18 del SPEC** (no se reescriben aquí). Cambios de interpretación por las decisiones 13 y 14:

- **AC1 (refinado por decisión 13):** días < 0, vol < `MIN_VOL`, spot/strike/prima/cantidad negativos o vacíos → mensaje en español y sin resultados; **días = 0 → aviso informativo, curvas calculadas, "hoy" = valor intrínseco, griegas "—"**.
- **AC13/AC14 (refinado por decisión 14):** la curva "hoy" incluye comisión de cierre para toda pata de opción si "incluir cierre"; la curva al vencimiento sigue la regla de decisión 6.
- **AC18:** `.venv/bin/pytest -q` pasa completo desde la raíz y el motor se importa sin Streamlit.

La trazabilidad completa AC → bloque → test está en [Matriz de trazabilidad](#matriz-de-trazabilidad-ac1ac18).

## Touchpoints

Archivos a crear (todos nuevos salvo los marcados "modificar"):

| Bloque | Archivo | Acción |
|---|---|---|
| 1 | `opciones/models.py` | crear |
| 1 | `opciones/pricing.py` | crear (`bs_price`, `bs_greeks`, `default_premium`) |
| 1 | `opciones/__init__.py` | modificar (re-exportar lo mínimo al final de cada bloque; `default_premium` desde el bloque 1) |
| 1 | `requirements.txt` | modificar (fijar versiones de la decisión 11) |
| 1 | `tests/test_pricing.py` | crear |
| 2 | `opciones/commissions.py` | crear |
| 2 | `opciones/payoff.py` | crear |
| 2 | `tests/test_legs_payoff.py`, `tests/test_commissions.py` | crear |
| 3 | `opciones/metrics.py` | crear |
| 3 | `tests/test_metrics.py` | crear |
| 4 | `opciones/validation.py` | crear |
| 4 | `opciones/__init__.py` | modificar (`validate_market`, `validate_legs`, `market_warnings`, `analyze`, `Analysis`; `default_premium` ya exportada desde el bloque 1 y se mantiene en la API pública) |
| 4 | `tests/test_validation.py`, `tests/test_analyze.py` | crear |
| 5 | `opciones/catalog.py` | crear |
| 5 | `opciones/__init__.py` | modificar (acceso al catálogo) |
| 5 | `tests/test_catalog.py` | crear |
| 6 | `app.py` (raíz) | crear |
| 6 | `tests/test_app_smoke.py` | crear |
| Cierre | `process/context/all-context.md`, `process/context/tests/all-tests.md` | modificar en UPDATE PROCESS (no en EXECUTE de código) |

Solo lectura: `DISENO.md`, el SPEC, `process/development-protocols/*`. Existentes sin tocar: `tests/__init__.py`.

## Public Contracts

Contratos visibles para `app.py` y los tests (firmas y semántica; el código lo escribe EXECUTE):

| Elemento | Contrato |
|---|---|
| `Leg` (dataclass) | `kind` ∈ {"call","put","stock"}; `side` ∈ {+1,-1}; `quantity` (>0); `strike` (None si stock); `price` (prima en opciones, precio de entrada en acciones); propiedad `multiplier` = 100 (opción) / 1 (acción) |
| `Market` (dataclass) | `underlying` ∈ {"Acción","ETF","Índice"}; `spot`; `vol` (fracción, 0.20 = 20 %); `days`; `rate`; `q` (defecto 0); propiedad `T = days/365` |
| `CommissionSettings` | `per_contract=0.65`, `index_surcharge=0.60`, `include_close=True` |
| Constantes (`models.py`) | `MIN_VOL = 0.0001`, `DAYS_PER_YEAR = 365`, `OPTION_MULTIPLIER = 100` |
| `bs_price(kind, S, K, r, q, sigma, T)` | `S` escalar o array numpy; devuelve array/escalar sin NaN. `T <= 0` → valor intrínseco; `sigma <= 0` → límite determinista `max(S·e^(−qT) − K·e^(−rT), 0)` (put análogo) |
| `bs_greeks(kind, S, K, r, q, sigma, T)` | devuelve delta, gamma, theta (por día, /365), vega (por punto), rho (por punto); lanza `ValueError` si `T <= 0` o `sigma <= 0` (la UI muestra "—") |
| `open_fee(leg, market, settings)` | opciones: `quantity × (per_contract + recargo si Índice)`; acciones: 0 |
| `close_fee_expiry(leg, S, market, settings)` | solo si `include_close` y la opción vence ITM **estricta** (call S > K, put S < K); acciones 0 |
| `close_fee_today(leg, market, settings)` | si `include_close`: igual tarifa que apertura para toda pata de opción (decisión 14); acciones 0 |
| `pnl_expiry(legs, market, settings, S)` / `pnl_today(...)` | P&L total de la estrategia (suma de patas) con comisiones; pata = `side × quantity × multiplier × (valor − price) − comisiones` |
| `position_greeks(legs, market)` | griega de posición = griega × `multiplier` × `quantity` × `side`; acción: delta = `side × quantity`, resto 0; con `days = 0` devuelve `None` por griega (UI "—") |
| `price_grid(market, legs)` | `linspace` en ~±30 % del spot ampliado para cubrir todos los strikes, unido a strikes y strikes ± 1e-9 (para dibujar el salto de comisión) |
| `compute_metrics(...)` → `Metrics` | `best_pnl`, `worst_pnl`, `profit_unlimited`, `loss_unlimited`, `breakevens` (lista, posiblemente vacía) |
| `validate_market(market)` / `validate_legs(legs)` | lista de mensajes de error en español (vacía = válido) + lista aparte de avisos informativos (decisión 13) |
| `market_warnings(market)` | avisos: "no es asesoría" siempre; aproximación americana (más fuerte en puts) para Acción/ETF; nota europea para Índice; aviso informativo si `days == 0`; nota de comisión de cierre |
| `default_premium(kind, market, strike)` | definida en `opciones/pricing.py` (bloque 1), re-exportada desde `opciones/__init__.py`; precio BS con datos globales (0 si el cálculo no es posible); es parte de la API pública final (bloque 4) y la usan `build_legs` (bloque 5) y la UI |
| Catálogo | `catalog.TEMPLATES` (exactamente 8 `Template`), `build_legs(template, market)` |
| `analyze(market, legs, settings)` → `Analysis` | dataclass con `grid`, `expiry_curve`, `today_curve`, `metrics`, `greeks`, `commission_total`; precondición: entradas ya validadas |

Sin cambios en CLI, red, ficheros ni formatos persistentes. No hay APIs externas.

## Blast Radius

- **Archivos**: ~10 de código nuevo (`opciones/*.py` ×7, `app.py` ×1) + ~8 de tests + `requirements.txt` + 2 docs de contexto al cierre. Repo prácticamente vacío (solo `opciones/__init__.py` y `tests/__init__.py`), por lo que no se rompe código existente.
- **Clase de riesgo**: baja a nivel de despliegue (app local, sin datos de usuario, sin red, sin secretos); **media a nivel de corrección financiera** (cálculos de P&L, griegas y métricas que el usuario podría usar para estudiar). La defensa es el conjunto de tests contra valores de libro y casos calculados a mano.
- **Acoplamiento**: `app.py` depende solo de la API pública de `opciones/__init__.py`; ningún módulo del motor importa Streamlit (verificado por test de import en AC18).
- **Rollback**: bloques aditivos; deshacer = borrar los archivos del bloque (no hay migraciones). `requirements.txt` es el único archivo existente modificado.

## Implementation Checklist

Orden estricto; cada bloque termina con pytest verde. Reglas transversales: funciones cortas, comentarios en español, `pytest.approx` en floats, un archivo por responsabilidad, ningún `print` en el motor.

### Bloque 1 — Modelos y precios Black-Scholes (AC2, AC6, AC7, AC8 parcial, T=0)

**Explicación para el usuario:** aquí nace la "calculadora" de precios: guardamos los datos del mercado y de cada pata en pequeñas clases, y escribimos la fórmula de Black-Scholes con dividendo. Los tests comparan contra los números del libro de Hull (call 4,7594, put 0,8086…) para estar seguros de que la fórmula es correcta antes de construir nada encima.

- [x] Ejecutar `date +%d-%m-%y` y `.venv/bin/python -c "import numpy, scipy, plotly, streamlit, pytest; print(numpy.__version__, scipy.__version__, plotly.__version__, streamlit.__version__, pytest.__version__)"` para reconfirmar versiones.
- [x] Fijar `requirements.txt` con `numpy==2.5.5`, `scipy==1.18.1`, `plotly==7.1.0`, `streamlit==1.67.0`, `pytest==9.2.0` (decisión 11).
- [x] Crear `opciones/models.py`: `Leg`, `Market`, `CommissionSettings`, constantes (`MIN_VOL`, etc.).
- [x] Crear `opciones/pricing.py`: `bs_price` vectorizada en `S` (scipy.stats.norm), con guardas `T <= 0` y `sigma <= 0`; `bs_greeks` en unidades prácticas; nunca devolver NaN; `default_premium(kind, market, strike)` (usa `bs_price` con `market.spot`, `market.rate`, `market.q`, `market.vol`, `market.T`; devuelve 0 si el cálculo no es posible).
- [x] Crear/modificar `opciones/__init__.py` en este bloque: re-exportar `Leg`, `Market`, `CommissionSettings`, `bs_price`, `bs_greeks` y `default_premium`.
- [x] Crear `tests/test_pricing.py`: Hull (S=42, K=40, r=0,10, σ=0,20, T=0,5 → call 4,7594, put 0,8086, delta call 0,7791); S=K=100, r=0,05, σ=0,20, T=1, q=0 → call 10,4506, put 5,5735; greeks de referencia (delta 0,6368, gamma 0,018762, vega 0,3752, theta −0,01757/día, rho 0,5323); paridad put-call con q = 0 y q > 0 en varios casos; q distinto de 0 altera precio y delta (AC2); `T = 0` devuelve valor intrínseco; `sigma = 0` devuelve límite determinista sin NaN; `bs_greeks` lanza `ValueError` en `T = 0` y `sigma = 0`; `default_premium` igual a `bs_price` con los datos del `Market` y 0 si el cálculo no es posible (AC4); entradas array y escalar dan el mismo resultado; `S` muy pequeño o muy grande sin NaN.
- [x] Comando: `.venv/bin/pytest tests/test_pricing.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** todos los tests verdes; los valores de referencia coinciden con `pytest.approx` (tolerancia de 4 decimales en precios del libro).

### Bloque 2 — Patas, P&L y comisiones (AC3, AC4, AC5, AC9 parcial, AC13, AC14 parcial)

**Explicación para el usuario:** una "pata" es una compra o venta de una opción (o de acciones). Aquí calculamos cuánto gana o pierde cada pata al vencimiento y "hoy", y le restamos las comisiones. Las comisiones se calculan en un único sitio para que gráfico y métricas coincidan siempre.

- [x] Crear `opciones/commissions.py`: `open_fee`, `close_fee_expiry` (ITM estricta), `close_fee_today` (decisión 14); recargo de índice solo si `market.underlying == "Índice"`; acciones pagan 0.
- [x] Crear `opciones/payoff.py`: `pnl_expiry` y `pnl_today` por pata y de estrategia (comisiones restadas dentro); `position_greeks`; `price_grid`.
- [x] Crear `tests/test_commissions.py`: 0,65 USD por contrato por defecto; +0,60 en Índice (1 contrato = 1,25 por tramo); `quantity = 3` triplica; acción = 0; `include_close = False` → solo apertura; call S = K → sin comisión de cierre; call S = K + 0,01 → con cierre; put S = K − 0,01 → con cierre; vence sin valor → sin cierre; **curva "hoy" cobra cierre en toda pata de opción incluso muy OTM (decisión 14)**.
- [x] Crear `tests/test_legs_payoff.py`: P&L por pata long/short call, put, acción con comisiones a cero (fórmula AC5); multiplicador 100 vs 1; prima editada se usa en el P&L (AC4); la prima por defecto (`default_premium`, definida en el bloque 1) se usa al crear patas (AC4); suma de patas igual a `pnl_expiry` de la estrategia (AC9); `price_grid` cubre todos los strikes aunque estén lejos del ±30 %, incluye los strikes y strikes ± 1e-9 (AC9); `pnl_today` con `days = 0` igual al valor intrínseco menos comisiones (AC1 parcial); `position_greeks` con signos long/short, delta de acción ±quantity, resto 0, y `None` con `days = 0` (AC8 parcial).
- [x] Comando: `.venv/bin/pytest tests/test_legs_payoff.py tests/test_commissions.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** verde; al menos un caso calculado a mano por regla de comisión.

### Bloque 3 — Métricas exactas al vencimiento (AC10, AC11, AC12, AC14 parcial)

**Explicación para el usuario:** el beneficio y la pérdida máximos no se estiman mirando el gráfico, se calculan exactamente: el P&L al vencimiento son tramos rectos que cambian de pendiente en los strikes. Evaluamos esos tramos y detectamos si la cola crece sin límite ("ilimitado"). Las comisiones hacen un pequeño escalón en cada strike y el cálculo lo respeta.

- [x] Crear `opciones/metrics.py` con el algoritmo fijado: `kinks = [0] + strikes únicos ordenados`; para cada intervalo evaluar `pnl_expiry` en dos puntos interiores → pendiente e intersección (misma función de P&L, comisiones incluidas); cola derecha con `Kmax + 1` y `Kmax + 2`; pendiente de cola > 0 → beneficio "ilimitado"; < 0 → pérdida "ilimitada"; lado izquierdo acotado (S >= 0).
- [x] Máx./mín.: valores alcanzados en S = 0, en cada K (`pnl_expiry(K)`) y en extremos de intervalos acotados (límites laterales de tramos contiguos).
- [x] Breakevens: raíces dentro de cada tramo abierto; en un strike, reportar K si los límites izquierdo/derecho tienen signo opuesto (cruce por salto) o `P(K) == 0`; deduplicar con tolerancia; tramo plano en cero → sin breakeven interior.
- [x] Crear `tests/test_metrics.py` (valores de libro, comisiones a cero): long call (pérdida = prima×100, beneficio ilimitado, 1 breakeven K + prima); long put (no ilimitado); short call (pérdida ilimitada); short put (no ilimitado); straddle (beneficio ilimitado, 2 breakevens); bull call spread (nunca pierde más de lo pagado; AC10); bear put spread; iron condor (2 breakevens, pérdida máx. acotada); covered call; protective put; sin breakeven (p. ej. P&L siempre positivo); varios breakevens.
- [x] Casos de comisión **calculados a mano** (1 contrato por pata, 0,65 USD, incluir cierre activo; el EXECUTE reconfirma las cuentas al escribir el test):
  - Call corto K=100, prima 2,00: beneficio máx. 199,35 (alcanzado en S ≤ 100; salto de −0,65 justo por encima de K), pérdida ilimitada, breakeven ≈ 101,987.
  - Bull call spread largo 100 @ 3,00 / corto 110 @ 1,00: pérdida máx. −201,95 (corregido en UPDATE PROCESS: justo por encima de S = 100 el call largo es ITM estricto y paga la comisión de cierre de 0,65; −201,30 es solo P(100)); **beneficio máx. 798,05 alcanzado exactamente en S = 110** (el corto no es ITM estricto en K; a la derecha la meseta es 797,40); breakeven ≈ 102,0195. Comisiones a cero: beneficio 800, pérdida 200, breakeven 102.
  - Condor corto put 95 @ 1,50 / largo put 90 @ 0,50 / corto call 105 @ 1,50 / largo call 110 @ 0,50: sin comisiones → beneficio 200, pérdida 300, breakevens 93 y 107; con comisiones → beneficio 197,40 (meseta 95–105), pérdida −303,90, breakevens ≈ 93,0325 y ≈ 106,9675.
- [x] Escenarios límite: un solo strike; dos patas en el mismo strike (deduplicar kinks); solo patas de acción (sin strikes, pendiente única); estrategia con P&L plano (sin breakeven); P&L exactamente 0 en un strike; strikes muy próximos (tolerancia); pata de acción + opción (covered call).
- [x] Comando: `.venv/bin/pytest tests/test_metrics.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** verde; el AC10 "bull spread nunca pierde más de lo pagado" se prueba con comisiones a cero.

### Bloque 4 — Validación y `analyze()` (AC1, AC17, AC18 parcial, decisión 13)

**Explicación para el usuario:** antes de calcular nada, comprobamos que los datos tienen sentido y, si no, devolvemos un mensaje claro en español. También creamos `analyze()`, la única función que la interfaz llamará para obtener gráfico, métricas y griegas de golpe.

- [x] Crear `opciones/validation.py`: `validate_market`, `validate_legs`, `market_warnings`, con mensajes en español y la regla de la decisión 13 (días = 0 es aviso, no error).
- [x] Completar `opciones/__init__.py`: exponer `validate_market`, `validate_legs`, `market_warnings`, `analyze`, `Analysis`, modelos y `CommissionSettings`; verificar que `default_premium` (re-exportada desde el bloque 1) sigue en la API pública.
- [x] Implementar `analyze()` encadenando `price_grid` → `pnl_expiry`/`pnl_today` → `compute_metrics` → `position_greeks` → total de comisiones.
- [x] Crear `tests/test_validation.py`: días < 0 → error; días = 0 → sin error + aviso informativo; vol = 0, vol < `MIN_VOL`, vol negativa → error; spot, strike, prima, cantidad negativos o `None`/vacíos → error; spot = 0 → error; estrategia sin patas → mensaje claro; avisos por subyacente (Acción/ETF → aproximación americana con énfasis en puts y "~7 %"; Índice → europea; siempre "no es asesoría"); los mensajes son texto en español no vacío.
- [x] Crear `tests/test_analyze.py`: `analyze()` con días = 0 → curva "hoy" = intrínseco, griegas `None`; con días > 0 → griegas presentes; curvas sin NaN en todo el grid (incl. vol cerca de `MIN_VOL` y T muy pequeño); el motor se importa sin Streamlit en un intérprete nuevo, independiente del orden de tests: `subprocess.run([sys.executable, "-c", "import opciones, sys; assert 'streamlit' not in sys.modules"], check=True)` (no se usa `sys.modules` del proceso de pytest); curva al vencimiento de `analyze()` = suma de patas.
- [x] Comando: `.venv/bin/pytest tests/test_validation.py tests/test_analyze.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** verde; ningún camino de entradas inválidas lanza excepción hacia fuera.

### Bloque 5 — Catálogo de 8 estrategias (AC15, AC16 motor)

**Explicación para el usuario:** cada estrategia del catálogo es una "plantilla": un texto explicativo en español y una lista de patas descritas en porcentaje respecto al spot. `build_legs` convierte la plantilla en patas reales redondeando los strikes a valores razonables y calculando la prima con Black-Scholes.

- [x] Crear `opciones/catalog.py`: `Template` (key, nombre, visión de mercado, qué apuesta, beneficio/pérdida máx., cuándo usarla, riesgos, y especificaciones de pata: kind, side, `strike_offset_pct`, quantity); exactamente 8 plantillas (long call, long put, covered call, protective put, bull call spread, bear put spread, long straddle, iron condor); textos en español dentro del módulo.
- [x] `build_legs(template, market)`: redondeo de strikes por tramos (0,5 bajo 25; 1 bajo 100; 2,5 bajo 250; 5 bajo 1000; 5 o más por encima), primas con `default_premium` (BS), patas de acción de 100 acciones a precio = spot; strikes ordenados y coherentes (p. ej. bull spread: strike largo < strike corto).
- [x] Crear `tests/test_catalog.py`: exactamente 8 claves esperadas; todos los campos de texto presentes y no vacíos; `build_legs` produce patas válidas (`validate_legs` sin errores) para spots 20, 99, 100, 250, 1000 y 4500 e `Índice`/`Acción`; redondeo por tramos en los límites (24,9 / 25 / 99,9 / 100 / 249 / 250 / 999 / 1000); métricas de libro por plantilla vía `analyze()` (comisiones a cero y con valores por defecto): long call/put, covered call (beneficio acotado, pérdida muy grande), protective put (pérdida acotada), bull call spread, bear put spread, straddle (2 breakevens, beneficio ilimitado), iron condor (2 breakevens); strikes distintos tras el redondeo incluso con spot bajo (sin patas degeneradas).
- [x] Comando: `.venv/bin/pytest tests/test_catalog.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** verde; cada plantilla produce métricas coherentes con su descripción textual.

### Bloque 6 — Interfaz Streamlit `app.py` (AC3, AC9, AC14, AC16, AC17 interfaz; AC18)

**Explicación para el usuario:** ahora se dibuja la app: datos globales en la barra lateral, tres pestañas (Catálogo, Constructor, Ajustes), filas de patas editables y el gráfico con la curva "hoy" y la de vencimiento. La UI no calcula nada: solo llama al motor. Como Streamlit no se puede probar del todo con tests, al final harás una revisión visual guiada con una lista.

Antes de escribir (EXECUTE): invocar `vc-frontend-design` para decisiones de maquetación y `vc-docs-seeker` para confirmar `st.tabs(..., key=, on_change="rerun")` y el comportamiento de pestañas perezosas y `persist_state` (parámetro de widgets como `number_input`, `selectbox`, `radio`, `segmented_control`, `checkbox`, con valores "page", "session" o None; NO de `st.tabs`) en Streamlit 1.67.0. Comprobaciones de solo lectura con `.venv/bin/python -c ...` permitidas.

- [x] Barra lateral (siempre renderizada): subyacente (Acción/ETF/Índice), spot, volatilidad (%), días, tipo (%), dividend yield q (defecto 0). Mostrar errores (`validate_market`) y avisos (`market_warnings`) y no llamar a `analyze()` si hay errores.
- [x] Navegación: `st.tabs(["Catálogo","Constructor","Ajustes"], key="main_tab", on_change="rerun")`; el botón "abrir en el constructor" fija `st.session_state["main_tab"] = "Constructor"` dentro de su callback (verificado en 1.67). Fallback documentado: radio/segmented control si las pestañas fallan.
- [x] Estado: `st.session_state.legs` como lista de dicts con `id` monotónico y bandera `premium_manual`; el `on_change` del input de prima fija `premium_manual = True`; las primas no manuales se reescriben con el valor BS en cada rerun; botón "↺ BS" por fila restablece; las primas manuales se conservan al cambiar los datos globales.
- [x] Ajustes: valores de comisión y `legs` en entradas simples de `st.session_state` actualizadas por callbacks (`on_change`), nunca solo como estado interno de widgets de pestañas; los datos de mercado viven en la barra lateral (siempre renderizada). Opcional: `persist_state="session"` en los widgets de Ajustes como refuerzo. La persistencia entre pestañas perezosas solo se prueba de verdad con el ítem 9 de la checklist manual.
- [x] Constructor: filas por pata (tipo, dirección, strike, cantidad, prima, quitar) + "+ añadir pata"; gráfico Plotly: vencimiento línea sólida, "hoy" discontinua, línea de cero, marcador de spot, marcadores de breakevens; `st.plotly_chart(fig, width="stretch")`; métricas ("ilimitado" cuando proceda), tabla de griegas ("—" con días = 0) y total de comisiones.
- [x] Avisos visibles: "no es asesoría"; aproximación americana (más fuerte en puts) para Acción/ETF; nota europea para Índice; nota corta "comisión de cierre solo si la opción vence con valor"; aviso informativo con días = 0.
- [x] Crear `tests/test_app_smoke.py` con `streamlit.testing.v1.AppTest`: la app carga sin excepción; "abrir" una plantilla del catálogo rellena `legs` y cambia a "Constructor"; los valores de comisión de `session_state` se aplican al resultado (cambiar `per_contract` por callback cambia el total de comisiones) — este test NO prueba persistencia entre pestañas, porque AppTest ejecuta el cuerpo de todas las pestañas; días = 0 produce aviso (no error) y la app no falla; con vol = 0 hay mensaje de error y no hay gráfico.
- [x] Comandos: `.venv/bin/pytest tests/test_app_smoke.py -q`, luego `.venv/bin/pytest -q` (puerta AC18), luego revisión manual con `.venv/bin/streamlit run app.py`.
- [x] **Checklist de revisión manual (criterios Hybrid, la hace el usuario):** (1) la app abre con tres pestañas en español; (2) mensajes de error legibles con vol = 0 y días < 0; (3) con días = 0 aparece el aviso y la curva "hoy" coincide con la de vencimiento (valor intrínseco menos comisiones); (4) añadir/quitar patas call/put/acción funciona; (5) la prima nueva coincide con BS y al editarla no se pisa al cambiar el spot; (6) el gráfico muestra las dos curvas, cero, spot y breakevens, con el salto de comisión visible; (7) "ilimitado" aparece en long call y call corto; (8) cada una de las 8 plantillas se abre en el constructor con gráfico y métricas; (9) Ajustes cambia el resultado y persiste al cambiar de pestaña (única prueba de la persistencia entre pestañas perezosas, no la cubre AppTest); (10) avisos visibles según Acción/ETF/Índice y "no es asesoría".
- **Pass criteria:** `.venv/bin/pytest -q` verde y la checklist manual aprobada por el usuario antes de marcar `✅ VERIFIED`.

## Verification Evidence

| Gate / Scenario | Strategy | Proves SPEC criterion |
|---|---|---|
| `.venv/bin/pytest tests/test_validation.py -q` (entradas inválidas, días = 0 aviso) + `tests/test_analyze.py` (hoy = intrínseco) + mensajes en UI | Hybrid | AC1 |
| `tests/test_pricing.py` (precio con q > 0 altera precios y griegas) | Fully-Automated | AC2 |
| `tests/test_legs_payoff.py` (modelo de pata, P&L al vencimiento) + `tests/test_app_smoke.py` + manual (añadir/quitar patas) | Hybrid | AC3 |
| `tests/test_pricing.py` (`default_premium` = `bs_price`) + `tests/test_legs_payoff.py` (prima editada usada) | Fully-Automated | AC4 |
| `tests/test_legs_payoff.py` (fórmula por tipo de pata, multiplicador) | Fully-Automated | AC5 |
| `tests/test_pricing.py` (Hull y S=K=100) | Fully-Automated | AC6 |
| `tests/test_pricing.py` (paridad put-call, q > 0) | Fully-Automated | AC7 |
| `tests/test_pricing.py` (griegas) + `tests/test_legs_payoff.py` (griegas de posición) | Fully-Automated | AC8 |
| `tests/test_legs_payoff.py` + `tests/test_analyze.py` (curva = suma de patas, rango cubre strikes) + lectura visual manual | Hybrid | AC9 |
| `tests/test_metrics.py` + `tests/test_catalog.py` (métricas por estrategia) | Fully-Automated | AC10 |
| `tests/test_metrics.py` (ilimitado) | Fully-Automated | AC11 |
| `tests/test_metrics.py` (breakevens múltiples / ninguno) | Fully-Automated | AC12 |
| `tests/test_commissions.py` (defecto, índice, sin cierre si sin valor, acción 0) | Fully-Automated | AC13 |
| `tests/test_commissions.py` + `tests/test_metrics.py` (comisiones mueven breakevens) + manual (editar en Ajustes; ítem 9 = única prueba de persistencia entre pestañas) + AppTest (los valores de comisión de `session_state` llegan al resultado; sin reclamar persistencia) | Hybrid | AC14 |
| `tests/test_catalog.py` (8 plantillas, campos presentes) | Fully-Automated | AC15 |
| `tests/test_catalog.py` (patas válidas, métricas de libro) + `tests/test_app_smoke.py` (abrir → Constructor) + manual | Hybrid | AC16 |
| `tests/test_validation.py` (lógica de avisos) + manual (presencia visual) | Hybrid | AC17 |
| `.venv/bin/pytest -q` completo + test de import sin Streamlit en subproceso nuevo (`tests/test_analyze.py`) | Fully-Automated | AC18 |
| Decisión 13 (días = 0 permitido, griegas "—") | Fully-Automated | AC1 (refinado) |
| Decisión 14 (cierre en curva "hoy") | Fully-Automated | AC13/AC14 (refinados) |

Los criterios Hybrid requieren además la revisión manual del usuario (AppTest no comprueba el aspecto visual). No hay tests asignados a Known-Gap para comportamiento desarrollado: la maquetación visual y la persistencia entre pestañas perezosas quedan cubiertas solo por la checklist manual del bloque 6 (ítems 6 y 9), no se declara PASS solo por AppTest.

Comandos de evidencia por bloque: `.venv/bin/pytest tests/test_pricing.py -q` (1), `.venv/bin/pytest tests/test_legs_payoff.py tests/test_commissions.py -q` (2), `.venv/bin/pytest tests/test_metrics.py -q` (3), `.venv/bin/pytest tests/test_validation.py tests/test_analyze.py -q` (4), `.venv/bin/pytest tests/test_catalog.py -q` (5), `.venv/bin/pytest tests/test_app_smoke.py -q` (6) y `.venv/bin/pytest -q` al final de cada bloque y como puerta final. Arranque manual: `.venv/bin/streamlit run app.py`.

## Matriz de trazabilidad AC1–AC18

| AC | Bloque | Test / evidencia | proven by | strategy |
|---|---|---|---|---|
| AC1 | 2, 4, 6 | `test_validation.py`, `test_analyze.py`, `test_legs_payoff.py` (días = 0), `test_app_smoke.py`, manual | validación-entradas-inválidas + hoy-igual-intrínseco-en-días-0 | Hybrid |
| AC2 | 1 | `test_pricing.py` | precio-con-dividendo | Fully-Automated |
| AC3 | 2, 6 | `test_legs_payoff.py`, `test_app_smoke.py`, manual | modelo-de-pata + resultado-por-pata | Hybrid |
| AC4 | 1, 2 | `test_pricing.py`, `test_legs_payoff.py` | prima-por-defecto-igual-a-BS + prima-editada-usada | Fully-Automated |
| AC5 | 2 | `test_legs_payoff.py` | payoff-por-tipo-de-pata | Fully-Automated |
| AC6 | 1 | `test_pricing.py` | precios-referencia-Hull | Fully-Automated |
| AC7 | 1 | `test_pricing.py` | paridad-put-call | Fully-Automated |
| AC8 | 1, 2 | `test_pricing.py`, `test_legs_payoff.py` | griegas-referencia + griegas-de-posición-signos | Fully-Automated |
| AC9 | 2, 4, 6 | `test_legs_payoff.py`, `test_analyze.py`, manual | curva-vencimiento-igual-suma-de-patas + rango-automático-cubre-strikes | Hybrid |
| AC10 | 3, 5 | `test_metrics.py`, `test_catalog.py` | métricas-por-estrategia-del-catálogo | Fully-Automated |
| AC11 | 3 | `test_metrics.py` | detección-de-ilimitado | Fully-Automated |
| AC12 | 3 | `test_metrics.py` | breakevens-múltiples + sin-breakeven | Fully-Automated |
| AC13 | 2 | `test_commissions.py` | comisiones-por-defecto + sin-cierre-si-expira-sin-valor + acción-sin-comisión | Fully-Automated |
| AC14 | 2, 3, 6 | `test_commissions.py`, `test_metrics.py`, `test_app_smoke.py` (comisiones de `session_state` llegan al resultado), manual (ítem 9: persistencia entre pestañas) | comisiones-mueven-breakeven + edición-en-Ajustes | Hybrid |
| AC15 | 5 | `test_catalog.py` | catálogo-completo-y-campos-presentes | Fully-Automated |
| AC16 | 5, 6 | `test_catalog.py`, `test_app_smoke.py`, manual | plantillas-generan-patas-válidas + navegación-del-botón | Hybrid |
| AC17 | 4, 6 | `test_validation.py`, manual | aviso-según-tipo-de-subyacente | Hybrid |
| AC18 | 1–6 | `.venv/bin/pytest -q` + test de import sin Streamlit en subproceso (`test_analyze.py`) | ejecución-pytest-completa | Fully-Automated |

## Risk Predictions

Debate previo (vc-predict, perfiles: corrección financiera, principiante de Python, UX Streamlit, mantenibilidad, QA) integrado en estos riesgos; los escenarios límite (vc-scenario) de los ítems de mayor riesgo están ya incorporados en los bloques 3, 4 y 6.

| # | Riesgo | Probabilidad / impacto | Mitigación |
|---|---|---|---|
| R1 | **Pestañas perezosas pierden estado** (widgets de pestañas no activas se descartan) | Media / Alto | Datos globales en la barra lateral; Ajustes y `legs` en entradas simples de `session_state` por callbacks (opcional `persist_state="session"` en widgets); AppTest NO puede reproducir la pérdida de estado (ejecuta todas las pestañas), así que la única prueba es el ítem 9 de la checklist manual; fallback radio/segmented control |
| R2 | **La comisión de cierre sorprende al usuario** (salto en el gráfico, beneficio máx. alcanzado "justo" en un strike) | Media / Medio | Nota corta visible en pantalla; salto dibujado (grid con strikes ± 1e-9); casos calculados a mano en `test_metrics.py`; explicación en el reporte |
| R3 | **σ y T casi cero** (inestabilidad numérica, división por cero) | Media / Alto | `MIN_VOL`; guardas en `bs_price` (T ≤ 0 intrínseco, σ ≤ 0 límite determinista); tests de no-NaN en todo el grid; greeks lanzan `ValueError` y la UI muestra "—" |
| R4 | **G1: recargo de índice 0,60 USD no verificado** con un broker real | Media / Bajo | Valor por defecto configurable en Ajustes; indicado en el SPEC y en el reporte final; el usuario lo contrasta con su broker |
| R5 | **Aproximación americana (G2)** hace números "hoy" de Acción/ETF inexactos | Alta / Medio | Aviso visible (AC17); fuera de alcance modelo binomial |
| R6 | Primas manuales incoherentes con BS (G4) | Media / Bajo | Se respeta la prima del usuario; "hoy" sigue usando BS con datos globales; indicador `premium_manual` + "↺ BS" |
| R7 | Redondeo de strikes de plantillas con spot muy bajo deja patas degeneradas (strikes iguales) | Baja / Medio | Test en `test_catalog.py` con spots bajos; ajuste mínimo de un paso entre strikes |
| R8 | AppTest no cubre lo visual: los criterios Hybrid podrían darse por buenos sin mirar | Media / Medio | Checklist manual explícita; `✅ VERIFIED` solo con confirmación del usuario |
| R9 | Detección errónea de breakevens en saltos de comisión o tramos planos | Media / Alto | Reglas de salto/`P(K)==0`/deduplicado con tolerancia; condor y bull spread calculados a mano |
| R10 | API de Streamlit 1.67 (`key`/`on_change` en tabs; `persist_state` solo en widgets, no en `st.tabs`) distinta a lo esperado | Media / Medio | `vc-docs-seeker` y comprobación de solo lectura al inicio del bloque 6; fallback documentado |

## Out of Scope

Heredado del SPEC: datos de mercado en vivo/yfinance, cadenas de opciones, volatilidad implícita, Monte Carlo y probabilidades, comparador de estrategias, guardar/cargar estrategias, asistente de sugerencias, backtesting, modelo binomial/valoración americana exacta, spreads calendar/diagonal, asesoría de inversión. Añadido por este plan: tema visual avanzado, internacionalización, despliegue en la nube, `MAX_VOL`, exportar a imagen/PDF.

## Dependencies

- Fijadas (decisión 11) en `requirements.txt`; ya instaladas en `.venv`.
- Orden de bloques: 2 necesita 1; 3 necesita 2; 4 necesita 3; 5 necesita 4 (usa `validate_legs`/`analyze` para sus tests); 6 necesita 1–5.
- Sin servicios externos, sin secretos, sin red.

## Test Infra Improvement Notes

(none identified yet) — candidatos a anotar durante EXECUTE/VALIDATE: fixture compartido `conftest.py` con un `Market` y `CommissionSettings` estándar; helper de comparación de curvas; documentar en `process/context/tests/all-tests.md` el uso de `streamlit.testing.v1.AppTest`.

## Context drift a corregir en UPDATE PROCESS

- `process/context/all-context.md` afirma que las dependencias no están fijadas y que no hay tests de UI: tras el bloque 1 las versiones quedan fijadas en `requirements.txt` y tras el bloque 6 existe un smoke test con `AppTest` (G3 resuelto por AppTest; lo visual sigue siendo manual).
- `process/context/tests/all-tests.md` dice "no automated UI tests in the MVP": actualizar con el smoke test `tests/test_app_smoke.py` y la checklist manual.
- Registrar en contexto la arquitectura del motor, las decisiones 13–14 y el salto de comisión al vencimiento.

## Resume and Execution Handoff

1. **Selected plan file path:** `process/general-plans/completed/mvp-laboratorio_20-11-26/mvp-laboratorio_PLAN_20-11-26.md` (archivado)
2. **Last completed phase or step:** TODOS los bloques ✅ VERIFIED; plan archivado en `process/general-plans/completed/` (ver Current Execution State).
3. **Validate-contract status:** PASS (ver `## Validate Contract`).
4. **Supporting context files loaded:** el SPEC bloqueado, `DISENO.md`, `process/context/all-context.md`, `process/context/tests/all-tests.md`, `process/development-protocols/plan-lifecycle.md`, `process/development-protocols/implementation-standards.md`, `.claude/skills/vc-generate-plan/references/example-complex-prd.md`.
5. **Next step for a fresh agent:** nada pendiente en este plan; ver `## Next Step`.

Envelope de contexto: feature: none → phase: PLAN → session-goal: plan del MVP en 6 bloques → branch: main → worktree: raíz del repo → context-group: all-context + all-tests → blast-radius-packages: `opciones/`, `tests/`, `app.py`, `requirements.txt` → active-plan: este archivo → test-runner: pytest → validate-contract: pending.

## Validate Contract

Status: PASS
Date: 20-11-26
date: 2026-11-20
generated-by: outer-pvl
supersedes: 2026-11-20 (outer-pvl) - re-run from V1 after PVL supplement cycle 1 (C1-C3 applied); results.tsv records 1 fix cycle

Parallel strategy: sequential
Rationale: 1/7 signals (S7: 5+ files in blast radius). Greenfield, one pure engine plus one Streamlit app; blocks depend on each other (2 needs 1, 3 needs 2, ...), so no parallel EXECUTE. VALIDATE fan-out done inline (proportionate to project size; no subagents spawned).

Re-validation evidence (this pass):
- Structural validator `validate-plan-artifact.mjs`: 0 failures, 0 warnings.
- Reference numbers (Hull, S=K=100 Greeks, bull spread -201.30 / 798.05 / 797.40 / 102.0195, condor 197.40 / -303.90 / 93.0325 / 106.9675 and 200 / -300 / 93 / 107, short call 199.35 / 101.987) were independently recomputed in the first pass (all MATCH); the supplement did not change any of them.
- Verified facts (Streamlit 1.67): `st.tabs(key=, on_change="rerun")` + callback switches tabs; `persist_state` is not an `st.tabs` parameter; AppTest executes every tab body; `streamlit.testing.v1` imports.
- C1 resolved: `default_premium` is created in `opciones/pricing.py` in block 1, tested in `tests/test_pricing.py`, re-exported from `__init__.py` in block 1 and kept in the block 4 API; block 2 and block 5 consume it after it exists (ordering holds).
- C2 resolved: no-Streamlit check runs in a fresh interpreter (`subprocess.run([sys.executable, "-c", ...], check=True)`) inside `tests/test_analyze.py`; independent of pytest's `sys.modules`.
- C3 resolved: commission settings and `legs` live in plain `st.session_state` updated by callbacks; AppTest is relabelled (does not claim tab persistence); manual checklist item 9 is the only proof of cross-tab persistence.
- No regressions found in the supplemented sections (blocks 1, 2, 4, 6, Verification Evidence, traceability matrix, risks R1/R10 all consistent).

Test gates (all run from repo root with `.venv/bin/pytest`; each block also ends with `.venv/bin/pytest -q`):

| criterion id | behavior | strategy | proving test | gap-resolution |
|---|---|---|---|---|
| AC2, AC4 (default_premium = BS), AC6, AC7 | BS price with q, Hull and S=K=100 references, put-call parity, default_premium = bs_price | Fully-Automated | `.venv/bin/pytest tests/test_pricing.py -q` | B |
| AC8 | Greeks reference values and position greeks signs | Fully-Automated | `.venv/bin/pytest tests/test_pricing.py tests/test_legs_payoff.py -q` | B |
| AC4, AC5 | edited premium used, per-leg payoff formula, multiplier | Fully-Automated | `.venv/bin/pytest tests/test_legs_payoff.py -q` | B |
| AC13, decision 14 | commission defaults, index surcharge, close only if ITM strict at expiry, close always on "hoy" curve | Fully-Automated | `.venv/bin/pytest tests/test_commissions.py -q` | B |
| AC10, AC11, AC12, AC14 | exact max/min, unlimited, breakevens, hand-computed commission cases | Fully-Automated | `.venv/bin/pytest tests/test_metrics.py -q` | B |
| AC1, AC9, AC17, decision 13, AC18 (import) | validation messages, days=0 warning, analyze() intrinsic "hoy", no-NaN grid, curve = sum of legs, import without Streamlit in fresh subprocess | Hybrid | `.venv/bin/pytest tests/test_validation.py tests/test_analyze.py -q` + manual checklist items 2, 3, 10 | B |
| AC15, AC16 (engine), AC10 | 8 templates, valid legs for 6 spots, rounding, book metrics | Fully-Automated | `.venv/bin/pytest tests/test_catalog.py -q` | B |
| AC3, AC9, AC14, AC16, AC17 (UI) | app loads, open template -> Constructor, commission values from session_state reach the result, days=0 warns, vol=0 errors | Hybrid | `.venv/bin/pytest tests/test_app_smoke.py -q` + user manual checklist (block 6, items 1-10, owned by the user; item 9 = only proof of cross-tab persistence) | B |
| AC18 | whole suite green | Fully-Automated | `.venv/bin/pytest -q` | A |

Failing stubs (Fully-Automated rows; EXECUTE writes them first, TDD): in each test file above add
`def test_<scenario>(): pytest.fail("NOT IMPLEMENTED - TDD stub: <scenario>")`
for every scenario listed in the block checklist, then replace with real assertions.

Legacy line form:
- pricing: [Fully-automated: `.venv/bin/pytest tests/test_pricing.py -q`]
- payoff/commissions: [Fully-automated: `.venv/bin/pytest tests/test_legs_payoff.py tests/test_commissions.py -q`]
- metrics: [Fully-automated: `.venv/bin/pytest tests/test_metrics.py -q`]
- validation/analyze: [hybrid: `.venv/bin/pytest tests/test_validation.py tests/test_analyze.py -q` + manual visual]
- catalog: [Fully-automated: `.venv/bin/pytest tests/test_catalog.py -q`]
- app: [hybrid: `.venv/bin/pytest tests/test_app_smoke.py -q` + manual checklist by user]
- final: [Fully-automated: `.venv/bin/pytest -q`]

Dimension findings:
- Infra fit: PASS - venv has all pinned versions; AppTest importable; `tests/__init__.py` and `opciones/__init__.py` present; `requirements.txt` pinned by block 1; structural validator 0 failures / 0 warnings; every gate command is runnable from repo root.
- Test coverage: PASS - C1, C2, C3 resolved (see evidence above); AC1-AC18 and decisions 1-14 all map to a gate; Hybrid rows carry an explicit manual checklist, so no developed behavior rests on Known-Gap alone (vacuous-green ban satisfied).
- Breaking changes: PASS - greenfield; only `requirements.txt` modified; rollback = delete block files.
- Security surface: PASS - local app, no network, secrets or persistence; no file I/O in the engine; `subprocess.run` in a test runs only `sys.executable -c` with a constant string.
- Section 1 (models + pricing + default_premium): PASS - formulas reproduce all references; guards consistent with decision 13; default_premium has an owner and a test.
- Section 2 (payoff + commissions): PASS - depends only on block 1; `pnl_today` charges close fee only when `include_close`.
- Section 3 (metrics): PASS - hand-computed commission cases reproduced. Highest-risk edit: supremum at a single point (S=110 gives 798.05 vs plateau 797.40); test the exact point and the right limit separately.
- Section 4 (validation + analyze): PASS - import check now isolated in a subprocess.
- Section 5 (catalog): PASS - ordering holds (default_premium block 1, analyze block 4).
- Section 6 (app.py): PASS - state design avoids lazy-tab loss; AppTest claims are honest; fallback documented. Blocks are beginner-sized, though block 3 (metrics) and block 6 (UI) are the largest; execute them in small steps with stubs first.

Open gaps (named residuals, user-owned, not counted as CONCERN):
- G1 (index surcharge 0.60 unverified vs broker), G2 (American approximation), G4, G5 as in SPEC: known-gap: documented.
- Visual layout and cross-tab persistence (AC3/AC9/AC14/AC16/AC17 UI aspects): covered only by the user's manual checklist (Hybrid), never by AppTest alone; `VERIFIED` requires user confirmation (gap-resolution D).

What this coverage does NOT prove:
- pytest on pricing/payoff/metrics does not prove the chart renders, tab navigation in a real browser, or lazy-tab behaviour (AppTest executes all tab bodies; only checklist item 9 proves persistence).
- BS results do not prove accuracy for American Acción/ETF options (approximation, ~7 % on puts) nor discrete dividends or early exercise.
- Index surcharge 0.60 USD is a configurable default, not broker-verified.
- Commission jump at strikes is proven numerically, not that it reads clearly on screen.
- Metrics prove exact values for the listed strategies and edge cases (one strike, same-strike legs, flat P&L, stock-only), not arbitrary user-built combinations.
- The subprocess import test proves `import opciones` does not load Streamlit, not that `app.py` is correct.

Execute-agent instructions:
1. Blocks strictly in order 1 to 6; run the block gate then `.venv/bin/pytest -q`; never start a block with the previous one red. Mark blocks `CODE DONE`, never `VERIFIED` without user confirmation.
2. Write failing stubs first (TDD), then implement; keep code simple (dataclasses, plain functions), identifiers in English, comments in Spanish.
3. Block 1: `default_premium` goes in `opciones/pricing.py` and is re-exported from `__init__.py` in this block.
4. Block 3: reconfirm the three commission hand cases (bull 798.05 / 797.40 / -201.30 / 102.0195; condor 197.40 / -303.90 / 93.0325 / 106.9675; short call 199.35 / 101.987) with `pytest.approx(abs=1e-3)` for breakevens, `abs=1e-6` for P&L.
5. Block 4: run the no-Streamlit import check via `subprocess.run([sys.executable, "-c", ...], check=True)`; pass `cwd` as the repo root so `import opciones` resolves regardless of where pytest is launched.
6. Block 6: before writing, read-only check with `.venv/bin/python -c` that `st.tabs(key=, on_change="rerun")` and widget `persist_state` behave as documented; keep sidebar widgets always rendered; keep commission settings and `legs` in plain `session_state` entries; fallback segmented control if tabs misbehave. Do not write AppTest assertions that claim tab persistence.
7. EVL: a spawned vc-tester re-runs every gate command above. Housekeeping for UPDATE PROCESS: the plan's Resume handoff item 3 and the final "Next Step" section are stale (still say contract pending / enter VALIDATE).

Plan updates applied: none by the validate agent (role writes only the contract); none required.

Gate: PASS
Accepted by: n/a - Gate is PASS (no FAILs, no unresolved CONCERNs). Prior CONCERNs C1 (default_premium placement), C2 (import-test isolation), C3 (AppTest vs lazy-tab persistence) were fixed in the plan by PVL supplement cycle 1 and re-verified here.

## Autonomous Goal Block

SESSION GOAL: MVP v1 Laboratorio de Opciones (engine `opciones/` + `app.py`)
Charter + umbrella plan: N/A - single plan
Autonomy: standing consent only after the user says ENTER EXECUTE MODE; subagent delegation stays mandatory.
Hard stop conditions / safety constraints:
- Do not start a block with the previous block's pytest red.
- Never mark a block VERIFIED without the user's confirmation; Hybrid criteria need the user's manual checklist.
- Do not add dependencies beyond the pinned five; no network, secrets, or file I/O in the engine.
Next phase: EXECUTE: process/general-plans/completed/mvp-laboratorio_20-11-26/mvp-laboratorio_PLAN_20-11-26.md
Validate contract: inline in plan
Execute start: `.venv/bin/pytest tests/test_pricing.py -q` then `.venv/bin/pytest -q` | e2e: none | probe: `.venv/bin/streamlit run app.py` (manual) | high-risk pack: no

## Current Execution State

**COMPLETE (20-11-26).** Los 6 bloques están implementados, cada uno confirmado por una ejecución EVL independiente de vc-tester y aprobado por el usuario; checklist manual de 10 ítems completada por el usuario ("Todo bien"). AC1–AC18 cumplidos. Suite final: 479/479, smoke AppTest 6/6.

| Bloque | Commit | Tests acumulados |
|---|---|---|
| 1 | 5918b13 | 23 |
| 2 | ac75c6d | 60 |
| 3 | ee8e46e | 91 |
| 4 | ce52faf | 166 |
| 5 | c7ac737 | 473 |
| 6 | 2c18510 | 479 |

SPEC/plan: c08f263.

## Lessons Learned and Deviations (UPDATE PROCESS)

- **Corrección numérica del plan:** el bull call spread calculado a mano (100 @ 3 / 110 @ 1, comisiones por defecto) tiene pérdida máx. −201,95, no −201,30: justo por encima de S = 100 el call largo es ITM estricto y paga la comisión de cierre (0,65); −201,30 es solo P(100). Texto del bloque 3 corregido.
- **Decisión 6 se mantiene** (el usuario la confirmó durante EXECUTE). Refinamiento posible movido al backlog: `process/general-plans/backlog/close-fee-rational-close_20-11-26.md`.
- **Elecciones no especificadas en el plan, aceptadas por el usuario:** rejilla de precios spot ±30 % ampliada 10 % más allá de los strikes extremos, 401 puntos; griegas `None` con vol <= 0; paso de strike 10 por encima de 1000; separación de strikes en colisión dentro del catálogo; prima 0 permitida, strike > 0; tipo y q negativos permitidos; `commission_total` = apertura + cierre (include_close); la app arranca con un call largo ATM; botón de reinicio de spot "↺ spot"; `persist_state` no se usó.
- **EVL ciclo 1 del bloque 6:** `st.metric` truncaba los breakevens (AC12); se movieron a una línea markdown propia y se añadió un test de regresión AppTest. Lección: la revisión visual en navegador detecta defectos que AppTest no ve.
- **Pendiente solo manual:** la persistencia entre pestañas perezosas no tiene test automático (ítem 9 de la checklist manual, pasado por el usuario).

## Next Step

MVP cerrado. Siguiente: roadmap v2 según `DISENO.md` (datos de mercado con yfinance, etc.) en un plan nuevo; opcionalmente el ítem de backlog de comisión de cierre racional.
