---
name: etapa-c2-historico-backtest PLAN
description: "Plan COMPLEX de la Etapa C2 (histórico diario del subyacente + pestaña Backtest de calibración de la PoP y diagnóstico de colas) de Laboratorio de Opciones, en 10 bloques secuenciales cada uno cerrado con pytest verde."
date: 21-11-26
status: planned
complexity: complex
spec: process/general-plans/active/etapa-c2-historico-backtest_21-11-26/etapa-c2-historico-backtest_SPEC_21-11-26.md
---

# Plan: Etapa C2 — Histórico del subyacente y calibración de la PoP (pestaña Backtest)

**Date**: 21-11-26
**Complexity**: COMPLEX (un solo plan, un solo flujo de ejecución, 10 bloques con dependencias; no es phase program)
**Status**: ⏳ PLANNED (PLAN escrito 21-11-26; ningún bloque ejecutado)
**SPEC bloqueado**: `process/general-plans/active/etapa-c2-historico-backtest_21-11-26/etapa-c2-historico-backtest_SPEC_21-11-26.md` (AC-C2-1..AC-C2-17, decisiones C2-1..C2-8, valores propuestos 1–12 aprobados por el usuario, huecos C2-G1..C2-G9)
**Entorno**: Python 3.12.3, `.venv` (numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0, yfinance 1.8.0, pandas 3.1.1); línea base: `.venv/bin/pytest -q` → **2742 passed, 3 skipped** (HEAD 14858a2, rama main)

**TL;DR:** dos módulos puros nuevos en el motor (`opciones/calibration.py` y `opciones/backtest.py`, sin pandas ni E/S; los módulos existentes de `opciones/` no cambian) recorren fechas pasadas t, calculan con datos ≤ t la PoP exacta (Black-Scholes) de una plantilla y miran si ganó en t+H; de ahí salen el gráfico de fiabilidad, Brier, N y N efectivo y el diagnóstico de colas. El histórico llega por una interfaz **separada** (`HistoryProvider`) con caché propia `.cache_datos/history/`, un servicio de limpieza/carga y un método nuevo en `YahooProvider`/`FakeProvider`. La interfaz es una 4.ª pestaña "Backtest" (`ui_backtest.py`) donde nada pesado corre sin pulsar "Cargar histórico" / "Calcular". La suite sigue sin red; cada bloque cierra con `.venv/bin/pytest -q` completo en verde.

**Clasificación de complejidad (mi decisión):** COMPLEX estándar: 4 módulos de `datos/` nuevos o ampliados, 2 módulos de motor nuevos, una pestaña de UI y ~150 tests nuevos; pero los bloques comparten tipos y `app.py` y se ejecutan en un solo flujo, así que un solo archivo basta (misma decisión que C1).

## Overview

La app calcula una PoP con un modelo lognormal de volatilidad constante, pero nadie ha comprobado si "acierta". La Etapa C2 añade años de precios diarios del subyacente (Yahoo, gratis, detrás de una interfaz intercambiable, con caché local) y la pestaña **Backtest**: el usuario elige plantilla, horizonte H, ventana de volatilidad W, paso y años; la app recorre fechas pasadas y compara "PoP que habría dicho la app ese día" con "¿ganó de verdad?". Resultado: **calibración de probabilidades, no rentabilidad real** (no hay precios históricos de opciones). Incluye diagnóstico de colas. El motor, el constructor, C1 y los modelos funcionan igual.

Contexto leído para este plan: `process/context/all-context.md`, `process/context/tests/all-tests.md`, el SPEC, el plan de C1 (plantilla estructural), `opciones/simulation.py`, `catalog.py`, `payoff.py`, `models.py`, `metrics.py`, `validation.py`, `__init__.py`; `datos/` (`__init__`, `provider`, `types`, `errors`, `tickers`, `cache`, `service`, `fake`, `yahoo`, `filters`), `app.py`, `tests/conftest.py`, `tests/test_app_smoke.py` (helper `data_app`), `tests/test_datos_isolation.py`, `tests/test_datos_live.py`.

## Quick Links

- [Decisiones](#decisiones-del-plan-pd-1pd-14) · [Desviaciones para el usuario](#desviaciones-menores-y-puntos-a-confirmar-por-el-usuario) · [Arquitectura](#arquitectura) · [Phase Completion Rules](#phase-completion-rules)
- [Acceptance Criteria](#acceptance-criteria) · [Touchpoints](#touchpoints) · [Public Contracts](#public-contracts) · [Blast Radius](#blast-radius)
- [Implementation Checklist (bloques 1–10 + cierre)](#implementation-checklist) · [Verification Evidence](#verification-evidence) · [Matriz de trazabilidad](#matriz-de-trazabilidad-ac-c2-1ac-c2-17)
- [Checklist manual](#checklist-manual-para-el-usuario) · [Risk Predictions](#risk-predictions) · [Out of Scope](#out-of-scope) · [Test Infra Improvement Notes](#test-infra-improvement-notes) · [Resume and Execution Handoff](#resume-and-execution-handoff) · [Validate Contract](#validate-contract)

## Status strip

| Bloque | Contenido | Depende de | Tests nuevos (aprox.) | Estado |
|---|---|---|---|---|
| 1 | `opciones/calibration.py` (Wilson, Brier, deciles, N efectivo, colas) | — | ~25 | ⏳ PLANNED |
| 2 | `opciones/backtest.py` ayudantes (vol realizada, μ, q, r, vencimiento) | — | ~22 | ⏳ PLANNED |
| 3 | `opciones/backtest.py` bucle `run_backtest` + oráculos + sin mirar el futuro + tiempo | 1, 2 | ~20 | ⏳ PLANNED |
| 4 | `PriceHistory`, `HistoryProvider`, `FakeProvider.get_history`, mapa de símbolos | — | ~16 | ⏳ PLANNED |
| 5 | `datos/history_cache.py` (+ `covers`, `start_for_years`) | 4 | ~20 | ⏳ PLANNED |
| 6 | `datos/history_service.py` (limpieza, carga por años+1, ^IRX, ^GSPC/^SPX) | 4, 5 | ~18 | ⏳ PLANNED |
| 7 | `YahooProvider.get_history` (cliente simulado) + prueba en vivo opcional | 4 | ~12 | ⏳ PLANNED |
| 8 | Aislamiento: importaciones y `requirements.txt` | 1–7 | ~4 | ⏳ PLANNED |
| 9 | UI esqueleto: pestaña, controles, caption de años, "Cargar histórico", entrada manual, limpieza al cambiar ticker | todos | ~12 | ⏳ PLANNED |
| 10 | UI resultados: "Calcular" (con comprobación de cobertura), gráficos, tabla, avisos, caché de sesión | 9 | ~14 | ⏳ PLANNED |
| Cierre | Suite completa sin red, `unshare -rn`, diff del motor, checklist manual | todos | — | ⏳ PLANNED |

Orden de ejecución recomendado: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, cierre (los bloques 1–3 y 4–7 son dos cadenas independientes; se serializan para no mezclar fallos). Cada bloque es testable y se commitea por separado directamente en `main`.

## Decisiones del plan (PD-1..PD-14)

Las decisiones C2-1..C2-8 y los valores propuestos 1–12 del SPEC siguen vigentes sin reescribirse. INNOVATE (21-11-26) las concreta así (el usuario aceptó las 14 decisiones del SPEC; lo siguiente es el diseño bloqueado):

| # | Decisión |
|---|---|
| PD-1 | **Módulos del motor nuevos, puros y sin pandas ni E/S:** `opciones/calibration.py` (~150 líneas) y `opciones/backtest.py` (~250 líneas). Usan numpy y `scipy.stats` (ver desviación iii). Los módulos existentes de `opciones/` **no cambian** (`exact_pop` se importa de `opciones.simulation`; no se añade línea de exportación en `__init__.py`). |
| PD-2 | **Entradas del motor:** lista de fechas ISO + arrays numpy; convierte con `np.array(dates, dtype="datetime64[D]")`. Sin pandas. La tasa r llega ya en fracción. |
| PD-3 | **Bucle simple en Python** por fecha: `build_legs`, `validate_market` (se salta y se cuenta si falla), `exact_pop`, `pnl_expiry`, con `Market(..., pricing_model="black_scholes")` forzado. "Ganó" = `pnl_expiry(...)[0] > ZERO_TOL` con el cierre **sin ajustar** en el vencimiento. Medido en INNOVATE: 2,8 ms por fecha (494 fechas ≈ 1,4 s; 2468 ≈ 6,9 s; la línea μ cuesta ≈ 2×). Sin vectorizar y sin callback de progreso: `st.spinner` + caption "≈ N fechas, ~X s" (N×3 ms). |
| PD-4 | **Volatilidad realizada:** `std(ddof=1)` de los log-rendimientos de `adj_close` de las W sesiones que terminan en t, × √252; exige `i ≥ W`. |
| PD-5 | **μ histórico:** `trailing_mu = mean(log-rendimientos de 252 sesiones) × 252 + vol²/2` (porque `SimulationSettings.mu` es el crecimiento esperado del precio, no el de log). Sin recortar al rango de `validate_simulation` (`exact_pop` no valida). |
| PD-6 | **q histórico:** suma de dividendos en (t−365 d, t] / `close[t]` con `cumsum` + `searchsorted`; 0 para el índice (con nota). |
| PD-7 | **r histórico:** último valor de ^IRX con fecha ≤ t (`searchsorted(side="right") − 1`); si t es anterior al primer dato de ^IRX, la fecha se salta y se cuenta (`no_rate`). |
| PD-8 | **Vencimiento:** `searchsorted(epoch_days, t+H, side="right") − 1`; si el último dato es anterior a t+H la fecha de cola se salta (`no_expiry`). |
| PD-9 | **Calibración:** deciles fijos `[0,0.1) … [0.9,1.0]` (PoP = 1,0 va al último), **siempre 10 filas**; vacío → "—"; n < 10 → "pocos casos" y excluido de la desviación máxima; sin fusionar. `effective_n = min(N, años_analizados·365/H)` con `años_analizados = (t_último − t_primero)/365,25`. |
| PD-10 | **Colas:** `z = (ln(S_{t+H}/S_t) − (r − q − σ²/2)·T)/(σ√T)` con T = H/365; curtosis en exceso y asimetría con `scipy.stats`, desviación típica de z, excedencias |z| > 2 y z < −2 frente a 4,55 % / 2,28 %, cuantiles 1/5/50/95/99 frente a la normal. Además Brier climatológico `mean((tasa − gana)²)` y habilidad `1 − B/B_clim`. |
| PD-11 | **Proveedor de histórico separado:** `@runtime_checkable Protocol HistoryProvider.get_history(symbol, start, end) -> PriceHistory` en `datos/provider.py`; `MarketDataProvider` no se toca. `PriceHistory` (frozen) en `datos/types.py`. `YahooProvider` y `FakeProvider` implementan ambos; la app comprueba `isinstance(p, HistoryProvider)`. `start` inclusivo, `end` exclusivo (como Yahoo), ambos `datetime.date`. |
| PD-12 | **Yahoo:** `Ticker.history(start, end, interval="1d", auto_adjust=False, actions=True)`; vacío → `EmptyDataError`; conversión sin importar pandas a nivel de módulo (se recorre `frame.index` y `frame[col].tolist()`). Símbolos: SPX prueba `^GSPC` y, solo si da `EmptyDataError`, `^SPX`; acciones/ETF su propio ticker; `^IRX` para la tasa. ^IRX llega en porcentaje y se convierte en `datos` con `rate_from_percent`. Fallo de ^IRX **no es fatal**: aviso + r constante de la barra lateral. |
| PD-13 | **FakeProvider de histórico generado en código** (sin fixtures): GBM con `random.Random(seed)` + `math`, semilla = suma de `ord` de los caracteres del ticker (nunca `hash()`), días hábiles generados hacia atrás desde el reloj inyectado (sin festivos), parámetros `sigma`, `mu`, `seed`, dividendos trimestrales opcionales; ^IRX devuelve una serie en porcentaje (constante o con un escalón); ticker desconocido → `EmptyDataError`; admite `fail_with`. Nunca caduca con el tiempo real. |
| PD-14 | **Caché y descarga:** `datos/history_cache.py` (nuevo; importa `_file_label`, `_atomic_write_json`, `market_today`, `DEFAULT_CACHE_DIR` de `datos.cache` sin modificarlo): `.cache_datos/history/<ETIQUETA>.json` (tasa en `history/IRX.json`), `schema_version` 1, `ticker`, `fetched_at` (con zona), `requested_start` (ISO, opcional al leer), `dates`, `close`, `adj_close`, `dividends`; lectura defensiva (None si falta/corrupta/otra versión), escritura atómica. Fresca si `fetched_at` es el mismo día de mercado que hoy **o** el último dato ≥ última sesión cerrada (día hábil anterior a `market_today`); si no, se vuelve a descargar completo. **Cambio 21-11-26 (decisión del usuario; sustituye la antigua "descarga fija de 16 años"):** "Cargar histórico" descarga **solo los años elegidos (`bt_years`, 1–15) + 1 año natural de calentamiento** (`years + 1` años naturales ≈ 249–252 sesiones (1 año de calendario) de calentamiento; con `bt_window` acotado a 10–250 el análisis empieza a 0–3 sesiones de lo pedido, desfase que absorbe la tolerancia de IP-3), en una solicitud por símbolo: `start = today − (years + 1) años naturales` (se usa **siempre aritmética de años naturales**: `today.replace(year=today.year − (years + 1))`, con 29-feb → 28-feb; nunca `× 365 días`), `end = today + 1 día` (exclusivo). **Reutilización de caché:** se reutiliza (sin red) solo si es fresca (regla `is_fresh` anterior) **y cubre el tramo pedido** (`covers`, ver IP-10: primer dato ≤ `start` + 7 días de tolerancia, o `requested_start` guardado ≤ `start`); si no, descarga completa del tramo pedido. Pedir menos años que los cacheados reutiliza la caché; pedir más obliga a descargar de nuevo (caption en la UI, bloque 9). El control "años" también recorta las fechas analizadas (IP-3). ^IRX se pide con el mismo tramo. |

### Interpretaciones propias de este plan (cierran huecos que INNOVATE dejó abiertos)

| # | Interpretación | Por qué |
|---|---|---|
| IP-1 | `wilson_interval(k, n, z=1.96, deff=1.0)`: el parámetro `deff` es un **multiplicador de la muestra** (`deff = N_ef/N ≤ 1`): se calcula Wilson con `n' = n·deff` y `k' = k·deff` (misma proporción, menos información). `deff = 1.0` es Wilson ingenuo; `n = 0` → `None`. | Evita la ambigüedad "design effect ≥ 1 divide / ≤ 1 multiplica". |
| IP-2 | **Calentamiento:** la primera fecha analizable exige `i ≥ max(W, 252)` **siempre** (haya o no línea μ), para que la línea neutral y la de μ usen las mismas fechas. | Compara manzanas con manzanas. |
| IP-3 | **Recorte por años:** el muestreo arranca en la primera sesión con fecha ≥ `última_fecha − años·365,25 días`; el aviso AC-C2-4 salta si `años_disponibles = (última_fecha − fecha[max(W,252)])/365,25 < años − 0,25` (la tolerancia de 0,25 años evita falsos avisos por el año de calentamiento y los festivos). Se informa el valor real redondeado a 1 decimal. | Regla única, testable. |
| IP-4 | **days del Market = H** (días naturales pedidos) aunque el último día de negociación ≤ t+H pueda ser 1–3 días anterior (fin de semana); el mismo T = H/365 se usa en z. Es un sesgo pequeño y documentado (R10). | Replica lo que la app diría con "H días". |
| IP-5 | **Comisiones:** `include_fees` → `CommissionSettings` de Ajustes; si no, `CommissionSettings(per_contract=0.0, index_surcharge=0.0, include_close=False)`. El mercado también pasa por `validate_legs`; los fallos de ambas validaciones cuentan como `invalid_market`. | Una sola categoría de omisión. |
| IP-6 | **Estado de widgets de la pestaña** con el patrón de Ajustes (anti pestañas perezosas): entradas simples `bt_template`, `bt_horizon`, `bt_window`, `bt_step`, `bt_years`, `bt_fees`, `bt_use_mu`; los widgets usan clave `bt_*_input`, `value=` desde la entrada simple y un callback `copy_bt_param(field)` que la actualiza. Los botones son `bt_load` y `bt_run`. | Las pestañas son perezosas; un widget no dibujado pierde su valor. |
| IP-7 | **Clic de botones:** dentro del cuerpo de la pestaña con `if st.button(...)` + `st.spinner` y escritura solo de claves **no ligadas a widgets** (`bt_history`, `bt_result`, `bt_notices`); no hay estado de widget cambiado fuera de callbacks. | `st.spinner` no se ve dentro de un callback. |
| IP-8 | **Cache ^IRX** guarda lo que devuelve el proveedor (porcentaje); la conversión `/100` ocurre al cargar en `history_service`. | Un solo lugar de conversión. |
| IP-9 | Tamaños de las pruebas de oráculo: se elige el paso para que N ≥ 1000 con serie de 40 años y se **mide y anota** el tiempo; si un oráculo pasa de 5 s se reduce el paso. | Mantener la suite ágil. |
| IP-10 | **Cobertura de caché (regla del usuario 21-11-26):** `covers(first_date, requested_start, start, tolerance_days=7) -> bool` en `datos/history_cache.py`: verdadero si `first_date ≤ start + 7 días` **o** si `requested_start` (el `start` con el que se descargó, guardado en el JSON como campo `requested_start`, ISO; ausente en cachés viejas → se ignora) `≤ start`. El segundo criterio es un refinamiento mío de la regla del usuario: sin él, un ticker cuya fuente tiene menos historia que la pedida (AC-C2-4) se volvería a descargar en cada pulsación y el aviso de "no cubre" saltaría siempre. La tolerancia de 7 días cubre inicios que caen en fin de semana/festivo. | Mantiene la regla "cubre el tramo pedido" sin bucles de descarga con fuentes cortas. |
| IP-11 | **Comprobación al calcular:** `HistoryLoad` lleva `requested_start: date | None` (el de la descarga, o el guardado en la caché usada; `None` si la caché vieja no tenía el campo). "Calcular" lo pasa **sin cambios** a `covers`, que ignora `None` (cae al criterio del primer dato). "Calcular" calcula `need_start = today − (bt_years + 1) años naturales` (reloj inyectado) y si `not covers(first_date, requested_start, need_start)` muestra `st.warning` con `MSG_BT_NOT_COVERED` ("El histórico cargado no cubre N años: pulsa «Cargar histórico»", N = `bt_years`) y **no calcula** (no se escribe `bt_result`). La clave de `bt_result` ya incluye `years`. Si tras una descarga fallida se usó la caché vieja (sin red), el mismo chequeo avisa si no cubre. | Opción más simple pedida por el usuario: detectar en Calcular, sin recarga automática. |

## Desviaciones menores y puntos a confirmar por el usuario

Para mostrar al usuario en la **aprobación del plan** (la (i) fue **rechazada** por el usuario el 21-11-26 y sustituida; las demás ya las aceptó el orquestador o las descubre este PLAN):

1. **(i) ~~Descarga fija de 16 años~~ — RECHAZADA por el usuario (21-11-26) → sustituida por:** "Cargar histórico" descarga solo los años elegidos + 1 año de calentamiento (`years + 1` años naturales; PD-14), con reutilización de la caché solo si está fresca **y** cubre el tramo pedido (primer dato ≤ inicio pedido + 7 días; IP-10). Menos años que los cacheados → reutiliza; más años → nueva descarga (la UI lo avisa con un caption: "cambiar a más años obliga a volver a descargar"). El control "años" ya importa al cargar: si se sube después de cargar, "Calcular" avisa «pulsa "Cargar histórico"» y no calcula (IP-11). Refinamiento propio a confirmar: la caché guarda `requested_start` para no redescargar en cada pulsación cuando la fuente tiene menos historia que la pedida (IP-10). Texto del SPEC afectado: AC-C2-3 y fila 7 de valores propuestos (se amplían, ver abajo).
2. **(ii) Barras de error de Wilson con `deff = N_efectivo / N`** (efecto de diseño por el solapamiento de ventanas); la tabla muestra n y n_ef por tramo.
3. **(iii) `scipy.stats` permitido en los módulos nuevos del motor** ("solo numpy" del SPEC se lee como "sin pandas ni E/S"); `requirements.txt` no cambia (scipy ya está).
4. **(iv) Un test existente cambia una aserción:** `tests/test_app_smoke.py` línea 65 comprueba que las pestañas son exactamente `["Catálogo", "Constructor", "Ajustes"]`; AC-C2-13 exige la 4.ª pestaña, así que esa lista pasa a incluir "Backtest". Es la **única** modificación de un test existente (ningún número esperado cambia).
5. **(v) Prueba en vivo de histórico:** se añade una segunda función opt-in en `tests/test_datos_live.py`; el conteo de omitidos pasa de 3 a **4** (2 de B1 + 2 en vivo). La línea base "3 skipped" del SPEC se actualiza a 4 al cierre.

## Chosen Approach y por qué este camino

**Elegido:** lógica de backtest y calibración en dos módulos puros del motor (probables con series sintéticas de respuesta conocida), acceso a datos en `datos/` detrás de un `Protocol` separado y una pestaña de UI delgada en un archivo propio (`ui_backtest.py`) que `app.py` solo invoca. Cada capa se prueba sola: motor con oráculos, `datos/` con proveedor falso y cliente simulado, UI con AppTest.

**Alternativas descartadas:**
- *Añadir `get_history` a `MarketDataProvider`*: toca el contrato de C1 y obligaría a cambiar todos sus implementadores/tests; se prefiere un Protocol aparte.
- *Meter el backtest dentro de `app.py`*: ya tiene 1359 líneas; `ui_backtest.py` evita un archivo gigante y un ciclo de importación (app.py ejecuta `main()` al importarse).
- *Vectorizar el bucle*: 2,8 ms por fecha ya cumple AC-C2-15 y reutiliza `exact_pop`/`pnl_expiry` sin duplicar lógica.
- *Binomial en el backtest*: ≈ 3 min por plantilla (C2-4).
- *pandas en el motor*: rompe la pureza y el aislamiento (AC-C2-16).
- *Fixtures de histórico grabadas*: caducarían con la fecha; un GBM determinista generado en código sirve para todos los tests de `datos/` y de UI.
- *Descarga fija de 16 años con "años" solo recortando* (propuesta inicial de este plan): **rechazada por el usuario (21-11-26)**; se adopta descargar `años + 1` con caché que reutiliza solo si cubre el tramo (PD-14, IP-10, IP-11). Coste aceptado: cambiar a más años obliga a una nueva descarga (una solicitud por símbolo).

## Arquitectura

```
opciones/                       # motor (los módulos existentes NO cambian)
  calibration.py   NUEVO        # wilson_interval, brier_score, climatological_brier, brier_skill, calibration_bins,
                                #   max_deviation, effective_n, tail_diagnostics  (numpy + scipy.stats, puro)
  backtest.py      NUEVO        # realized_vol, trailing_mu, trailing_dividend_yield, rate_at, expiry_index,
                                #   first_analyzed_index, run_backtest -> BacktestResult  (numpy, puro, importa solo opciones.*)
datos/
  types.py         AMPLIADO     # + PriceHistory (frozen)
  provider.py      AMPLIADO     # + HistoryProvider (Protocol aparte); MarketDataProvider intacto
  tickers.py       AMPLIADO     # + HISTORY_SYMBOLS, history_symbols(label)
  fake.py          AMPLIADO     # + FakeProvider.get_history (GBM determinista generado en código)
  yahoo.py         AMPLIADO     # + YahooProvider.get_history
  history_cache.py NUEVO        # history_path, read_history, write_history, is_fresh, covers (cobertura del tramo pedido)
  history_service.py NUEVO      # clean_history, load_history(years) (descarga years+1 años naturales), HistoryLoad, textos de antigüedad
  __init__.py      AMPLIADO     # reexporta lo nuevo (sin importar yfinance/pandas)
ui_backtest.py     NUEVO (raíz) # render_backtest(...), clear_backtest_state(), gráficos plotly, avisos fijos
app.py             +~15 líneas  # TAB_NAMES con "Backtest", main() llama render_backtest pasando el callable `data_provider` (sin invocarlo), clear_loaded_data limpia el backtest
```

### Contratos de datos del motor

- `BacktestResult` (dataclass): `dates` (ISO, array de fechas válidas), `pop`, `pop_mu` (o `None` si no se pidió), `win` (bool/0-1), `z`, `vol` (arrays alineados), `skipped` (dict `{no_window, no_expiry, invalid_market, no_rate}` con enteros), `warnings` (lista de textos en español), más `n` y `years_analyzed` como propiedades.
- `run_backtest(dates, close, adj_close, div_dates, div_amounts, rate_dates, rate_values, template, underlying, horizon_days, vol_window, step, settings, fallback_rate, first_date=None, with_mu=False) -> BacktestResult`. `rate_dates/rate_values` pueden ser `None` (entonces r = `fallback_rate`). `settings` ya resuelto (IP-5). `first_date` = inicio del recorte por años (IP-3).
- `BinRow` (dataclass): `lo`, `hi`, `n`, `n_eff`, `mean_pop`, `observed`, `ci_low`, `ci_high`, `few` (n < 10), `empty` (n = 0).
- `TailResult` (dataclass): `n`, `mean`, `std`, `skew`, `excess_kurtosis`, `frac_gt2`, `frac_lt_m2` (esperados 0,0455 y 0,0228 como constantes del módulo), `quantiles` (dict nivel → (empírico, normal)).

### Reglas de fechas (resumen operativo)

Para cada índice muestreado i (cada `step` sesiones desde `first_date`): sin ventana si `i < max(W, 252)`; vol/μ/q con datos ≤ fecha[i]; r por `rate_at`; vencimiento `expiry_index(...)`; mercado `Market(underlying, close[i], vol, H, r, q, "black_scholes")`; `validate_market` + `validate_legs`; `build_legs(template, market)`; `pop = exact_pop(market, legs, settings, SimulationSettings(mu=None))`; `pop_mu` análogo con `mu=trailing_mu`; `win = pnl_expiry(legs, market, settings, np.array([close[j]]))[0] > ZERO_TOL`; `z` según PD-10 con `close[j]/close[i]`.

## Phase Completion Rules

A phase is NOT complete until:

1. **Integration Test** — el bloque funciona con los anteriores y con los 2742 tests existentes (`.venv/bin/pytest -q` completo, red bloqueada por `conftest.py`).
2. **Manual Test** — el usuario puede reproducir con `.venv/bin/python -c ...` (bloques 1–8) y con la checklist manual (bloques 9–10 y cierre).
3. **Data Verification** — cifras de referencia (Wilson de valores conocidos, Brier de casos pequeños, vol/μ/q de series cortas, tasas de acierto de oráculos) **recalculadas con las entradas exactas de cada test** (lección de Etapas A/B1/C1); se anota en el test el valor medido y la tolerancia.
4. **Error Handling** — entradas malas, histórico vacío/corto, fallos de red o de ^IRX devuelven mensajes en español, nunca NaN, excepciones hacia la UI ni números inventados.
5. **User Confirmation** — el usuario dice "funciona".

Status: ⏳ PLANNED · 🔨 CODE DONE · 🧪 TESTING · ✅ VERIFIED · 🚧 BLOCKED. Regla honesta: tests verdes sin revisión del usuario es `🔨 CODE DONE`, no `✅ VERIFIED`; solo el usuario pasa un bloque a `✅ VERIFIED`. Lección de MVP/A/B1/C1: vc-execute-agent no puede escribir bajo `process/`; el estado del plan y el reporte los actualiza UPDATE PROCESS.

Reporte (lo crea EXECUTE/UPDATE PROCESS, no este plan): `process/general-plans/completed/etapa-c2-historico-backtest_21-11-26/etapa-c2-historico-backtest_REPORT_<fecha>.md`.

## Acceptance Criteria

Se heredan literalmente **AC-C2-1..AC-C2-17 del SPEC** (no se reescriben). Interpretaciones fijadas por este plan:

- **AC-C2-1:** `HistoryProvider.get_history(symbol, start, end)`; `FakeProvider` determinista con semilla (misma llamada → mismos datos; dos tickers distintos → series distintas); rango o ticker sin datos → `EmptyDataError` con mensaje en español; 429 → `RateLimitError`; fallo de conexión → `NetworkError` (mapeo ya existente en `to_datos_error`).
- **AC-C2-2:** `clean_history` descarta la fila de hoy y las futuras, precios NaN/≤ 0/no numéricos (en `close` o `adj_close`), fechas duplicadas; ordena ascendente; conserva solo dividendos > 0 con fecha válida.
- **AC-C2-3:** caché propia, una por ticker, `schema_version` 1, escritura atómica; vuelve a descargar si no es fresca **o no cubre el tramo pedido `years + 1`** (PD-14, IP-10; ampliación de la regla del SPEC por decisión del usuario 21-11-26); fresca y que cubre → 0 llamadas; menos años que los cacheados → reutiliza; más años → descarga completa; sin red usa la caché con aviso de antigüedad; sin caché y sin red → `DatosError` en español.
- **AC-C2-4:** aviso con los años reales disponibles según IP-3 y el backtest usa lo que hay (con fuente corta no hay redescarga repetida ni aviso de "no cubre": IP-10/IP-11). "Calcular" con un histórico que no cubre `bt_years + 1` → `st.warning` `MSG_BT_NOT_COVERED` sin calcular (IP-11).
- **AC-C2-5:** vol realizada = `std(ddof=1)` de log-rendimientos de `adj_close` de W sesiones × √252; test del oráculo manual; test "sin mirar el futuro": alterar cualquier dato posterior a t (precios y dividendos y ^IRX) deja idéntico el resultado de esa fecha (misma PoP, win salvo que cambie el precio de vencimiento, que sí es futuro por definición: la comprobación se hace sobre `pop`, `vol`, `pop_mu`, y sobre `win` solo si el precio de t+H no se toca).
- **AC-C2-6:** vencimiento = último día ≤ t+H (calendarios pequeños con fines de semana y festivos); muestreo cada `step` sesiones; cola y arranque saltados y contados.
- **AC-C2-7:** modelo forzado a Black-Scholes (`Market.pricing_model == "black_scholes"` verificado con un espía/`monkeypatch` de `exact_pop`); `build_legs` reutilizado (patas iguales a las del catálogo para el mismo Market); fecha inválida se salta y se cuenta; ganar con y sin comisiones con un caso calculado a mano.
- **AC-C2-8:** ^IRX en porcentaje → fracción (4,12 → 0,0412) en `history_service`; respaldo constante con aviso; q = dividendos 12 meses previos / `close[t]`; índice → q = 0 con nota.
- **AC-C2-9:** deciles fijos, 10 filas siempre; Wilson con valores conocidos (p. ej. k = 5, n = 10 → [0,2366, 0,7634] con 4 decimales, recalcular en el test); vacío "—"; n < 10 marcado y fuera de la desviación máxima.
- **AC-C2-10:** oráculos de GBM (tolerancias en el bloque 3): diagonal en agregado con GBM de volatilidad constante; deciles con n ≥ 100 dentro de 0,15 con GBM de regímenes (10/20/40 % en bloques de 504 sesiones, o W = 60); Brier ≈ Σp(1−p)/N ± 0,04 y brecha de habilidad (Brier climatológico − Brier) ≥ 0,03 (validado: C-V2).
- **AC-C2-11:** serie con saltos (base 10 % + 2 % de días con salto N(0, 6 %)): curtosis en exceso > 2 y desviación máxima ≥ 0,20, semilla fija.
- **AC-C2-12:** `effective_n = min(N, años·365/H)`, aviso de solapamiento presente, μ de ventana 252 con datos ≤ t (misma prueba de "futuro" que AC-C2-5 aplicada a `pop_mu`).
- **AC-C2-13:** 4.ª pestaña con los controles de IP-6; sin botón no se descarga ni se calcula (el proveedor falso cuenta llamadas = 0 y `bt_result` ausente); "Entrada manual" → `st.info` pidiendo un ticker curado.
- **AC-C2-14:** con datos cargados y "Calcular": figura de fiabilidad (traza diagonal y = x + puntos con `error_y`), tabla por tramo (`st.dataframe`), 3 métricas (Brier, N, N efectivo), avisos fijos (textos exactos abajo) y figura de colas; el resultado se reutiliza si la clave de parámetros no cambia (el proveedor y `run_backtest` no se vuelven a llamar).
- **AC-C2-15:** 10 años, paso 5 (≈ 494 fechas), Black-Scholes: cota holgada **< 5 s** (medido 1,4 s); con línea μ **< 10 s**.
- **AC-C2-16:** `git diff --stat -- opciones/` solo muestra `calibration.py` y `backtest.py` nuevos (ningún módulo existente); `import datos` sin yfinance/pandas; `opciones.backtest`/`opciones.calibration` se importan en un subproceso sin streamlit, pandas, yfinance ni `datos`; `HistoryProvider` intercambiable (prueba con una clase mínima).
- **AC-C2-17:** `.venv/bin/pytest -q` → 2742 existentes + nuevos passed, **4 skipped** (ver desviación v); también bajo `unshare -rn`; `requirements.txt` sin diff; ningún test escribe en el `.cache_datos/` real.

**Avisos fijos (textos canónicos, en `ui_backtest.py` como constantes `MSG_BT_*`):** volatilidad realizada ≠ implícita; opciones americanas valoradas como europeas; q aproximado con 12 meses previos; "Mide calibración de probabilidades, no rentabilidad real: no hay precios históricos de opciones."; "Herramienta de estudio, no asesoría de inversión." (reutiliza `MSG_NOT_ADVICE`); texto de colas: "colas gordas del modelo + ruido de volatilidad"; aviso de solapamiento de ventanas junto a N efectivo.

## Touchpoints

| Bloque | Archivo | Acción |
|---|---|---|
| 1 | `opciones/calibration.py` | crear |
| 1 | `tests/test_calibration.py` | crear |
| 2 | `opciones/backtest.py` (ayudantes) | crear |
| 2 | `tests/test_backtest_helpers.py` | crear |
| 3 | `opciones/backtest.py` (`BacktestResult`, `run_backtest`) | ampliar |
| 3 | `tests/synthetic.py` (generadores GBM, regímenes y saltos con `numpy.random.default_rng(seed)`), `tests/test_backtest.py` | crear |
| 4 | `datos/types.py` (`PriceHistory`), `datos/provider.py` (`HistoryProvider`), `datos/tickers.py` (`HISTORY_SYMBOLS`, `history_symbols`), `datos/fake.py` (`get_history`), `datos/__init__.py` | modificar |
| 4 | `tests/test_datos_history_types.py` | crear |
| 5 | `datos/history_cache.py`, `tests/test_datos_history_cache.py` | crear |
| 6 | `datos/history_service.py`, `tests/test_datos_history_service.py` | crear |
| 6 | `datos/__init__.py` | modificar (reexportar) |
| 7 | `datos/yahoo.py` (`get_history`), `tests/test_datos_yahoo_history.py` (crear), `tests/test_datos_live.py` (segunda función opt-in) | modificar / crear |
| 8 | `tests/test_datos_isolation.py` (4 pruebas nuevas) | ampliar |
| 9 | `ui_backtest.py`, `app.py` (`TAB_NAMES`, `main`, `clear_loaded_data`, `init_state`), `tests/test_app_backtest.py` (crear), `tests/test_app_smoke.py` (**solo** la lista de pestañas de la línea 65) | crear / modificar |
| 10 | `ui_backtest.py`, `tests/test_app_backtest.py` | ampliar |
| Cierre | `process/context/all-context.md`, `process/context/tests/all-tests.md` | modificar en UPDATE PROCESS (no en EXECUTE de código) |

Solo lectura / sin tocar: **todo `opciones/` existente** (`simulation.py`, `catalog.py`, `payoff.py`, `models.py`, `metrics.py`, `validation.py`, `commissions.py`, `__init__.py`, …), `datos/cache.py`, `datos/service.py`, `datos/filters.py`, `datos/errors.py`, `requirements.txt`, `.gitignore` (ya ignora `.cache_datos/`, que cubre `history/`), `tests/conftest.py`, el SPEC. **Nunca tocar el `.cache_datos/` real del usuario ni un Streamlit en el puerto 8501.**

## Public Contracts

| Elemento | Contrato |
|---|---|
| `PriceHistory` (frozen) | `ticker: str`, `dates: tuple[str, ...]` (ISO ascendente), `close`, `adj_close: tuple[float, ...]`, `dividends: tuple[tuple[str, float], ...]` (fecha, importe), `source: str = "live"`, `loaded_at: datetime \| None = None`. |
| `HistoryProvider` | `@runtime_checkable Protocol`: `get_history(symbol: str, start: date, end: date) -> PriceHistory` (start inclusivo, end exclusivo); lanza `NetworkError`/`RateLimitError`/`EmptyDataError`. `MarketDataProvider` intacto. |
| `datos.tickers.history_symbols(label)` | tupla de símbolos Yahoo a probar en orden: `("^GSPC", "^SPX")` para SPX, `(label,)` para el resto; `RATE_HISTORY_SYMBOL = "^IRX"`. |
| `history_cache` | `history_path(label, cache_dir=None) -> Path`; `write_history(history, fetched_at, requested_start, cache_dir=None) -> (bool, aviso \| None)`; `read_history(label, cache_dir=None) -> (PriceHistory, fetched_at, requested_start \| None) \| None`; `is_fresh(fetched_at, last_date, today) -> bool`; `covers(first_date, requested_start, start, tolerance_days=7) -> bool` (IP-10); `start_for_years(today, years) -> date` (= `today − (years + 1)` años naturales, 29-feb → 28-feb; único lugar de esta aritmética). |
| `history_service` | `clean_history(history, today) -> PriceHistory`; `load_history(provider, label, years, today=None, now=None, cache_dir=None) -> (HistoryLoad, list[str])` (`years` obligatorio, 1–15; pide `start = start_for_years(today, years)`) o lanza `DatosError` (sin red ni caché); `HistoryLoad(history, rates, source, loaded_at, symbol, requested_start)` con `rates: PriceHistory \| None` (cierre ya en **fracción**) y `requested_start: date | None` (IP-11; `None` solo con una caché vieja sin el campo usada sin red); `history_age_text(load, now)`. |
| `opciones.calibration` | `wilson_interval(k, n, z=1.96, deff=1.0) -> (lo, hi) \| None`; `brier_score(pop, win)`; `climatological_brier(win)`; `brier_skill(pop, win)`; `calibration_bins(pop, win, deff=1.0, min_cases=10) -> list[BinRow]` (10 filas); `max_deviation(rows)`; `effective_n(n, years_analyzed, horizon_days)`; `tail_diagnostics(z) -> TailResult`. |
| `opciones.backtest` | `realized_vol`, `trailing_mu`, `trailing_dividend_yield`, `rate_at`, `expiry_index`, `first_analyzed_index`, `run_backtest(...) -> BacktestResult`. Importa solo `opciones.*`, numpy y scipy.stats; **no** importa `datos`, `streamlit` ni pandas. |
| `ui_backtest` | `render_backtest(get_provider, now, settings, underlying, ticker, fallback_rate, cache_dir)` (`get_provider` es un **callable** que solo se invoca dentro de la rama del botón `bt_load`; C-V1); `clear_backtest_state()`; `copy_bt_param(field)`; constantes `MSG_BT_*` (incluye `MSG_BT_NOT_COVERED` y `MSG_BT_YEARS_CAPTION` = "Se descargan los años elegidos + 1 de calentamiento; cambiar a más años obliga a volver a descargar."); `BT_DEFAULTS`. |
| Claves de `session_state` | simples: `bt_template` ("iron_condor"), `bt_horizon` (30), `bt_window` (30; `st.number_input` entero, rango 10–250 sesiones), `bt_step` (5), `bt_years` (10), `bt_fees` (True), `bt_use_mu` (False); widgets `bt_*_input`; botones `bt_load`, `bt_run`; datos: `bt_history` (`{"ticker", "load", "notices"}` o `None`), `bt_result` (`{"key", "result"}` o `None`), `bt_error`. `clear_loaded_data()` de `app.py` también las limpia (cambio de ticker/tipo). |
| `opciones/` existente | **sin cambios**. |
| `MarketDataProvider`, `service.py`, `cache.py` | **sin cambios**. |

## Blast Radius

- **Archivos nuevos:** 2 módulos de motor, 2 de `datos/`, `ui_backtest.py`, `tests/synthetic.py` y 9 archivos de test (~150 tests).
- **Modificados:** `datos/types.py`, `datos/provider.py`, `datos/tickers.py`, `datos/fake.py`, `datos/yahoo.py`, `datos/__init__.py`, `app.py` (~15 líneas), `tests/test_datos_isolation.py` (ampliado), `tests/test_datos_live.py` (ampliado), `tests/test_app_smoke.py` (una aserción, línea 65).
- **Riesgo:** medio-bajo. El motor existente no cambia. Riesgos principales: `app.py` (cuarta pestaña: AppTest ejecuta todas las pestañas, nada pesado sin botón), `FakeProvider` compartido con tests de C1 (se añade método, no se cambia el existente) y la interfaz de Yahoo no verificada en vivo (histórico de ^GSPC/^SPX/^IRX).
- **Entorno:** sin dependencias nuevas; sin instalaciones; sin red salvo la corrida opcional en vivo del bloque 7.

## Implementation Checklist

Orden indicado en la tabla de estado; cada bloque termina con su gate y `.venv/bin/pytest -q` completo en verde, y se commitea directamente en `main` (mensaje convencional `feat: etapa C2 bloque N - ...`). Reglas transversales: TDD (tests primero, en rojo), funciones cortas, comentarios y docstrings en español, identificadores en inglés, `pytest.approx` en floats, ningún `print` en `opciones/` ni `datos/`, `opciones/backtest.py` y `calibration.py` no importan `datos`, `streamlit` ni pandas, **no modificar módulos existentes de `opciones/`**.

**Reglas vinculantes para el agente de EXECUTE (lecciones de MVP/A/B1/C1):**
- Los agentes de EXECUTE **no pueden escribir bajo `process/`**: devolver estado de bloques, cifras medidas y texto de contexto en el mensaje final.
- **No tocar `opciones/` existente** (`git diff --stat -- opciones/` solo muestra los dos archivos nuevos).
- **Nunca tocar el `.cache_datos/` real ni el servidor Streamlit del puerto 8501**; los tests usan `tmp_path`; un servidor manual usa 8502+ y se detiene al terminar; tras cambiar código, reiniciarlo (imports obsoletos).
- `st.metric` trunca textos largos: avisos y notas en `st.caption`/`st.info`/`st.warning`.
- **`format_func` de AppTest no puede leer `session_state` ni el reloj**: calcular etiquetas dentro de la ejecución del script (patrón de `render_expiry_select`).
- El estado de un **widget** solo cambia desde callbacks; las claves `bt_history`/`bt_result`/`bt_error` no son de widgets y se escriben en el cuerpo (IP-7).
- AppTest ejecuta todas las pestañas y no puede vaciar un `number_input` a `None`.
- **Recalcular cifras de referencia con las entradas exactas** de cada test; anotar valor medido y tolerancia. Nunca cambiar un número esperado de un test existente.
- Pruebas contra la red real solo con `LIVE_DATA=1`, a propósito.
- Tests de fechas: reloj inyectado; el `FakeProvider` genera días hábiles hacia atrás desde ese reloj.

### Bloque 1 — `opciones/calibration.py` (AC-C2-9, AC-C2-10 parcial, AC-C2-11 parcial, AC-C2-12 parcial)

**Explicación para el usuario:** es la "calculadora de notas" del estudio: dado un listado de "PoP que dijo la app" y "¿ganó de verdad?", agrupa por tramos de 10 %, da el intervalo de confianza de cada tramo, el puntaje de Brier (cuánto se equivocó la app en promedio) y mide si los movimientos extremos son más frecuentes de lo que dice la normal. Es matemática pura sin Streamlit ni datos.

- [ ] Ejecutar `date +%d-%m-%y` y `.venv/bin/pytest -q` → 2742 passed, 3 skipped antes de tocar nada.
- [ ] Crear `tests/test_calibration.py` (en rojo, ~25): Wilson con valores conocidos (k=5,n=10; k=0; k=n; `n=0` → `None`; `deff=0.5` ensancha el intervalo; `deff=1.0` igual al ingenuo); Brier de casos pequeños a mano (pop=[0.5,0.5], win=[1,0] → 0,25; perfecto → 0; peor → 1); climatológico y habilidad (habilidad 0 cuando pop = tasa constante); deciles: 10 filas siempre, PoP = 1,0 en el último, PoP = 0 en el primero, bordes 0,1/0,2…, vacío → `empty` y observado `None`, n=9 → `few`, n=10 no `few`, `max_deviation` ignora filas `few`/vacías y devuelve `None` si no queda ninguna; `effective_n` (min con N, H=30 y 10 años → 121,67 → se limita a N si N menor; N=0 → 0); `tail_diagnostics` con muestra normal sembrada (curtosis ≈ 0, std ≈ 1, cuantiles cercanos) y con muestra construida a mano (curtosis conocida, excedencias contadas a mano) y vacía/NaN-safe; ningún NaN en salidas; entradas listas o arrays.
- [ ] Crear `opciones/calibration.py` según Public Contracts (comentarios en español; constantes `EXPECTED_GT2 = 0.0455`, `EXPECTED_LT_M2 = 0.0228`, `MIN_CASES = 10`, `QUANTILE_LEVELS = (0.01, 0.05, 0.5, 0.95, 0.99)`).
- [ ] Comandos: `.venv/bin/pytest tests/test_calibration.py -q`; `git diff --stat -- opciones/` (solo archivo nuevo); `.venv/bin/pytest -q`.
- **Pass criteria:** tests nuevos verdes; 2742 + 3 skipped intactos; sin NaN; módulo sin imports de `datos`/`streamlit`/pandas.

### Bloque 2 — `opciones/backtest.py` ayudantes (AC-C2-5 parcial, AC-C2-6 parcial, AC-C2-8 parcial, AC-C2-12 parcial)

**Explicación para el usuario:** las piezas pequeñas del backtest, cada una probada sola contra un cálculo hecho a mano: cuánta volatilidad hubo en las últimas semanas, qué crecimiento tuvo el último año, cuánto dividendo pagó el último año, qué tasa había ese día y cuál es el último día de negociación antes del vencimiento.

- [ ] Crear `tests/test_backtest_helpers.py` (en rojo, ~22): `realized_vol` contra `numpy.std(ddof=1)` calculado a mano sobre una serie corta con W=5, exige `i ≥ W` (si no, `None`), usa `adj_close` (cambiar `close` no altera); `trailing_mu` contra cálculo manual (media de 252 log-rendimientos × 252 + vol²/2) y exige `i ≥ 252`; **sin mirar el futuro** (alterar datos posteriores a i no cambia nada); `trailing_dividend_yield`: ventana (t−365 d, t] con bordes exactos (dividendo en t−365 d excluido, en t incluido), 0 si no hay dividendos, índice → 0; `rate_at`: valor exacto en la fecha, fin de semana → el viernes, antes del primer dato → `None`, porcentaje ya convertido; `expiry_index`: calendarios pequeños con fin de semana y festivo (t+H cae en sábado → viernes; en festivo → día anterior), `None` si el último dato < t+H, t+H = último dato válido; `first_analyzed_index` (recorte por años, calentamiento `max(W,252)`, aviso de corto con la regla IP-3).
- [ ] Crear `opciones/backtest.py` con esos ayudantes (arrays `datetime64[D]` internos; sin pandas; imports solo `numpy` y `opciones.*`).
- [ ] Comandos: `.venv/bin/pytest tests/test_backtest_helpers.py -q`; `git diff --stat -- opciones/`; `.venv/bin/pytest -q`.
- **Pass criteria:** tests verdes con valores medidos a mano; suite completa verde; sin pandas.

### Bloque 3 — `run_backtest`, oráculos, sin mirar el futuro y tiempo (AC-C2-5, 6, 7, 10, 11, 12, 15)

**Explicación para el usuario:** el recorrido completo por el pasado. Se prueba con series inventadas cuya "verdad" conocemos: si el mundo es exactamente el del modelo (movimiento browniano), la app debería quedar bien calibrada; si el mundo tiene saltos bruscos, las colas deben salir mal. Y se comprueba que no se "hace trampa" mirando el futuro.

- [ ] Crear `tests/synthetic.py` (generadores `gbm_series`, `regime_series`, `jump_series` con `numpy.random.default_rng(seed)`; devuelven fechas hábiles ISO, `close`, `adj_close` iguales, sin dividendos) y `tests/test_backtest.py` (en rojo, ~20): estructura de `BacktestResult` (arrays alineados, `skipped` con las 4 claves); muestreo por `step` (índices esperados a mano), cola y arranque saltados y contados; `Market.pricing_model == "black_scholes"` forzado (espía sobre `exact_pop` ve el mercado); patas iguales a `build_legs(template, market)` del mismo Market; fecha con vol < `MIN_VOL` → `invalid_market` contado; `no_rate` contado; **ganar con y sin comisiones** (caso de 2–3 fechas calculado a mano con un iron condor y `ZERO_TOL`); oráculos (tolerancias **validadas por la medición del prototipo**, C-V2; a re-medir con las entradas exactas y anotar): GBM σ constante ≥ 40 años sintéticos × 2 semillas → |media PoP − tasa observada| ≤ **0,05** (medido 0,006–0,025; error estándar ≈ 0,02 con N efectivo ≈ 490) y |curtosis en exceso| < 1; regímenes (10/20/40 % en **bloques de 504 sesiones**, o bloques de 126 con W = 60) → cada decil con **n ≥ 100** dentro de **0,15** (0,10 solo si lo medido deja margen), brecha de habilidad (Brier climatológico − Brier) ≥ **0,03** (medido 0,04–0,064) y |Brier − Σp(1−p)/N| ≤ **0,04** (medido hasta 0,027); saltos (base 10 % + 2 % de días con salto N(0, 6 %)) → curtosis > 2 (medido 2,67 / 5,31) y `max_deviation` ≥ 0,20 (medido ≥ 0,46), semilla fija y serie ≥ 40 años; **regla de ensanchado:** el ejecutor mide cada oráculo y, si una cota queda a menos del 25 % de su valor medido, la ensancha con la razón escrita en el test y anota los valores medidos en el informe del bloque; **sin mirar el futuro**: para una fecha muestreada, alterar precios, dividendos y ^IRX posteriores a t no cambia `pop`, `pop_mu` ni `vol` de esa fecha; línea μ ausente (`None`) cuando `with_mu=False` y presente con N igual al de la neutral cuando `True`; N efectivo = `effective_n(N, years, H)`; **tiempo**: 10 años sintéticos, paso 5 (≈ 494 fechas) < 5 s y con μ < 10 s (cotas holgadas; anotar tiempos medidos).
- [ ] Ampliar `opciones/backtest.py` con `BacktestResult` y `run_backtest` (PD-3..PD-10, IP-2..IP-5).
- [ ] Guardar en el test los valores medidos (tasa observada, curtosis, Brier, tiempos) y los tamaños de serie usados (IP-9); mantener los oráculos pocos (cada uno 1–2 s).
- [ ] Comandos: `.venv/bin/pytest tests/test_backtest.py tests/test_backtest_helpers.py tests/test_calibration.py -q`; `git diff --stat -- opciones/`; `.venv/bin/pytest -q`.
- **Pass criteria:** oráculos dentro de tolerancia (ninguna cota a menos del 25 % del valor medido; valores medidos anotados en el informe) con semillas fijas (no aleatorios); tiempo dentro de cota; suite completa verde; existentes de `opciones/` sin diff.

### Bloque 4 — `PriceHistory`, `HistoryProvider`, `FakeProvider.get_history` y mapa de símbolos (AC-C2-1 parcial, AC-C2-16 parcial)

**Explicación para el usuario:** definimos la "caja" del histórico (fechas, cierre, cierre ajustado, dividendos) y el "enchufe" para obtenerlo, separado del enchufe de opciones de C1 para no tocarlo. El proveedor falso inventa un histórico realista pero siempre igual (con semilla) y calculado desde el reloj, para que las pruebas no caduquen.

- [ ] Crear `tests/test_datos_history_types.py` (en rojo, ~16): `PriceHistory` frozen y campos; una clase mínima satisface `HistoryProvider` (`isinstance`); `FakeProvider` satisface ambos Protocol; `get_history` determinista (dos llamadas iguales; dos tickers con series distintas; semilla = suma de `ord`, no `hash()`); días hábiles hacia atrás desde el reloj inyectado sin fines de semana, `start` inclusivo / `end` exclusivo, `close ≥ ` 0, `adj_close ≤ close` cuando hay dividendos; dividendos trimestrales opcionales con fecha y > 0; `^IRX` devuelve porcentaje (constante o con un escalón, valores en 0–20); ticker desconocido → `EmptyDataError`; rango vacío → `EmptyDataError`; `fail_with` lanza el error en `get_history`; `history_empty_symbols`, `history_fail_symbols` e `history_years` actúan solo sobre los símbolos/años indicados y, con sus valores por defecto, la salida es idéntica a la anterior; `history_symbols("SPX") == ("^GSPC", "^SPX")` y `history_symbols("SPY") == ("SPY",)`; los métodos existentes de `FakeProvider` (opciones) no cambian (tests de C1 siguen verdes).
- [ ] Modificar `datos/types.py` (`PriceHistory`), `datos/provider.py` (`HistoryProvider`), `datos/tickers.py` (`HISTORY_SYMBOLS`, `RATE_HISTORY_SYMBOL`, `history_symbols`), `datos/fake.py` (`get_history`, parámetros `sigma`, `mu`, `seed`, `dividends`, `irx_percent_series` y, **solo añadidos con valores por defecto que preservan el comportamiento actual** (C-V4): `history_empty_symbols` (símbolos que devuelven `EmptyDataError`, p. ej. `^GSPC` para probar el respaldo a `^SPX`), `history_fail_symbols` (mapa símbolo → error, p. ej. `^GSPC` con `NetworkError` que **no** debe reintentar con `^SPX`, o solo `^IRX` fallando = no fatal) e `history_years` (tope de años generados, para el aviso corto de AC-C2-4); `get_history` respeta `start`/`end` (y recorta además a `history_years` años hacia atrás si está fijado) y registra cada llamada en `history_calls`; `fail_with` sigue fallando todas las llamadas, también `get_history`), `datos/__init__.py` (reexportar los tipos nuevos).
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_history_types.py tests/test_datos_types.py tests/test_datos_service.py tests/test_datos_tickers.py -q`; `.venv/bin/pytest -q`.
- **Pass criteria:** tests nuevos verdes; los de C1 intactos; `MarketDataProvider` sin diff (`git diff -- datos/provider.py` solo añade).

### Bloque 5 — `datos/history_cache.py` (AC-C2-3 parcial)

**Explicación para el usuario:** guardamos el histórico de cada ticker en `.cache_datos/history/` para no volver a bajarlo a cada rato. Se considera "al día" si se bajó hoy o si ya contiene la última sesión cerrada, **y además debe cubrir el tramo de años pedido** (años elegidos + 1); si no, se baja de nuevo completo. La escritura es segura (o queda completo o no queda).

- [ ] Crear `tests/test_datos_history_cache.py` (en rojo, siempre con `tmp_path`, ~20): escribe/lee de ida y vuelta; nombre `SPY.json`, `SPX.json` (nunca `^SPX.json`) e `IRX.json` en `history/`; atómica (no deja temporales; fallo de escritura no destruye el viejo); JSON corrupto, esquema distinto, campos ausentes o de longitudes distintas → `None`; `fetched_at` sin zona → rechazado al escribir; `is_fresh`: mismo día de mercado (aunque el último dato sea viejo) → fresca; último dato ≥ última sesión cerrada (lunes con dato del viernes) → fresca; martes festivo/ayer sin dato → no fresca; borde de medianoche usando Nueva York; `requested_start` se escribe y se lee de ida y vuelta (y una caché sin el campo se lee con `None`); `start_for_years` (`today − (years + 1)` años naturales; 29-feb → 28-feb; `years = 1` y `15`); `covers`: primer dato = `start` → cubre; primer dato = `start` + 7 días → cubre (borde de tolerancia); `start` + 8 días → **no** cubre; `requested_start ≤ start` con primer dato posterior (fuente corta) → cubre; `requested_start` posterior a `start` y primer dato posterior → no cubre; `requested_start = None` se ignora (~+6 tests); nada se crea fuera de `tmp_path` (huella de `.cache_datos/` sin cambios, ver Comandos; C-V3).
- [ ] Crear `datos/history_cache.py` (reutiliza `_file_label`, `_atomic_write_json`, `market_today`, `DEFAULT_CACHE_DIR` de `datos.cache`; no modifica `cache.py`; solo biblioteca estándar).
- [ ] **Antes de empezar el bloque 5** (y al inicio de cada sesión de EXECUTE: re-baseline, porque el uso normal de la app por el usuario puede cambiar legítimamente `.cache_datos/`; nunca borrar ni modificar sus archivos) registrar la huella: `find .cache_datos -type f -printf '%p %s %T@\n' | sort | sha256sum` (incluye la subcarpeta `yfinance/`); `git status --short .cache_datos` **no sirve** (el directorio está ignorado por git).
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_history_cache.py tests/test_datos_cache.py -q`; repetir la huella y comprobar igualdad; `git check-ignore -v .cache_datos/history/x.json`; `.venv/bin/pytest -q`.
- **Pass criteria:** verdes; `datos/cache.py` sin diff; huella de `.cache_datos/` idéntica antes y después (ninguna escritura fuera de `tmp_path`).

### Bloque 6 — `datos/history_service.py` (AC-C2-1, 2, 3, 4, 8 parcial)

**Explicación para el usuario:** el "cerebro" del histórico: limpia filas sucias (precios raros, duplicados, la fila de hoy que puede estar a medias), decide si usa la caché (solo si está al día **y** cubre los años pedidos + 1) o descarga solo ese tramo, prueba `^GSPC` y luego `^SPX` para el índice, trae la tasa `^IRX` y, si esta falla, avisa y sigue con la tasa de la barra lateral.

- [ ] Crear `tests/test_datos_history_service.py` (en rojo, ~18, reloj fijo, `tmp_path`; todas las llamadas a `load_history` pasan `years`): `clean_history` (fila de hoy y futuras descartadas; NaN, 0, negativo, texto en `close`/`adj_close`; duplicados; orden ascendente; dividendos ≤ 0 o con fecha inválida descartados; no lanza); `load_history` con caché fresca **que cubre** → **0 llamadas** al proveedor; **menos años que los cacheados** (p. ej. cacheado con `years=10`, pedir 5) fresca → **0 llamadas** (reutiliza); **más años que los cacheados** (cacheado con 5, pedir 10) aunque esté fresca → **descarga completa** del nuevo tramo y reescribe la caché con el `requested_start` nuevo; caché fresca de una fuente corta (`history_years` bajo, `requested_start` ≤ `start`) → **0 llamadas** (sin bucle de descarga; IP-10); caché caducada → descarga completa y reescribe; descarga escribe caché; sin red + caché → usa caché con aviso de antigüedad; sin red + sin caché → `DatosError` en español; `RateLimitError` y `EmptyDataError` mapeados; SPX: `^GSPC` vacío (`history_empty_symbols={"^GSPC"}`) → prueba `^SPX`, ambos vacíos → error; `^GSPC` con error de red (`history_fail_symbols={"^GSPC": NetworkError}`) **no** reintenta con `^SPX` (el falso cuenta las llamadas por símbolo); ^IRX en porcentaje → `rates` en fracción (4,12 → 0,0412); fallo solo de ^IRX (`history_fail_symbols={"^IRX": NetworkError}`) → `rates is None` + aviso, no fatal; histórico más corto que lo pedido (`history_years` bajo) → datos tal cual (el aviso AC-C2-4 se calcula con `first_analyzed_index`, probado aquí con el resultado); el tramo pedido es `years + 1` (el proveedor falso registra en `history_calls` `start = today − (years + 1)` años naturales y `end = today + 1 día`, para `years` = 1, 5 y 15, y con 29-feb); **^IRX se pide con el mismo `start`/`end`** que el subyacente; sin red + caché que no cubre → usa la caché con aviso y `HistoryLoad.requested_start` refleja la caché (IP-11); `HistoryLoad.requested_start` coincide con el `start` pedido tras una descarga; **sin red + caché vieja sin `requested_start` → `HistoryLoad.requested_start is None`, sin excepción, y `covers` aplica el criterio del primer dato (S-2)**.
- [ ] Crear `datos/history_service.py`; reexportar en `datos/__init__.py`.
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_history_service.py tests/test_datos_history_cache.py tests/test_datos_history_types.py -q`; repetir la huella de `.cache_datos/` (misma orden del bloque 5) y comprobar igualdad con la línea base; `.venv/bin/pytest -q`.
- **Pass criteria:** verdes; reloj fijado en todos los tests; `service.py` y `cache.py` sin diff; huella de `.cache_datos/` sin cambios.

### Bloque 7 — `YahooProvider.get_history` con cliente simulado y prueba en vivo opcional (AC-C2-1, AC-C2-17 parcial)

**Explicación para el usuario:** ahora sí hablamos con Yahoo: pedimos el histórico diario sin ajuste automático (para tener a la vez el cierre normal, el ajustado y los dividendos) y lo traducimos a nuestras cajas. Lo probamos sin Internet con un "yfinance de mentira"; la prueba contra Yahoo real queda opcional y apagada.

- [ ] Crear `tests/test_datos_yahoo_history.py` (en rojo, ~12): `yf_module` simulado con DataFrame falso (o clase con `.index`, `__getitem__`, `.tolist()`, `.empty`); llamada con `interval="1d"`, `auto_adjust=False`, `actions=True` y `start`/`end`; columnas `Close`, `Adj Close`, `Dividends` → tuplas; fechas del índice → ISO; dividendos solo > 0; `empty` → `EmptyDataError`; excepciones de red/429/vacío mapeadas por `to_datos_error` (reutilizado); sin importar pandas (subproceso o `sys.modules`); `^IRX` devuelve porcentaje sin convertir (la conversión es de `datos`); timeout de la sesión ya existente respetado; `YahooProvider` satisface `HistoryProvider` y sigue satisfaciendo `MarketDataProvider`.
- [ ] Modificar `tests/test_datos_live.py`: **segunda** función `test_historial_en_vivo` con `skipif(LIVE_DATA != "1")` (SPY y ^GSPC/^SPX y ^IRX; cuenta solicitudes; escribe en `tmp_path`). Conteo esperado: **4 skipped**.
- [ ] Modificar `datos/yahoo.py` (`get_history`).
- [ ] **Una ejecución manual en vivo opcional** (`LIVE_DATA=1 .venv/bin/pytest tests/test_datos_live.py -q -s`; requiere red fuera del sandbox y aprobación): anotar si `^GSPC`/`^SPX`/`^IRX` devuelven historial, el nº de filas y de solicitudes. Si se deniega, el bloque queda `🔨 CODE DONE` con "corrida en vivo pendiente" (no bloquea ningún AC).
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_yahoo_history.py tests/test_datos_yahoo.py tests/test_datos_live.py -q`; `.venv/bin/pytest -q` → N passed, **4 skipped**.
- **Pass criteria:** verdes; el adaptador no importa pandas a nivel de módulo; `import datos` sigue sin yfinance.

### Bloque 8 — Aislamiento de importaciones y dependencias (AC-C2-16, AC-C2-17)

**Explicación para el usuario:** una comprobación de "higiene": el motor nuevo no puede depender de Streamlit ni de pandas ni de los datos de internet, `import datos` sigue siendo ligero y no se añadió ninguna librería.

- [ ] Ampliar `tests/test_datos_isolation.py` (en rojo, ~4, en subproceso): (a) `import datos` + los módulos `history_*` no cargan `yfinance` ni `pandas`; (b) `import opciones.backtest, opciones.calibration` no cargan `streamlit`, `pandas`, `yfinance`, `curl_cffi` ni `datos`; (c) con un finder que bloquea `pandas`/`yfinance`, `from opciones.backtest import run_backtest` funciona; (d) `requirements.txt` contiene exactamente las 7 líneas actuales (`numpy`, `scipy`, `plotly`, `streamlit`, `pytest`, `yfinance`, `pandas`).
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_isolation.py -q`; `git diff --stat -- opciones/ requirements.txt`; `.venv/bin/pytest -q`.
- **Pass criteria:** verdes; diff de `opciones/` = solo los 2 archivos nuevos; `requirements.txt` sin diff.

### Bloque 9 — UI esqueleto: pestaña, controles, "Cargar histórico" (AC-C2-3 parcial, AC-C2-4, AC-C2-13)

**Explicación para el usuario:** aparece la pestaña "Backtest" con sus controles (plantilla, horizonte, ventana, paso, años, comisiones, línea con tendencia histórica). Al abrirla no se descarga ni se calcula nada; solo el botón "Cargar histórico" trae y guarda los datos (los años elegidos más uno de calentamiento) y muestra de cuándo son; una nota junto al control de años avisa de que cambiar a más años obliga a volver a descargar. Con "Entrada manual" la pestaña te pide elegir un ticker de la lista.

- [ ] Crear `tests/test_app_backtest.py` (en rojo, ~12; helper `data_app`, `choose_ticker`, `FIXED_NOW` importados de `tests/test_app_smoke.py`, **sin** importar nombres `test_*`; `FakeProvider` con pocos años y `cache_dir` en `tmp_path`): existe la pestaña "Backtest" y es la 4.ª; controles con valores por defecto (iron condor, 30, 30, 5, 10, comisiones sí, μ no); rangos (H 7–120, **W 10–250 entero, por defecto 30 (min/max/defecto; S-1)**, paso 1–20, años 1–15); **caption `MSG_BT_YEARS_CAPTION` presente** ("cambiar a más años obliga a volver a descargar") junto al control de años; pulsar `bt_load` con `bt_years = 5` pide al proveedor falso `start = today − 6` años naturales (`history_calls`), y la segunda pulsación con 5 o menos años no hace llamadas (caché que cubre) mientras con `bt_years` mayor sí; sin botón: 0 llamadas a `get_history` y sin `bt_history`/`bt_result`; **sin botón `YahooProvider` nunca se construye** (monkeypatch de `datos.yahoo.YahooProvider` que lanza, o espía sobre `data_provider()` / la ruta de inyección por `session_state`), tanto en el fixture `app` desnudo como en `data_app` (C-V1); la pestaña por defecto no emite `st.warning`, `st.error` ni gráficos plotly; "Entrada manual" → `st.info` y botones ausentes/desactivados; con SPY elegido, pulsar `bt_load` rellena `bt_history`, muestra antigüedad ("histórico guardado de …" o "cargado a las HH:MM" con reloj fijado) y el aviso AC-C2-4 cuando el proveedor genera menos años de los pedidos (`FakeProvider(history_years=...)`); cambiar el ticker (o el tipo) limpia `bt_history` y `bt_result` (tipo SPY → QQQ); error de proveedor → `st.error` en español y, con caché, uso de la caché (`history_fail_symbols`/`fail_with`; `^GSPC` con error de red no cae a `^SPX`; solo ^IRX fallando → aviso no fatal y tasa de la barra lateral); la pestaña no falla con un proveedor que no implementa `HistoryProvider` (mensaje **solo tras pulsar** "Cargar histórico").
- [ ] Modificar `tests/test_app_smoke.py` **solo** la aserción de la línea 65 (lista de pestañas) → incluir "Backtest".
- [ ] Crear `ui_backtest.py` (controles con patrón IP-6, `render_backtest`, `clear_backtest_state`, lectura de histórico con `load_history`, textos) y modificar `app.py` (`TAB_NAMES`, `st.tabs` con 4 pestañas y `render_backtest(...)` pasando el **callable** `data_provider` (nunca `data_provider()` en cada rerun: construiría `YahooProvider`, importaría yfinance/pandas y crearía `.cache_datos/yfinance` real en cada AppTest; el callable se invoca solo en la rama `if st.button("Cargar histórico")`), `current_time()`, `settings_from_state()`, `underlying`, ticker, `rate_pct/100`, `cache_dir`; `init_state` con `BT_DEFAULTS`; `clear_loaded_data` llama a `clear_backtest_state`). `format_func` de la plantilla no lee `session_state` ni el reloj.
- [ ] Comandos: `.venv/bin/pytest tests/test_app_backtest.py tests/test_app_smoke.py -q`; `.venv/bin/pytest -q` (**emular el cambio de `app.py` contra la suite completa**).
- [ ] Repetir la huella de `.cache_datos/` y comprobar igualdad con la línea base (C-V3).
- **Pass criteria:** verdes; modo manual idéntico; ningún test existente cambia salvo la línea 65; sin excepciones visibles ante errores; `YahooProvider` no construido sin pulsar botón; huella de `.cache_datos/` sin cambios.

### Bloque 10 — UI resultados: "Calcular", gráficos, tabla, avisos y caché de sesión (AC-C2-12, AC-C2-14, AC-C2-4)

**Explicación para el usuario:** con el histórico cargado, "Calcular" muestra el gráfico de fiabilidad (¿cuando la app dice 70 %, gana ~70 %?), la tabla por tramos, el puntaje de Brier, el número de casos y de casos independientes, el diagnóstico de colas y los avisos de qué mide y qué no. Si cambias un parámetro el resultado viejo se oculta hasta que pulses "Calcular" otra vez. Si subes los años por encima de lo cargado, "Calcular" te pide pulsar "Cargar histórico" de nuevo en vez de calcular con datos insuficientes.

- [ ] Ampliar `tests/test_app_backtest.py` (en rojo, ~14): `Calcular` sin histórico → `st.warning`; **cargar con `bt_years = 3`, subir `bt_years` a 8 y pulsar `bt_run` → `st.warning` con "El histórico cargado no cubre 8 años: pulsa «Cargar histórico»", `bt_result` ausente y `run_backtest` no llamado (espía); bajar a 2 años → calcula sin avisar; pulsar "Cargar histórico" con 8 y luego `bt_run` → calcula; fuente corta (`history_years` bajo, histórico cargado con los años pedidos) → **no** aparece el aviso de "no cubre" y sí el de histórico corto (AC-C2-4, IP-11)**; con histórico (proveedor falso, 4–5 años, paso grande para que dure < 1 s) → `bt_result` con `key` y `result`; figuras en pantalla: una con traza diagonal y traza de puntos con `error_y` (inspeccionando `at.get("plotly_chart")`/datos de las figuras si AppTest las expone, o comprobando funciones puras `build_reliability_figure`/`build_tails_figure` devueltas por `ui_backtest`); tabla por tramo con 10 filas; 3 métricas (`Brier`, `Casos (N)`, `N efectivo`); avisos fijos presentes (cada `MSG_BT_*`, incluido "no rentabilidad real", "estudio, no asesoría", "colas gordas del modelo + ruido de volatilidad" y aviso de solapamiento); caption "≈ N fechas, ~X s"; segunda línea μ solo con `bt_use_mu` activo; **resultado en caché de sesión**: segundo `rerun` sin cambios no llama a `run_backtest` (espía) ni al proveedor; cambiar un parámetro → mensaje "los parámetros cambiaron: pulsa Calcular" y el resultado viejo oculto; cambiar un ajuste de comisiones o recargar el histórico (huella distinta) invalida la clave; histórico corto → aviso con años reales; tramos con n < 10 marcados "pocos casos" en la tabla; ningún NaN en pantalla.
- [ ] Ampliar `ui_backtest.py` con la comprobación de cobertura de "Calcular" (IP-11: `need_start = start_for_years(today, bt_years)`; `not covers(...)` → `st.warning(MSG_BT_NOT_COVERED)` y no calcular), más `build_reliability_figure(rows, rows_mu=None)` (diagonal y = x; puntos con barras de error de Wilson; gris hueco para n < 10; serie μ opcional), `build_tails_figure(tail)` (histograma en densidad + curva normal + tabla de cuantiles), tabla con `st.dataframe`, métricas, avisos; clave de caché `(ticker, template, H, W, step, years, fees, use_mu, comisiones, r de respaldo si no hay ^IRX, huella del histórico = última fecha + nº de filas)`; spinner y caption de tiempo.
- [ ] Comandos: `.venv/bin/pytest tests/test_app_backtest.py tests/test_app_smoke.py -q`; `.venv/bin/pytest -q`.
- [ ] Repetir la huella de `.cache_datos/` y comprobar igualdad con la línea base (C-V3).
- **Pass criteria:** verdes; huella de `.cache_datos/` sin cambios; aspecto visual pendiente de la checklist manual (Hybrid AC-C2-14).

### Cierre — suite completa sin red y checklist manual (AC-C2-15, 16, 17)

- [ ] Gate de cierre: `.venv/bin/pytest -q` → **2742 existentes + nuevos passed, 4 skipped**; `unshare -rn .venv/bin/pytest -q` (sin red, verificado como utilizable en C1); `git diff --stat -- opciones/` (solo `calibration.py` y `backtest.py` nuevos); `git diff --stat -- requirements.txt` vacío; huella de `.cache_datos/` (`find .cache_datos -type f -printf '%p %s %T@\n' | sort | sha256sum`) igual a la línea base de la sesión; grep de que `opciones/backtest.py` y `calibration.py` no importan `datos`, `streamlit` ni pandas; `git diff -- tests/test_app_smoke.py` solo la aserción de pestañas; sin servidores arrancados.
- [ ] Entregar la [checklist manual](#checklist-manual-para-el-usuario) y dejar los bloques en `🔨 CODE DONE` hasta la confirmación del usuario.

## Verification Evidence

| Gate / Scenario | Strategy | Proves SPEC criterion |
|---|---|---|
| `.venv/bin/pytest tests/test_datos_history_types.py tests/test_datos_yahoo_history.py tests/test_datos_history_service.py -q` (Fake determinista, vacío → error español, sin red, 429) | Fully-Automated | AC-C2-1 |
| `.venv/bin/pytest tests/test_datos_history_service.py -q` (`clean_history`: fila de hoy, NaN/≤0, duplicados, orden, dividendos) | Fully-Automated | AC-C2-2 |
| `.venv/bin/pytest tests/test_datos_history_cache.py tests/test_datos_history_service.py -q` (escribe/lee, caducada → redescarga, **fresca y que cubre → 0 llamadas; menos años → reutiliza; más años → redescarga; `covers` con tolerancia de 7 días; inicio pedido = `today − (years + 1)` años naturales, ^IRX mismo tramo**, sin red usa caché, sin caché error) + `git check-ignore .cache_datos/history/x.json` | Fully-Automated | AC-C2-3 |
| `.venv/bin/pytest tests/test_backtest_helpers.py tests/test_datos_history_service.py tests/test_app_backtest.py -q` (aviso de histórico corto con años reales; fuente corta sin redescarga ni falso "no cubre"; **"Calcular" con histórico que no cubre `años + 1` → `st.warning` y sin cálculo**) | Fully-Automated | AC-C2-4 |
| `.venv/bin/pytest tests/test_backtest_helpers.py tests/test_backtest.py -q` (vol a mano, sin mirar el futuro) | Fully-Automated | AC-C2-5 |
| `.venv/bin/pytest tests/test_backtest_helpers.py tests/test_backtest.py -q` (vencimiento ≤ t+H, muestreo, cola/arranque) | Fully-Automated | AC-C2-6 |
| `.venv/bin/pytest tests/test_backtest.py -q` (BS forzado, `build_legs`, inválida saltada, ganar con/sin comisiones) | Fully-Automated | AC-C2-7 |
| `.venv/bin/pytest tests/test_backtest_helpers.py tests/test_datos_history_service.py -q` (r % → fracción, respaldo constante, q 12 meses, índice 0) | Fully-Automated | AC-C2-8 |
| `.venv/bin/pytest tests/test_calibration.py -q` (deciles, Wilson, vacío/pocos) | Fully-Automated | AC-C2-9 |
| `.venv/bin/pytest tests/test_backtest.py tests/test_calibration.py -q` (oráculos GBM y regímenes, Brier) | Fully-Automated | AC-C2-10 |
| `.venv/bin/pytest tests/test_backtest.py tests/test_calibration.py -q` (oráculo de saltos) | Fully-Automated | AC-C2-11 |
| `.venv/bin/pytest tests/test_calibration.py tests/test_backtest.py tests/test_app_backtest.py -q` (N efectivo, aviso, μ sin futuro) | Fully-Automated | AC-C2-12 |
| `.venv/bin/pytest tests/test_app_backtest.py tests/test_app_smoke.py -q` (pestaña, sin botón no calcula, entrada manual, caption "cambiar a más años obliga a volver a descargar") | Fully-Automated | AC-C2-13 |
| `.venv/bin/pytest tests/test_app_backtest.py -q` (resultados, avisos, caché de sesión, aviso de cobertura al subir años) + checklist manual 2–6 | Hybrid | AC-C2-14 |
| `.venv/bin/pytest tests/test_backtest.py -q -k tiempo` (10 años, paso 5 < 5 s; μ < 10 s) + checklist manual 2 (sensación de espera) | Hybrid | AC-C2-15 |
| `.venv/bin/pytest tests/test_datos_isolation.py -q` + `git diff --stat -- opciones/` + `HistoryProvider` intercambiable + revisión de diff | Hybrid | AC-C2-16 |
| `.venv/bin/pytest -q` completo (red bloqueada) + `unshare -rn .venv/bin/pytest -q` + `git diff --stat -- requirements.txt` vacío + `tests/test_datos_live.py` omitidas | Fully-Automated | AC-C2-17 |

**Qué demuestra y qué NO demuestra (known gaps, residual):**
- Los oráculos prueban que el motor está **bien calculado** (calibra con GBM, detecta colas con saltos), no que el mercado real se comporte así: eso es lo que el usuario verá en la pestaña (C2-G7: resultado dependiente del periodo).
- No se prueba contra Yahoo real en la suite (C2-G5): disponibilidad de `^GSPC`/`^SPX`/`^IRX` y el formato del histórico solo los cubre la prueba en vivo opcional.
- AppTest no prueba lo visual (aspecto de los gráficos, barras de error) ni la persistencia entre pestañas perezosas en navegador real (C2-G8): **Known-Gap, no apto para PASS por sí solo en los Hybrid AC-C2-14, AC-C2-15 y AC-C2-16**; quedan condicionados a la checklist manual.
- Tiempo: AC-C2-15 mide solo el motor, no el navegador; con paso 1 la espera es ≈ 5× mayor (C2-G9: el caption "≈ N fechas, ~X s" avisa).
- Sesgo de IP-4 (days = H frente a la fecha real de vencimiento) y de IP-1 (Wilson con deff) son aproximaciones documentadas, no verificadas contra una referencia externa.

## Matriz de trazabilidad AC-C2-1..AC-C2-17

| AC | Bloque(s) | Archivo(s) de test |
|---|---|---|
| AC-C2-1 | 4, 6, 7 | `tests/test_datos_history_types.py`, `tests/test_datos_history_service.py`, `tests/test_datos_yahoo_history.py` |
| AC-C2-2 | 6 | `tests/test_datos_history_service.py` |
| AC-C2-3 | 5, 6, 9 | `tests/test_datos_history_cache.py`, `tests/test_datos_history_service.py`, `tests/test_app_backtest.py` |
| AC-C2-4 | 2, 6, 9, 10 | `tests/test_backtest_helpers.py`, `tests/test_datos_history_service.py`, `tests/test_app_backtest.py` |
| AC-C2-5 | 2, 3 | `tests/test_backtest_helpers.py`, `tests/test_backtest.py` |
| AC-C2-6 | 2, 3 | `tests/test_backtest_helpers.py`, `tests/test_backtest.py` |
| AC-C2-7 | 3 | `tests/test_backtest.py` |
| AC-C2-8 | 2, 6 | `tests/test_backtest_helpers.py`, `tests/test_datos_history_service.py` |
| AC-C2-9 | 1 | `tests/test_calibration.py` |
| AC-C2-10 | 1, 3 | `tests/test_calibration.py`, `tests/test_backtest.py` |
| AC-C2-11 | 1, 3 | `tests/test_calibration.py`, `tests/test_backtest.py` |
| AC-C2-12 | 1, 2, 3, 10 | `tests/test_calibration.py`, `tests/test_backtest_helpers.py`, `tests/test_backtest.py`, `tests/test_app_backtest.py` |
| AC-C2-13 | 9 | `tests/test_app_backtest.py`, `tests/test_app_smoke.py` |
| AC-C2-14 | 10 | `tests/test_app_backtest.py` + checklist manual |
| AC-C2-15 | 3, cierre | `tests/test_backtest.py` (`-k tiempo`) |
| AC-C2-16 | 4, 8, cierre | `tests/test_datos_isolation.py`, `tests/test_datos_history_types.py` + `git diff --stat -- opciones/` |
| AC-C2-17 | 7, 8, cierre | `tests/test_datos_live.py` (omitidos), suite completa, `unshare -rn`, `git diff --stat -- requirements.txt` |

## Checklist manual para el usuario

Arranque: `.venv/bin/streamlit run app.py --server.port 8502` (**nunca 8501**; detener el servidor al terminar; reiniciarlo tras cualquier cambio de código).

1. Pestaña "Backtest" visible como 4.ª junto a Catálogo / Constructor / Ajustes; con "Entrada manual" muestra el mensaje de elegir un ticker de la lista y nada se descarga.
2. Elegir SPY → "Cargar histórico": aparece el texto de antigüedad y, la segunda vez, se usa la caché (sin esperar); abrir la pestaña no dispara nada por sí solo. Junto al control de años se lee que cambiar a más años obliga a volver a descargar: subir de 10 a 15 años, pulsar "Calcular" → aviso «pulsa "Cargar histórico"»; tras cargar de nuevo calcula; bajar a 5 años reutiliza la caché sin descargar.
3. "Calcular" con iron condor, H = 30, W = 30, paso 5, 10 años: tarda unos segundos y muestra el gráfico de fiabilidad con la diagonal y los puntos con barras de error; los tramos con pocos casos se ven grises y huecos.
4. Tabla por tramo (10 filas), Brier, N y N efectivo visibles y legibles (sin texto cortado); aviso de solapamiento junto a N efectivo.
5. Histograma de colas con la curva normal, curtosis y tabla de cuantiles; texto "colas gordas del modelo + ruido de volatilidad".
6. Avisos fijos presentes: volatilidad realizada ≠ implícita; americanas como europeas; q aproximado; "no rentabilidad real"; "estudio, no asesoría".
7. Cambiar un parámetro (p. ej. H) oculta el resultado con "los parámetros cambiaron: pulsa Calcular"; con la línea μ activada aparece una segunda serie en el gráfico.
8. Cambiar de ticker (SPY → QQQ) o de tipo borra el histórico y el resultado; cambiar de pestaña y volver conserva los controles y el resultado; sin internet (con caché) se calcula y se ve la antigüedad; con SPX confirmar qué símbolo respondió (^GSPC o ^SPX) y con un ticker sin ^IRX confirmar el aviso de tasa constante.

## Risk Predictions

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| R1 | **Yahoo no devuelve histórico de `^GSPC`/`^SPX`/`^IRX` o cambia el formato** | Media | Respaldos definidos (SPX prueba dos símbolos; r constante con aviso); mensajes específicos; prueba en vivo opcional (bloque 7); proveedor intercambiable |
| R2 | **Límite de solicitudes (429)** | Baja | 1 solicitud por ticker (+1 para ^IRX); caché fresca **que cubre** sin red (subir los años obliga a una nueva descarga: asumido por el usuario, avisado en un caption); `MSG_RATE_LIMIT`; sin reintentos en bucle |
| R3 | **Mirar el futuro por descuido** (vol, μ, q, r o dividendos con datos posteriores a t) | Media | Tests de "futuro" que alteran todo lo posterior a t y exigen resultado idéntico; `searchsorted` con `side="right"`; revisión del bucle |
| R4 | **Oráculos estadísticos frágiles** (falsos rojos por azar o series demasiado cortas) | Media | Semillas fijas, series de ≥ 40 años sintéticos, tolerancias propuestas y **medidas** (IP-9), regímenes para llenar deciles; si un valor medido está cerca de la cota se ensancha con justificación escrita |
| R5 | **Tiempo del backtest** (paso 1 → 5× más; 2,8 ms/fecha) | Media | Caption "≈ N fechas, ~X s" y spinner; cotas holgadas (5 s/10 s); paso mínimo documentado |
| R6 | **AppTest ejecuta todas las pestañas** y dispararía descarga/cálculo al abrir (o construiría `YahooProvider` en cada rerun) | Alta si se descuida | Todo con `if st.button`; `render_backtest` recibe un callable `get_provider` invocado solo en el botón; test de "sin botón: 0 llamadas y `YahooProvider` no construido"; proveedor falso cuenta llamadas |
| R7 | **Pestañas perezosas pierden el valor de los widgets** | Media | Patrón de Ajustes (IP-6); checklist manual ítem 8 |
| R8 | **`FakeProvider`/`__init__` compartidos rompen tests de C1** | Baja | Solo se añaden métodos; el bloque 4 corre los tests de C1 explícitamente |
| R9 | **`import datos` carga pandas/yfinance** o el motor importa `datos`/streamlit | Baja | Bloque 8 en subproceso; `yahoo.py` sin pandas a nivel de módulo |
| R10 | **Sesgos aceptados**: vol realizada ≠ implícita, americanas como europeas, q aproximado, days = H, deff aproximado | Alta (conocidos) | Avisos fijos (C2-G2/G4); documentados en IP-1/IP-4; no se presentan como rentabilidad |
| R11 | **Cifras de referencia copiadas de un prototipo con otras entradas** | Media | Recalcular con las entradas exactas de cada test y anotar valor y tolerancia (lección A/B1/C1) |
| R12 | **Caché corrupta o de otro esquema** rompe la pestaña | Baja | Lectura defensiva → `None`; escritura atómica; versión de esquema |
| R13 | **Tests que tocan el `.cache_datos/` real del usuario** | Baja | `cache_dir=tmp_path` obligatorio (también para el caché tz de `YahooProvider`); huella `find .cache_datos -type f -printf '%p %s %T@\n' | sort | sha256sum` registrada antes del bloque 5 y re-comprobada tras los bloques 5, 6, 9, 10 y el cierre (`git status` no sirve: el directorio está ignorado); re-baseline al inicio de cada sesión de EXECUTE (el uso normal de la app puede cambiarlo); nunca borrar ni modificar archivos del usuario |
| R14 | **Streamlit conserva imports obsoletos** tras editar `datos/` o `opciones/` | Alta | Reiniciar el servidor manual (puerto ≠ 8501) tras cada cambio |
| R15 | **Resultado dependiente del periodo** (p. ej. 10 años alcistas) | Alta (inherente) | Se muestra el rango de fechas usado; no se generaliza (C2-G7) |
| R16 | **Cobertura de caché mal calculada** (descarga en bucle con fuentes cortas, o calcular con datos que no cubren; año bisiesto; inicio en fin de semana) | Media | `covers` con tolerancia de 7 días y `requested_start` (IP-10); aritmética de años naturales en un único helper `start_for_years` con prueba de 29-feb; comprobación de cobertura en "Calcular" (IP-11) con tests de subir/bajar años y de fuente corta |
| R17 | **Una descarga caducada con menos años sobrescribe una caché más larga** (se pierde cobertura ya descargada) | Baja | Aceptado: se vuelve a descargar solo el tramo pedido; subir de nuevo los años vuelve a descargar (avisado por el caption); no se fusionan cachés |

## Out of Scope

Replay de la estrategia / P&L histórico y cualquier afirmación de rentabilidad real; histórico de precios de opciones (C3); comparación de volatilidad realizada con VIX; varios tickers a la vez, optimización de parámetros, recomendación de estrategias; binomial en el backtest, dividendos discretos, superficie de volatilidad; tickers fuera de la lista curada, datos intradía o en tiempo real; cambios en los módulos existentes del motor, en Monte Carlo o en métricas; operar, órdenes, bróker; asesoría de inversión; comisión de cierre racional (B2); barra de progreso real durante el cálculo.

## Dependencies

- **Nuevas:** ninguna (`requirements.txt` sin cambios; `scipy.stats` ya instalado).
- **Existentes:** numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0, yfinance 1.8.0, pandas 3.1.1.
- **Orden:** 3 ← 1, 2; 5 ← 4; 6 ← 4, 5; 7 ← 4; 8 ← 1–7; 9 y 10 ← todos (9 antes que 10; ambos tocan `ui_backtest.py` y `tests/test_app_backtest.py`).
- **Red:** solo la corrida en vivo opcional del bloque 7 (puede requerir aprobación del usuario fuera del sandbox).

## Test Infra Improvement Notes

(none identified yet)

## Resume and Execution Handoff

1. **Plan file:** `process/general-plans/active/etapa-c2-historico-backtest_21-11-26/etapa-c2-historico-backtest_PLAN_21-11-26.md` (execute-anchor).
2. **Last completed phase/step:** PLAN escrito (21-11-26); ningún bloque ejecutado (0/10 bloques + cierre); SPEC bloqueado y decisiones de INNOVATE concretadas arriba (PD-1..PD-14, IP-1..IP-11). Cambio del usuario 21-11-26: desviación (i) rechazada y sustituida por descarga `años + 1` con caché que reutiliza solo si cubre el tramo (PD-14, IP-10, IP-11).
3. **Validate-contract status:** PASS (re-validación ciclo 3, 21-11-26; suplemento S-1..S-3 aplicado y verificado: W acotado a 10–250, `HistoryLoad.requested_start: date | None`); listo para EXECUTE. E-7 y E-8 siguen accesibles desde el contrato.
4. **Supporting context files loaded:** SPEC de C2; plan de C1 (plantilla estructural); `process/context/all-context.md`; `process/context/tests/all-tests.md`; `opciones/{simulation,catalog,payoff,models,metrics,validation,__init__}.py`; `datos/*.py`; `app.py`; `tests/conftest.py`, `tests/test_app_smoke.py` (`data_app`), `tests/test_datos_isolation.py`, `tests/test_datos_live.py`.
5. **Next step for a fresh agent:** tras la re-validación y el aviso al usuario sobre las desviaciones (ii)–(v) y el reemplazo de (i), ejecutar el **Bloque 1** (TDD: `tests/test_calibration.py` en rojo → `opciones/calibration.py`), gate `.venv/bin/pytest tests/test_calibration.py -q` y luego `.venv/bin/pytest -q`; no empezar un bloque con el anterior en rojo; commit en `main` por bloque; marcar `CODE DONE`, nunca `VERIFIED` sin confirmación del usuario.

**Instrucciones para el agente de EXECUTE (vinculantes):**
1. Orden 1 → 10 → cierre; cada bloque cierra con su gate y `.venv/bin/pytest -q` completo; commit por bloque directamente en `main` (sin rama), con la atribución exigida por el entorno.
2. TDD: tests primero (rojo), luego implementación; código simple (el usuario es principiante), identificadores en inglés, comentarios y docstrings en español.
3. Los agentes de EXECUTE no escriben bajo `process/`: devolver estados, cifras medidas, tiempos y texto de contexto en el mensaje final.
4. No modificar `opciones/` existente ni `datos/cache.py`, `service.py`, `filters.py`, `errors.py`; de los tests existentes solo cambia la aserción de la línea 65 de `tests/test_app_smoke.py` y se amplían `test_datos_isolation.py` y `test_datos_live.py`; nunca cambiar números esperados.
5. Nunca tocar el `.cache_datos/` real (comprobación por huella, no por `git status`; re-baseline al inicio de cada sesión) ni el puerto 8501; servidores manuales en 8502+ y detenidos al terminar.
6. `format_func` sin `session_state` ni reloj; widgets solo desde callbacks; `st.metric` solo para números; AppTest no vacía `number_input`.
7. Recalcular cifras de referencia con las entradas exactas y anotarlas; los oráculos usan semillas fijas.
8. Sin red en la suite normal; red real solo con `LIVE_DATA=1` a propósito.
9. **Proveedor perezoso (C-V1):** `main()` no llama `data_provider()` en cada rerun; pasa el callable a `render_backtest`, que lo invoca solo en el botón. Test: sin botón, `YahooProvider` no se construye.
10. **Oráculos (C-V2):** medir cada oráculo con las entradas exactas, usar las cotas validadas del bloque 3 y ensanchar cualquiera a menos del 25 % del valor medido, anotando valores medidos en el informe.
11. **Huella de caché (C-V3):** registrar y comparar `find .cache_datos -type f -printf '%p %s %T@\n' | sort | sha256sum` antes del bloque 5 y tras 5, 6, 9, 10 y cierre; re-baseline al inicio de cada sesión de EXECUTE; nunca borrar ni modificar archivos del usuario.
12. **FakeProvider (C-V4):** solo añadidos (`history_empty_symbols`, `history_fail_symbols`, `history_years`) con defaults que preservan el comportamiento.
13. **Pestaña por defecto:** sin gráfico, sin `st.warning` y sin `st.error` (los smoke existentes cuentan gráficos plotly y exigen `not app.warning` hacia la línea 699 de `tests/test_app_smoke.py`).
14. EVL: un vc-tester independiente vuelve a ejecutar cada comando de gate de este plan.
15. **Descarga por años (cambio del usuario 21-11-26):** `load_history(provider, label, years, ...)` pide `start = start_for_years(today, years)` (`years + 1` años naturales, nunca `× 365 días`) también para ^IRX; reutiliza la caché solo si es fresca **y** `covers(...)` (tolerancia 7 días; `requested_start` guardado); "Calcular" comprueba cobertura (`MSG_BT_NOT_COVERED`) y no calcula si falta; caption `MSG_BT_YEARS_CAPTION` junto al control de años. No existe ya ninguna descarga "fija de 16 años": ningún test ni código debe suponerla.

## Validate Contract

Status: PASS
Date: 21-11-26
date: 2026-11-21
generated-by: outer-pvl
Note: re-validation cycle 3 (from V1) after supplement S-1..S-3 of the cycle-2 CONDITIONAL. Supersedes the cycle-2 CONDITIONAL contract and the cycle-1 PASS contract. Years+1 download rule (PD-14, IP-10, IP-11, R16, R17), C-V1..C-V4 and E-1..E-7 re-verified intact.

Parallel strategy: sequential
Rationale: 10 blocks + closeout in one flow; blocks 1-3 and 4-7 are independent chains but are serialised to keep failures isolated; blocks 9 and 10 share `app.py`, `ui_backtest.py` and `tests/test_app_backtest.py`; no concurrent file ownership possible. Executor opus, tester/validators sonnet. Fan-out dimension checks were run inline by the validate agent (no sub-agents spawned).

### V1-V3 result (21-11-26, re-validation cycle 3)
- Structural validator (`validate-plan-artifact.mjs`): run after this edit (see footer). Paths and signatures verified in cycle 1 are untouched (plan-only edits since).
- **S-1 verified applied.** PD-14 now reads "`years + 1` años naturales ≈ 249-252 sesiones ... con `bt_window` acotado a 10-250 el análisis empieza a 0-3 sesiones de lo pedido, desfase que absorbe la tolerancia de IP-3". Public Contracts (`session_state` keys): `bt_window` (30; `st.number_input` entero, rango 10-250 sesiones). Block 9 test lists "W 10-250 entero, por defecto 30 (min/max/defecto; S-1)". Block 3 oracles use W = 30/60 (inside the range). The SPEC states no conflicting W range (only "por defecto 30").
- **S-2 verified applied.** Public Contracts `HistoryLoad(..., requested_start)` with `requested_start: date | None`; IP-11 says Calcular passes it unchanged to `covers`, which ignores `None`; Block 6 has the test "sin red + caché vieja sin `requested_start` -> `HistoryLoad.requested_start is None`, sin excepción, y `covers` aplica el criterio del primer dato (S-2)". Consistent with IP-10 and `read_history -> (..., requested_start | None)`.
- **S-3 verified.** Resume item 3 and `## Next Step` previously claimed re-validation pending; both rewritten in this pass to state the PASS contract (E-7 reachable from the handoff).
- **Regression sweep: none.** Years+1 rule consistent across PD-14, IP-10/11, Desviación (i), Alternatives, Arquitectura, Public Contracts, Blocks 4-6 and 9-10, Verification Evidence, traceability (AC-C2-3 -> 5, 6, 9; AC-C2-4 -> 2, 6, 9, 10), R2/R16/R17, Resume item 15. "16 años" appears only in the rejected-deviation strikethrough, the rejected alternative, the PD-14 "sustituye" clause, Resume item 15's "no existe ya" sentence and this contract's notes. AC-C2-1..17 all mapped to blocks and test files. Skipped count 4 (3 + 1 live test) consistent in desviación (v), AC-C2-17, Block 7, closeout and gates; baseline 2742 passed, 3 skipped unchanged. Offline (`unshare -rn`), real-cache fingerprint (Blocks 5, 6, 9, 10, closeout), lazy-provider (C-V1), oracle tolerances (C-V2/E-3), FakeProvider knobs (C-V4), AppTest rules (`format_func`, widget callbacks, default tab without warning/error/chart) unchanged. No deadlock or download loop between AC-C2-4 and the Calcular coverage warning (traced in cycle 2, unchanged).

### Dimension findings
- Infra fit: PASS - provider construction lazy; one request per symbol (+^IRX); fingerprint and offline suite unchanged.
- Test coverage: PASS - covers/start_for_years/reuse/refetch/coverage warning/short source/W range/`requested_start = None` all have Fully-Automated tests (Blocks 5, 6, 9, 10); AppTest visual limits stay as documented Known-Gaps.
- Breaking changes: PASS - `datos/cache.py`, `service.py`, existing `opciones/` modules, `requirements.txt` untouched; only existing-test edit is the line-65 tab list; skipped 3 -> 4.
- Security surface: PASS - no auth/billing/PII; symbols from a fixed table; defensive cache reads, atomic writes.
- Section feasibility: Blocks 1-10 and closeout PASS.

### Test gates (run from repo root; every block ends with the full `.venv/bin/pytest -q`; baseline 2742 passed, 3 skipped)

| criterion id | behavior | strategy | proving test | gap-resolution |
|---|---|---|---|---|
| AC-C2-9, 10p, 11p, 12p | Block 1: Wilson, Brier, 10 deciles, effective N, tail diagnostics | Fully-Automated | `.venv/bin/pytest tests/test_calibration.py -q`; `git diff --stat -- opciones/` (only new `calibration.py`) | B |
| AC-C2-5p, 6p, 8p, 12p | Block 2: realized vol, trailing mu, q, rate_at, expiry_index, first_analyzed_index | Fully-Automated | `.venv/bin/pytest tests/test_backtest_helpers.py -q` | B |
| AC-C2-5, 6, 7, 10, 11, 12, 15 | Block 3: `run_backtest`, oracles, no look-ahead, timing | Fully-Automated | `.venv/bin/pytest tests/test_backtest.py tests/test_backtest_helpers.py tests/test_calibration.py -q`; `.venv/bin/pytest tests/test_backtest.py -q -k tiempo` (test names containing "tiempo") | B |
| AC-C2-1p, 16p | Block 4: `PriceHistory`, `HistoryProvider`, `FakeProvider.get_history` (+ knobs, `history_calls`), symbol map | Fully-Automated | `.venv/bin/pytest tests/test_datos_history_types.py tests/test_datos_types.py tests/test_datos_service.py tests/test_datos_tickers.py -q` | B |
| AC-C2-3p | Block 5: history cache, freshness, atomic write, `requested_start`, `covers`, `start_for_years` | Fully-Automated | `.venv/bin/pytest tests/test_datos_history_cache.py tests/test_datos_cache.py -q`; real-cache fingerprint equal before/after | B |
| AC-C2-1, 2, 3, 4, 8p | Block 6: clean_history, `load_history(years)` (years+1 span, ^IRX same span, fresh+covers = 0 calls, fewer years reuses, more years refetches, short source no loop, `requested_start = None` fallback), ^GSPC/^SPX fallback, ^IRX % -> fraction | Fully-Automated | `.venv/bin/pytest tests/test_datos_history_service.py tests/test_datos_history_cache.py tests/test_datos_history_types.py -q`; fingerprint equal | B |
| AC-C2-1, 17p | Block 7: Yahoo adapter with simulated client; live test opt-in | Fully-Automated | `.venv/bin/pytest tests/test_datos_yahoo_history.py tests/test_datos_yahoo.py tests/test_datos_live.py -q`; `.venv/bin/pytest -q` -> N passed, 4 skipped | B |
| AC-C2-16, 17p | Block 8: import isolation, requirements unchanged | Fully-Automated | `.venv/bin/pytest tests/test_datos_isolation.py -q`; `git diff --stat -- opciones/ requirements.txt` | B |
| AC-C2-3p, 4, 13 | Block 9: tab, controls (W 10-250 range test), years caption, "Cargar histórico" (`today-(years+1)` request, reuse on fewer years), manual entry, ticker-change clearing, lazy provider | Hybrid | `.venv/bin/pytest tests/test_app_backtest.py tests/test_app_smoke.py -q`; fingerprint equal; manual checklist 1, 2, 8 | B |
| AC-C2-4, 12, 14 | Block 10: "Calcular" (coverage check -> `MSG_BT_NOT_COVERED` without computing; short source shows short-history warning only), figures, table, notices, session cache | Hybrid | `.venv/bin/pytest tests/test_app_backtest.py tests/test_app_smoke.py -q`; fingerprint equal; manual checklist 2-7 | B |
| AC-C2-15, 16, 17 | Closeout: full suite offline, engine diff, deps diff | Fully-Automated | `.venv/bin/pytest -q` -> 2742 + new passed, 4 skipped; `unshare -rn .venv/bin/pytest -q`; `git diff --stat -- opciones/ requirements.txt tests/test_app_smoke.py`; fingerprint equal | B |
| C2-G5 | Yahoo still returns ^GSPC/^SPX/^IRX history | Hybrid | `LIVE_DATA=1 .venv/bin/pytest tests/test_datos_live.py -q -s` (network, optional, may be denied) | D |

Failing stubs: each Fully-Automated row starts as the plan's own "en rojo" test step (block checklists).

### Execute-agent instructions (binding)
The 15 numbered instructions in the plan's `## Resume and Execution Handoff` (order 1 -> 10 -> closeout; TDD; no writes under `process/`; no edits to existing `opciones/`/`datos/cache.py`/`service.py`/`filters.py`/`errors.py`/`requirements.txt`/`tests/conftest.py`; real-cache fingerprint; port 8501 off-limits; `format_func`/widget-state rules; oracles measured with fixed seeds; lazy provider; FakeProvider additions only; default tab emits no warning/error/chart; EVL by an independent vc-tester; item 15 years+1 download with coverage-checked reuse) are binding as written. Additions from this validation:
- E-1. Commit per block directly on `main` with conventional message; final state `CODE DONE`, never `VERIFIED`; run the full `.venv/bin/pytest -q` before starting the next block.
- E-2. Lazy-provider test: `data_provider()` wraps construction in `except Exception`, so a patch that merely raises is swallowed. Patch `datos.yahoo.YahooProvider` with a spy class that records instantiation in a list (and may also raise) and assert the list is empty without a button press, in the bare `app` fixture and in `data_app`. `render_backtest` must also handle `get_provider()` returning `None` (message only after pressing "Cargar histórico").
- E-3. Oracle regimes: use the 504-session, W = 30 form with seeds 1-2 as primary (measured margins >= 40 %); do not use 126-session blocks with W = 60 unless re-measured (measured: seed 2 max dev 0.168 > 0.15 and skill 0.027 < 0.03). Record measured values; widen any bound within 25 % of its measured value with a written reason.
- E-4. Fingerprint: `find .cache_datos -type f -printf '%p %s %T@\n' | sort | sha256sum` (verified stable across the full existing suite); re-baseline at the start of each EXECUTE session and immediately before each comparison if a user Streamlit server is running; if the hash changes, diff the file listing to see whether a test or the user caused it; never delete or modify user files.
- E-5. `FakeProvider` additions must include a history call log (e.g. `history_calls`: symbol, start, end) used by Block 6/9 tests (per-symbol call counts; the `years + 1` calendar-year `start` and `end = today + 1 day` for years = 1, 5, 15 and 29-Feb; ^IRX with the same span; 0 calls without a button). No test or code may assume a fixed 16-year request.
- E-6. Dates in tests use the injected clock (`FIXED_NOW` = Friday 2026-11-20 10:30 America/New_York); "tiempo" tests keep names containing `tiempo` so `-k tiempo` selects them. Block 7's live function is a second `skipif(LIVE_DATA != "1")` test (skipped count 4); if the optional live run is denied, mark `CODE DONE` with "live run pending".
- E-7. Coverage tests must use the same injected clock on both sides (Load and Calcular) and compute `need_start` only through `start_for_years`; a test must cover Calcular one day after Load without reload (still covered) and the same-day equality case.
- E-8 (advisory note, non-gating). In markdown tables, an unescaped pipe inside `` `requested_start: date | None` `` (IP-11 row and the `history_service` row of Public Contracts) can split the table cell when rendered; write `date \| None` there if the plan is ever re-rendered. Cosmetic only; the text is unambiguous when read raw and the structural validator is unaffected.

### What this coverage does NOT prove
- Oracles prove the engine is computed correctly on synthetic worlds, not that real markets behave that way (C2-G7: period-dependent result).
- Yahoo availability/format of `^GSPC`, `^SPX`, `^IRX` history is covered only by the optional live run (C2-G5); that Yahoo honours `start` for the narrower years+1 window is assumed from `Ticker.history` semantics.
- AppTest cannot check visual look of the charts/error bars, truncation, or lazy-tab persistence in a real browser (C2-G8): Hybrid AC-C2-14, 15, 16 stay conditional on the manual checklist.
- Timing covers the engine only (0.65 s / 1.05 s for 450 dates), not the browser; step 1 is ~5x slower (C2-G9: the caption warns).
- IP-1 (Wilson with deff) and IP-4 (days = H) are documented approximations with no external reference.
- `is_fresh` uses weekday-only logic (no market holidays): after a holiday the cache may be considered stale and trigger one extra download; harmless. The 1-calendar-year warm-up is 249-252 sessions; with W <= 250 the shortfall (<= 3 sessions) is absorbed by the IP-3 tolerance.
- Oracle bounds are seed-dependent (see E-3).
- R17 (a stale-cache refetch with fewer years overwrites a longer cache) is accepted by the user's rule, not tested beyond the "more years refetches" case.

### Known gaps
C2-G5, C2-G7, C2-G8, C2-G9 (documented residuals, gap-resolution D); optional live run pending user/network approval. S-1 and S-2 are closed.

Gate: PASS
Accepted by: n/a (no concerns outstanding)

**Status:** DONE
**Summary:** Re-validation cycle 3: S-1 (W 10-250, PD-14 249-252 sessions, Block 9 range test), S-2 (`requested_start: date | None`, Block 6 test) and S-3 (Resume item 3 / Next Step) verified applied; no regression in C-V1..C-V4, years+1 rule, E-1..E-7, AC traceability, gates, skipped count 4, offline/fingerprint/AppTest rules. Whole-plan sweep consistent.
**Concerns/Blockers:** none; one cosmetic note E-8 (unescaped pipe in two table cells).

## Lessons Learned and Deviations (UPDATE PROCESS)

(vacío hasta el cierre; lo rellena UPDATE PROCESS)

## Next Step

Mostrar al usuario las desviaciones (ii)–(v) (la (i) fue sustituida por su regla); después ENTER EXECUTE MODE con el Bloque 1 (contrato de validación: PASS, ciclo 3). RIPER-5: PLAN → VALIDATE → EXECUTE.

PHASE_COMPLETE: PLAN

**Status:** DONE
**Summary:** Plan COMPLEX de C2 escrito (10 bloques + cierre, AC-C2-1..17 mapeados, gates por bloque, checklist manual de 8 ítems, riesgos, handoff).
**Concerns/Blockers:** ninguno bloqueante; 2 desviaciones nuevas a confirmar con el usuario (aserción de pestañas en `test_app_smoke.py` línea 65; omitidos pasan de 3 a 4).
