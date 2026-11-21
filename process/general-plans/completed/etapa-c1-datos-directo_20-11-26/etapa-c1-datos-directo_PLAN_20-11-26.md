---
name: etapa-c1-datos-directo PLAN
description: "Plan COMPLEX de la Etapa C1 (datos de mercado en directo de Yahoo Finance, solo opciones líquidas, con caché local) de Laboratorio de Opciones, en 7 bloques secuenciales cada uno cerrado con pytest verde."
date: 20-11-26
status: completed
complexity: complex
spec: process/general-plans/completed/etapa-c1-datos-directo_20-11-26/etapa-c1-datos-directo_SPEC_20-11-26.md
---

# Plan: Etapa C1 — Datos de mercado en directo en el constructor

**Date**: 20-11-26
**Complexity**: COMPLEX (un solo plan, un solo flujo de ejecución, 7 bloques secuenciales; no es phase program)
**Status**: ⏳ PLANNED (PLAN escrito 20-11-26; ningún bloque ejecutado)
**SPEC bloqueado**: `process/general-plans/completed/etapa-c1-datos-directo_20-11-26/etapa-c1-datos-directo_SPEC_20-11-26.md` (AC-C1-1..AC-C1-16, decisiones C1–C9, huecos C-G1..C-G10; valores propuestos ya aprobados por el usuario)
**Entorno**: Python 3.12.3, `.venv` (numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0, pandas 3.1.1 ya presente por Streamlit); línea base: `.venv/bin/pytest -q` → **2330 passed, 2 skipped** (HEAD c31c356, rama main; sin cambios sin confirmar salvo esta carpeta de tarea con el SPEC)

**TL;DR:** un paquete nuevo de nivel superior `datos/` (fuera del motor `opciones/`, que no cambia) trae precio, tasa y dividend yield de Yahoo Finance (`yfinance==1.8.0`) detrás de una interfaz de proveedor intercambiable, filtra la cadena a **solo opciones líquidas** con reglas en un único lugar, y guarda cada carga en una caché local ignorada por git. `app.py` gana una cascada Tipo → Ticker → "Cargar datos" → Vencimiento, un selector de patas reales (prima = mid, IV del motor, IV de Yahoo solo como referencia) y un texto de antigüedad. La suite normal **no usa red** (bloqueo automático en `conftest.py`); una prueba en vivo opcional se activa con `LIVE_DATA=1`. Cada bloque cierra con `.venv/bin/pytest -q` completo en verde.

**Clasificación de complejidad (mi decisión):** COMPLEX estándar: hay un paquete nuevo (7 módulos), dependencias externas, caché, interfaz y tests de red; pero los 7 bloques son secuenciales (cada uno usa los tipos y filtros del anterior; los bloques 5 y 6 comparten `app.py`) y caben honestamente en un solo archivo.

## Overview

La Etapa C1 conecta el constructor con datos reales: el usuario elige un subyacente de una **lista curada** (Índice SPX; ETF SPY, QQQ, IWM; Acción AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA), pulsa "Cargar datos" y la app rellena spot, r (letras a 13 semanas, `^IRX`) y q (rendimiento por dividendos anual reciente), y ofrece **solo vencimientos y strikes líquidos**. La prima de una pata elegida es el mid (bid+ask)/2; la IV se recalcula con el motor (Black-Scholes para Índice, binomial para Acción/ETF, según B1); la IV de Yahoo es solo referencia. Cada carga se guarda en `.cache_datos/` para usarla sin internet. Con "Entrada manual" (el valor por defecto) la app es exactamente la de antes.

Contexto leído: `process/context/all-context.md`, `process/context/tests/all-tests.md`, `process/development-protocols/plan-lifecycle.md`, `implementation-standards.md`, el SPEC, el plan de la Etapa B1 (formato), `app.py`, `opciones/__init__.py`, el layout de `tests/`, `requirements.txt`, `.gitignore` y los scripts de investigación `chains.json`, `probe.py`, `dump.py`, `cmp.py` del scratchpad (`.../scratchpad/stageC/`, solo referencia; no se copian tal cual).

## Quick Links

- [Decisiones bloqueadas](#decisiones-bloqueadas-c1c10) · [Chosen Approach](#chosen-approach-y-por-qué-este-camino) · [Arquitectura](#arquitectura) · [Phase Completion Rules](#phase-completion-rules)
- [Acceptance Criteria](#acceptance-criteria) · [Touchpoints](#touchpoints) · [Public Contracts](#public-contracts) · [Blast Radius](#blast-radius)
- [Implementation Checklist (bloques 1–7)](#implementation-checklist) · [Verification Evidence](#verification-evidence) · [Matriz de trazabilidad](#matriz-de-trazabilidad-ac-c1-1ac-c1-16)
- [Risk Predictions](#risk-predictions) · [Out of Scope](#out-of-scope) · [Test Infra Improvement Notes](#test-infra-improvement-notes) · [Resume and Execution Handoff](#resume-and-execution-handoff) · [Validate Contract](#validate-contract)

## Status strip

| Bloque | Contenido | Estado |
|---|---|---|
| 1 | Dependencias fijadas + `.gitignore` + `datos/` tipos, errores, interfaz de proveedor | ⏳ PLANNED |
| 2 | `datos/filters.py` (reglas, limpieza, de-duplicado) + tests de borde | ⏳ PLANNED |
| 3a | `tests/conftest.py` (bloqueo de red) + suite completa | ⏳ PLANNED |
| 3b | Fixtures (reales recortadas + sintéticas de borde) con cifras medidas | ⏳ PLANNED |
| 3c | `datos/cache.py` (`SPX.json`, regla parcial-vs-rico con helpers de comparación) + tests | ⏳ PLANNED |
| 3d | `datos/fake.py` (vencimientos relativos al reloj, `offsets` configurables) + `service.py` (reloj inyectable, usa la caché, parada en el primer 429) + tests | ⏳ PLANNED |
| 4 | `datos/yahoo.py` (adaptador: timeout, errores de conexión, directorio tz inyectable) + test de aislamiento + prueba en vivo opcional | ⏳ PLANNED |
| 5 | `datos/tickers.py` + cascada de la barra lateral + "Cargar datos" + texto de antigüedad | ⏳ PLANNED |
| 6 | Selector de patas reales, `premium_source`, IV de Yahoo como referencia, aviso de vencimiento | ⏳ PLANNED |
| 7 | Smoke AppTest, suite completa con red bloqueada y checklist manual | ⏳ PLANNED |

## Decisiones bloqueadas (C1–C10)

C1–C9 del SPEC (fuente Yahoo detrás de interfaz, dependencias fijadas, prima = mid, IV del motor, caché local, solo opciones líquidas, selección desde "Tipo de subyacente", r y q autorrellenados, paquete de nivel superior) siguen vigentes sin reescribirse. Se añade:

| # | Decisión |
|---|---|
| C10 | **Índice (SPX): "Cargar datos" deja el campo q como el usuario lo tenga escrito** y muestra una nota informativa: "sin dividend yield para índices: edítalo, SPX ≈ 1,2 %". (Resuelve el "q usa el valor manual por defecto y se avisa" de AC-C1-4 para índices: no se sobrescribe q.) |

Resoluciones de este plan (INNOVATE, 20-11-26; el usuario aprobó los valores propuestos del SPEC):

| Tema | Resolución |
|---|---|
| Lista curada | Índice: SPX→`^SPX`; ETF: SPY, QQQ, IWM; Acción: AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA. Solo estos; no hay campo libre de ticker. |
| Filtros (`LiquidityRules`, un solo lugar) | bid > 0, ask > 0, OI ≥ 100, spread (ask−bid)/mid ≤ 10 % o ≤ 0,10 USD absoluto si mid < 1, strike en ±20 % del spot, vencimiento 7–120 días naturales. |
| Limpieza vs liquidez | `clean_row` descarta por **calidad** (NaN/None/negativos/bid > ask/campos ausentes); `filter_chain` aplica **liquidez**. Strikes duplicados (kind, strike): se conserva uno. |
| q | De `trailingAnnualDividendYield` (fracción), **no** de `dividendYield` (porcentaje). Si `Ticker.info` falla: q no disponible + aviso, q = 0 en la app. |
| r | `^IRX` llega en porcentaje: `rate = valor/100`; la app guarda `rate_pct = round(rate*100, 2)`. |
| Spot | `fast_info` preferido; las llamadas se hacen solo en el adaptador. |
| Carga | Ansiosa: al cargar se trae la cadena de todos los vencimientos de la ventana 7–120 días; tolerante a fallos parciales (se cuenta cuántos fallaron y se avisa). |
| Caché | Un JSON por ticker en `.cache_datos/` (raíz del repo, ignorado por git), sin TTL; los filtros se **reaplican al leer** y los días se recalculan desde hoy. El nombre del archivo sale de la **etiqueta curada** (`SPX.json`, nunca `^SPX.json`). Un snapshot parcial **nunca** sustituye a uno más rico ya guardado (se compara nº de vencimientos y de cotizaciones; se conserva el más rico y se avisa al usuario). |
| Reloj | **Zona horaria (A3):** las fechas de mercado (`today`, días hasta el vencimiento) se calculan en `America/New_York` (`zoneinfo`); los textos "cargados a las HH:MM" / "guardados de DD/MM HH:MM" se muestran en la zona horaria local del sistema (`now.astimezone()`). `today`/`now` son inyectables (`session_state["clock"]` en la app, parámetro `today`/`now` en `service.py` y en la lectura de caché); `FakeProvider` construye sus vencimientos **relativos** a ese reloj, así que los tests de humo no caducan con el paso del tiempo (C-V2). |
| Tolerancia numérica | Las comparaciones de umbral usan una tolerancia `EPS = 1e-9` (`spread <= limit + EPS`, etc.) definida junto a `LiquidityRules` (C-V3). |
| Robustez de carga | Al primer `RateLimitError` se dejan de pedir cadenas y se conserva lo ya descargado; timeout explícito por solicitud; errores de conexión de `curl_cffi`/`requests` → `NetworkError`; el directorio de caché tz de yfinance es un parámetro del adaptador (C-V4). |
| Dependencias | `yfinance==1.8.0` y `pandas==3.1.1` fijados en `requirements.txt`; instalación en el `.venv` en el bloque 1 (necesita red). |
| Pruebas con red | Ninguna en la suite normal: bloqueo automático de red; prueba en vivo con `skipif(LIVE_DATA != "1")`. |

## Chosen Approach y por qué este camino

**Elegido:** paquete `datos/` plano y pequeño, con tipos inmutables y funciones puras (filtros, servicio, caché) separados del único módulo que toca `yfinance` (`yahoo.py`). El resto de la lógica depende solo del `Protocol` de proveedor, así que se prueba con un proveedor falso respaldado por fixtures grabadas, y cambiar de proveedor no toca motor ni interfaz.

**Alternativas descartadas:**
- *Meter el acceso a datos en `opciones/`*: rompe la pureza del motor (sin E/S, importable sin red) exigida por AC-C1-13.
- *Carga perezosa por vencimiento*: más solicitudes repartidas pero el selector de vencimientos no sabría cuáles son líquidos sin cargarlos; se elige carga ansiosa con conteo de fallos parciales.
- *Mostrar opciones ilíquidas con aviso*: prohibido por C6 (no se ofrecen).
- *Caché con TTL*: el SPEC pide ver "lo último guardado" sin internet; el texto de antigüedad ya informa de la edad.
- *Leer `dividendYield`*: llega en porcentaje y mezclaría escalas; se usa la fracción `trailingAnnualDividendYield`.

## Arquitectura

```
datos/
  __init__.py     # reexporta tipos, errores, load_snapshot, FakeProvider...; SIN importar yfinance ni pandas
  types.py        # OptionQuote, MarketSnapshot (dataclasses frozen)
  errors.py       # DatosError, NetworkError, RateLimitError, EmptyDataError + MSG_* en español
  provider.py     # Protocol MarketDataProvider
  filters.py      # LiquidityRules, clean_row, filter_chain, dedupe (puro)
  cache.py        # .cache_datos/{etiqueta}.json (SPX.json); escritura atómica; sin TTL; regla parcial-vs-rico
  tickers.py      # lista curada por tipo; ticker -> símbolo Yahoo
  fake.py         # FakeProvider respaldado por fixtures (+ fail_with)
  service.py      # load_snapshot, helpers de r/q/días, textos de antigüedad
  yahoo.py        # YahooProvider: único módulo que usa yfinance (import dentro del constructor)
```

- `OptionQuote(kind, strike, bid, ask, last, oi, volume, iv_yahoo)`: `kind` en {"call","put"}; `last` y `iv_yahoo` informativos (nunca entran en la prima). `mid` es una propiedad `(bid+ask)/2`.
- `MarketSnapshot(ticker, loaded_at, spot, rate, q, q_source, chains, source)`: `chains: dict[str, list[OptionQuote]]` (clave = vencimiento ISO `YYYY-MM-DD`, solo vencimientos con al menos una opción líquida); `q` puede ser `None` (índice o no disponible); `q_source` en {"yahoo","indice","no_disponible"}; `source` en {"live","cache"}.
- `MarketDataProvider` (Protocol): `get_spot(ticker) -> float`, `get_expirations(ticker) -> list[str]`, `get_chain(ticker, expiry) -> list[dict]` (filas crudas), `get_rate() -> float` (fracción), `get_dividend_yield(ticker) -> float | None`.
- `clean_row(dict) -> OptionQuote | None`; `filter_chain(quotes, spot, rules) -> list[OptionQuote]`; `LiquidityRules` frozen con los valores del SPEC y `DEFAULT_RULES`.
- `service.load_snapshot(ticker, provider, today, now, cache_dir, rules)`: obtiene spot, r, q (índice → `q=None`, `q_source="indice"`), expiraciones; filtra la ventana 7–120 días (con `today` inyectado); descarga cada cadena; limpia y filtra; descarta vencimientos vacíos; guarda caché en carga exitosa. **Política de fallos parciales:** al primer `RateLimitError` se detiene la descarga de más cadenas (no se insiste); si ya hay ≥1 cadena → snapshot parcial + aviso con el conteo; si hay 0 → se lanza `RateLimitError`. Otros fallos de una cadena se cuentan y se sigue. **Regla parcial-vs-rico:** un snapshot parcial (o con menos vencimientos/cotizaciones que el guardado) no sobrescribe un archivo de caché más rico: se conserva el rico y se avisa. Si el spot, las expiraciones o todas las cadenas fallan → `DatosError` específico; el llamador (app) recurre a `cache.read_snapshot(...)`.
- **Reloj inyectable:** `today`/`now` llegan como parámetros; la app los toma de `st.session_state.get("clock")` (callable que devuelve un `datetime` con zona; por defecto `datetime.now(ZoneInfo("America/New_York"))`), igual que `data_provider` y `cache_dir` (solo inyección en tests). `FakeProvider(today=..., offsets=(10, 17, 45, 90, 150))` genera vencimientos a `today + offset` días (por defecto +10, +17, +45, +90, +150; `offsets` sobrescribible por prueba para los bordes exactos 6/7/120/121) (los de +150 caen fuera de la ventana a propósito); todas las pruebas que dependen de fechas fijan el reloj.
- Cuándo se usa la caché: si `load_snapshot` lanza `DatosError`, `app.py` llama a `cache.read_snapshot` (filtros reaplicados, días recomputados desde hoy) y muestra su hora ("datos guardados de DD/MM HH:MM"); si no hay caché → aviso y entrada manual.
- `YahooProvider(tz_cache_dir=None, timeout=...)`: `import yfinance` solo dentro del constructor; `yf.set_tz_cache_location(tz_cache_dir)` con el directorio **inyectable** (por defecto `<repo>/.cache_datos/yfinance`; los tests pasan `tmp_path`, así que nunca crean `.cache_datos/` real); timeout explícito por solicitud (por defecto 10 s); convierte DataFrames a `list[dict]` (pandas solo aquí); mapea excepciones de red/429/vacío a `NetworkError`/`RateLimitError`/`EmptyDataError` con un `except` amplio dentro del adaptador que incluye los errores de conexión de `curl_cffi` y `requests` (→ `NetworkError`); `^IRX` percent→fracción.
- Aislamiento: `import opciones` e `import datos` no deben cargar `yfinance` ni `pandas` (test en subproceso).
- Estado de la app: `ticker_choice` y `expiry_choice` son **claves de widgets selectbox** (viven en la barra lateral, que se dibuja siempre; verificado con sonda AppTest); `snapshot` y `load_notice` (lista de mensajes) son claves simples no ligadas a widgets. La cascada y el botón usan callbacks: `on_underlying_change` (cambia el tipo) y **`on_ticker_change`** (cambia el ticker dentro del mismo tipo) limpian `snapshot`, `expiry_choice` y `load_notice` para que nunca se muestre la cadena de SPY bajo una etiqueta QQQ (C-V1).

## Phase Completion Rules

A phase is NOT complete until:

1. **Integration Test** - el bloque funciona con los anteriores y con los 2330 tests existentes (`.venv/bin/pytest -q` completo, con el bloqueo de red activo desde el bloque 3).
2. **Manual Test** - el usuario puede reproducir con `.venv/bin/python -c ...` (bloques 1–4) y la checklist manual (bloques 5–7).
3. **Data Verification** - cifras de referencia (supervivencia de filtros, conversiones r/q, mid, IV ida y vuelta) recalculadas **con los datos exactos de cada fixture** (lección de Etapas A/B1: no copiar de un prototipo con otras entradas). Referencia de cordura medida en el estudio: AAPL 27/28, SPY 138/148, ^SPX 21/41 (4 calls, 17 puts) — se **recalcula** al grabar las fixtures y se fija el valor medido.
4. **Error Handling** - entradas malas o fallos de red devuelven mensajes en español, nunca NaN, excepciones hacia la UI ni números inventados.
5. **User Confirmation** - el usuario dice "funciona".

Status: ⏳ PLANNED · 🔨 CODE DONE · 🧪 TESTING · ✅ VERIFIED · 🚧 BLOCKED.

Regla honesta: un bloque con tests verdes y sin revisión del usuario es `🔨 CODE DONE`, no `✅ VERIFIED`. Solo el usuario pasa un bloque a `✅ VERIFIED`. **Lección del MVP/Etapas A y B1:** vc-execute-agent no puede escribir bajo `process/`; las actualizaciones de estado de este plan y el reporte se hacen en UPDATE PROCESS.

Reporte (lo crea EXECUTE/UPDATE PROCESS, no este plan): `process/general-plans/completed/etapa-c1-datos-directo_20-11-26/etapa-c1-datos-directo_REPORT_20-11-26.md`.

## Acceptance Criteria

Se heredan literalmente **AC-C1-1..AC-C1-16 del SPEC** (no se reescriben). Interpretaciones fijadas por este plan:

- **AC-C1-1:** `tickers.py` expone la lista por tipo; la cascada solo ofrece "Entrada manual" + esos tickers (selectbox cerrado: no hay texto libre); una función `resolve_ticker(kind, name)` rechaza (`ValueError`/`None`) cualquier ticker fuera de la lista.
- **AC-C1-2:** con `ticker_choice == "Entrada manual"` ningún camino nuevo se ejecuta: mismos widgets, mismos valores por defecto, mismas claves de estado que antes (más las nuevas, inertes); los 2330 tests existentes siguen verdes sin tocar sus números. El selector de patas reales no aparece sin snapshot.
- **AC-C1-3:** "Cargar datos" escribe `spot` desde el callback (antes de dibujar widgets); spot, r y q siguen siendo `number_input` editables.
- **AC-C1-4:** r: `^IRX` 4,12 → `0.0412` en el servicio y `rate_pct = 4.12` en la app (`round(rate*100, 2)`); q: `trailingAnnualDividendYield` (fracción) → `q_pct = round(q*100, 2)`; ausente en acción/ETF → `q_pct = 0` + caption "sin dividend yield disponible: q = 0, edítalo si hace falta"; índice → no se toca q + nota C10 exacta: "sin dividend yield para índices: edítalo, SPX ≈ 1,2 %".
- **AC-C1-5:** `LiquidityRules` es un dataclass frozen con los defaults del SPEC en un único lugar; los tests de borde recorren cada umbral en el límite exacto, justo dentro y justo fuera (p. ej. OI 99/100, spread 10 %/10,01 %, mid 0,99 con spread 0,10/0,11, strike ±20 %, días 6/7/120/121). **Regla de tolerancia (C-V3):** toda comparación de umbral con decimales usa `EPS = 1e-9` a favor del límite (`spread <= limit + EPS`, `abs(strike/spot - 1) <= 0,20 + EPS`); OI y días son enteros (comparación exacta). Trampa medida: `0.40 - 0.30 <= 0.10` es falso por ruido de coma flotante (0.10000000000000003). Los casos de "justo en el límite" se prueban con **filas sintéticas de borde** construidas con entradas binario-exactas o redondeadas explícitamente (p. ej. bid 0,50 / ask 0,60 y bid 0,30 / ask 0,40 deben pasar con spread absoluto 0,10; spot 100 con strikes 80 y 120; vencimientos a 7 y 120 días exactos con el reloj fijado), porque las filas grabadas solo cubren ±10 % y un vencimiento.
- **AC-C1-6:** todo lo que la UI ofrece sale de `snapshot.chains` (ya filtrado); la lista de vencimientos son las claves de `chains`; con la fixture con muchos bid = 0, ninguna de esas filas aparece.
- **AC-C1-7:** la prima de la pata = `(bid+ask)/2` exacto; test con fixture donde `last` ≠ mid por mucho (put con último viejo).
- **AC-C1-8:** IV del motor: `implied_vol(leg, market)` con la prima = mid; ida y vuelta: precio del motor con esa IV ≈ mid (misma tolerancia que B1, |Δprecio| ≤ 1e-6 donde la IV es identificable). La IV de Yahoo se muestra con el rótulo "IV Yahoo (referencia): x %" y no entra en ningún cálculo.
- **AC-C1-9:** textos: vivo `"datos con ~15 min de retraso; cargados a las HH:MM"`; caché `"datos guardados de DD/MM HH:MM"`; las funciones reciben el reloj como parámetro (reloj falso en tests); en la app el reloj sale de `st.session_state["clock"]` (por defecto `datetime.now`), y los `days` del callback de Vencimiento y la aserción "HH:MM" usan ese reloj. Ningún test dependiente de fechas queda sin reloj fijado (C-V2).
- **AC-C1-10:** `cache.py` escribe de forma atómica (temp + `os.replace`); JSON corrupto o `schema_version` distinto → "sin caché" (no excepción); el archivo se llama como la etiqueta curada (`SPX.json`, nunca `^SPX.json`); un snapshot parcial no sobrescribe uno más rico (se conserva el rico y se avisa); `.cache_datos/` aparece en `.gitignore` (`git check-ignore .cache_datos/x.json` imprime la ruta).
- **AC-C1-11:** cada `DatosError` trae su `MSG_*` (red, límite de solicitudes, respuesta vacía, "sin opciones líquidas ahora" para mercado cerrado/fin de semana); la UI muestra `st.error`/`st.warning`, nunca el traceback.
- **AC-C1-12:** fixtures sucias (columnas ausentes, strike duplicado, bid > ask, negativos, NaN) → se descartan por fila; el resto de la cadena sobrevive; no hay NaN en ninguna salida.
- **AC-C1-13:** `import opciones` e `import datos` en un subproceso no cargan `yfinance`, `pandas`, `streamlit` (este último solo para `opciones`/`datos`); `git diff --stat -- opciones/` vacío; `FakeProvider` y `YahooProvider` pasan los mismos tests de contrato de interfaz (el segundo solo con `LIVE_DATA=1` o con un cliente simulado dentro del adaptador).
- **AC-C1-14:** autouse en `tests/conftest.py` que parchea `socket.socket.connect` y `socket.getaddrinfo` para lanzar un error claro, desactivado si `LIVE_DATA=1`; **no** se parchea `socketpair` (lo usa asyncio/Streamlit). `tests/test_datos_live.py` con `skipif(os.environ.get("LIVE_DATA") != "1")`; **conteo esperado tras C1: N passed, 3 skipped** (2 previos + 1 prueba en vivo; una sola función de test en vivo).
- **AC-C1-15:** `requirements.txt` añade exactamente `yfinance==1.8.0` y `pandas==3.1.1`; el resto de líneas intactas. Instalación en el `.venv` sin conflictos (verificado por dry-run en INNOVATE; añade beautifulsoup4 4.15.0, cffi 2.1.1, curl_cffi 0.17.0, lxml 6.1.3, peewee 4.5.3, platformdirs 4.14.8, pycparser 3.12, pytz 2026.6, soupsieve 4.1.3).
- **AC-C1-16:** `.venv/bin/pytest -q` → 2330 existentes pasan; total esperado = 2330 + nuevos passed, 3 skipped; con el bloqueo de red activo en todo momento.

## Touchpoints

| Bloque | Archivo | Acción |
|---|---|---|
| 1 | `requirements.txt` | modificar (añadir `yfinance==1.8.0`, `pandas==3.1.1`) |
| 1 | `.gitignore` | modificar (añadir `.cache_datos/`) |
| 1 | `datos/__init__.py`, `types.py`, `errors.py`, `provider.py` | crear |
| 1 | `tests/test_datos_types.py` | crear |
| 2 | `datos/filters.py` | crear |
| 2 | `tests/test_datos_filters.py` | crear |
| 3a | `tests/conftest.py` | crear (bloqueo de red autouse) |
| 3b | `tests/fixtures/` (AAPL, SPY, ^SPX recortadas + sintéticas: bid cero, sucia, último viejo, **filas de borde exacto**: ±20 %, 7/120 días, spread 10 % y 0,10) | crear |
| 3c | `datos/cache.py` (nombre `SPX.json`, regla parcial-vs-rico, helpers de comparación) | crear |
| 3c | `tests/test_datos_cache.py` | crear |
| 3d | `datos/fake.py` (vencimientos relativos al reloj, `offsets` configurables), `datos/service.py` (reloj inyectable, usa `cache.py`, parada en el primer 429) | crear |
| 3d | `tests/test_datos_service.py` | crear |
| 4 | `datos/yahoo.py` (timeout, errores de conexión → `NetworkError`, `tz_cache_dir` inyectable) | crear |
| 4 | `tests/test_datos_yahoo.py` (adaptador con cliente simulado), `tests/test_datos_isolation.py` (subproceso), `tests/test_datos_live.py` | crear |
| 5 | `datos/tickers.py` | crear |
| 5 | `app.py` | modificar (estado nuevo, cascada, callback de carga, antigüedad) |
| 5 | `tests/test_datos_tickers.py`, `tests/test_app_smoke.py` | crear / ampliar |
| 6 | `app.py` | modificar (selector de patas reales, `premium_source`, IV Yahoo, aviso de vencimiento) |
| 6 | `tests/test_app_smoke.py`, `tests/test_datos_chain_picker.py` | ampliar / crear |
| 7 | `tests/test_app_smoke.py` | ampliar |
| Cierre | `process/context/all-context.md`, `process/context/tests/all-tests.md` | modificar en UPDATE PROCESS (no en EXECUTE de código) |

Solo lectura / sin tocar: **todo `opciones/`** (motor sin diff), `tests/test_*.py` existentes salvo `test_app_smoke.py` (solo se amplía), el SPEC.

## Public Contracts

| Elemento | Contrato |
|---|---|
| `OptionQuote` | dataclass frozen: `kind`, `strike`, `bid`, `ask`, `last`, `oi`, `volume`, `iv_yahoo`; propiedad `mid`. |
| `MarketSnapshot` | dataclass frozen: `ticker`, `loaded_at` (datetime con zona), `spot`, `rate` (fracción), `q` (fracción o `None`), `q_source`, `chains`, `source` ("live"/"cache"). |
| `DatosError` y subclases | `NetworkError`, `RateLimitError`, `EmptyDataError`; cada una con mensaje en español (`MSG_NETWORK`, `MSG_RATE_LIMIT`, `MSG_EMPTY`, `MSG_NO_LIQUID`...). |
| `MarketDataProvider` | Protocol con `get_spot`, `get_expirations`, `get_chain`, `get_rate`, `get_dividend_yield`. |
| `LiquidityRules` / `DEFAULT_RULES` | frozen; únicos umbrales del paquete. |
| `clean_row(row) -> OptionQuote \| None`; `filter_chain(quotes, spot, rules, ...)` | puras; no lanzan; sin NaN en la salida. |
| `load_snapshot(...)` | devuelve `MarketSnapshot` o lanza `DatosError`; escribe caché solo en éxito. |
| `cache.write_snapshot / read_snapshot` | escritura atómica; lectura devuelve `None` si falta, está corrupta o es de otro `schema_version`. |
| `new_leg_dict(...)` | gana campos opcionales para patas de mercado (`premium_source`, `bid`, `ask`, `iv_yahoo`, `expiry`); las llamadas existentes siguen válidas. |
| Claves de `session_state` | `ticker_choice` y `expiry_choice` (claves de widgets selectbox), `snapshot`, `load_notice` (nuevas); `data_provider`, `cache_dir` y **`clock`** (callable → `datetime` con zona; por defecto `datetime.now`) solo para inyección en tests. Callbacks nuevos: `on_underlying_change`, **`on_ticker_change`**, `on_load_data`. |
| `service.load_snapshot(..., today, now, ...)` / `cache.read_snapshot(..., today)` | `today`/`now` inyectables; `today` = fecha de mercado en `America/New_York`; `FakeProvider(today=..., offsets=(10, 17, 45, 90, 150))` con vencimientos relativos y offsets configurables. |
| Reloj y zona horaria (A3) | Reloj por defecto `datetime.now(ZoneInfo("America/New_York"))`; fechas de mercado y `days` en `America/New_York`; textos de hora convertidos a la zona local del sistema con `.astimezone()` (los tests comparan con `fixed.astimezone().strftime(...)`). |
| `cache.write_snapshot / richness / is_richer_or_equal` | `write_snapshot(...) -> (escrito, aviso o None)`; no importa `service.py` (la caché va antes que el servicio, C-V6). |
| `YahooProvider(tz_cache_dir=None, timeout=...)` | directorio tz de yfinance y timeout inyectables; errores de conexión → `NetworkError`. |
| `LiquidityRules` | incluye la tolerancia `EPS = 1e-9` para comparaciones decimales. |
| `opciones/` | **sin cambios** (ni API ni comportamiento). |

## Blast Radius

- **Archivos nuevos:** 10 módulos en `datos/`, ~9 archivos de test, fixtures, `tests/conftest.py`.
- **Modificados:** `requirements.txt`, `.gitignore`, `app.py` (cascada, callback de carga, selector de patas, IV de referencia), `tests/test_app_smoke.py` (ampliar).
- **Riesgo:** medio. El motor no cambia. El riesgo principal es `app.py` (estado de widgets y callbacks) y el bloqueo de red global en `conftest.py` (afecta a toda la suite). Mitigación: modo manual protegido por AC-C1-2 y emulación contra la suite completa tras cada cambio de la app y del `conftest`.
- **Entorno:** instalar dependencias en `.venv` (+~237 MB, aceptado por el usuario, C2/C-G4).

## Implementation Checklist

Orden estricto; cada bloque termina con pytest verde. Reglas transversales: TDD (tests primero, en rojo), funciones cortas, comentarios y docstrings en español, identificadores en inglés, `pytest.approx` en floats, ningún `print` en `datos/`, `datos/` no importa `streamlit` ni nada de UI, **no modificar `opciones/`**.

**Reglas vinculantes para el agente de EXECUTE (lecciones de MVP/A/B1):**
- Los agentes de EXECUTE **no pueden escribir bajo `process/`**: no editar este plan ni crear el reporte; devolver el estado de bloques y la información del informe en el mensaje final.
- **No tocar `opciones/`** (el motor no cambia; `git diff --stat -- opciones/` vacío al final de cada bloque).
- **Servidores:** si se arranca alguno (smoke manual), usar un puerto distinto de **8501** (vista previa del usuario: nunca tocarla ni detenerla) y **detener** el que se haya arrancado antes de terminar.
- **Streamlit conserva imports obsoletos en memoria:** tras cambiar código de `datos/` o `app.py`, reiniciar el servidor que se haya arrancado (no basta con recargar la página).
- `st.metric` trunca textos largos (visto dos veces): mensajes de antigüedad, avisos y notas van en `st.caption`/`st.info`/markdown, no en `st.metric`.
- El estado de un widget solo cambia desde callbacks `on_click`/`on_change` (antes del render); si no, `StreamlitWidgetAlreadyInstantiatedError`.
- AppTest ejecuta **todas las pestañas** en cada ejecución y **no puede vaciar un `number_input` a `None`**; no escribir tests que dependan de ello.
- **Recalcular las cifras de referencia con las entradas exactas** de cada test/fixture antes de fijarlas; registrar en el test el valor medido y la tolerancia.
- **Emular los cambios transversales de la app contra la suite completa** (`.venv/bin/pytest -q`) antes de darlos por buenos (cambios en `app.py` y en `conftest.py`).
- Cualquier prueba contra la red real solo con `LIVE_DATA=1`, a propósito y sin que `pytest -q` la ejecute.

### Bloque 1 — Dependencias, `.gitignore` y tipos de `datos/` (AC-C1-13 parcial, AC-C1-15, AC-C1-10 parcial)

**Explicación para el usuario:** antes de escribir nada que hable con Yahoo, preparamos el terreno: fijamos las versiones de las librerías nuevas (para que la app arranque igual dentro de seis meses), dejamos que git ignore la carpeta de caché, y creamos el paquete `datos/` con las "cajas" de datos (una cotización, una foto del mercado), los errores con mensajes en español y el "enchufe" (interfaz) al que se conectará cualquier proveedor.

- [ ] Ejecutar `date +%d-%m-%y` y `.venv/bin/pytest -q` → 2330 passed, 2 skipped antes de tocar nada.
- [ ] Crear `tests/test_datos_types.py` (en rojo): `OptionQuote.mid`, inmutabilidad (frozen), `MarketSnapshot` con `q=None`, jerarquía de errores (`NetworkError`, `RateLimitError`, `EmptyDataError` heredan de `DatosError`), cada `MSG_*` es texto en español no vacío, el `Protocol` es satisfecho por una clase mínima de prueba.
- [ ] Modificar `requirements.txt`: añadir `yfinance==1.8.0` y `pandas==3.1.1` (sin tocar las demás líneas). Modificar `.gitignore`: añadir `.cache_datos/`.
- [ ] Instalar en el `.venv`: `.venv/bin/pip install -r requirements.txt` (**requiere red fuera del sandbox; puede pedirse aprobación al usuario**). Verificar `.venv/bin/pip check` sin conflictos y `.venv/bin/python -c "import yfinance, pandas; print(yfinance.__version__, pandas.__version__)"` → `1.8.0 3.1.1`.
- [ ] Crear `datos/types.py`, `errors.py`, `provider.py`, `__init__.py` (sin importar `yfinance` ni `pandas`).
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_types.py -q`; `git check-ignore -v .cache_datos/x.json`; `git diff requirements.txt`; luego `.venv/bin/pytest -q`.
- **Pass criteria:** tests nuevos verdes; 2330 existentes verdes; `requirements.txt` solo gana 2 líneas; `.cache_datos/` ignorada; `pip check` limpio.

### Bloque 2 — Filtros de liquidez y limpieza (AC-C1-5, AC-C1-6 parcial, AC-C1-12)

**Explicación para el usuario:** este es el "portero" de las opciones: solo deja pasar las que se pueden operar de verdad (hay oferta y demanda, el hueco entre ambas es estrecho, hay muchos contratos abiertos, el strike está cerca del precio y el vencimiento ni muy pronto ni muy lejos). Todas las reglas viven en un único cuadro (`LiquidityRules`) para ajustarlas en un solo sitio. Además limpia filas rotas (precios negativos, NaN, strikes repetidos) sin romper el resto.

- [ ] Crear `tests/test_datos_filters.py` (en rojo) con tablas de casos en el borde: bid = 0 / ask = 0 / negativos / NaN / `None`; OI 99 vs 100; spread relativo 10 % vs 10,01 %; mid < 1 con spread absoluto 0,10 vs 0,11; strike en ±20 % exactos y justo fuera; días 6/7/120/121; bid > ask descartado; strikes duplicados (kind, strike); campos ausentes; **umbrales en un solo lugar** (cambiar `LiquidityRules` cambia el resultado; ningún número mágico duplicado en el módulo). Con fixtures reales grabadas (bloque 3 las crea; aquí se usa una fila-de-ejemplo en línea y se amplía con las fixtures en el bloque 3).
- [ ] **Tolerancia (C-V3):** en los mismos tests (rojo primero) añadir casos de borde exacto con **filas sintéticas en línea** de entradas binario-exactas o redondeadas: spread absoluto 0,10 con bid 0,50/ask 0,60 y con bid 0,30/ask 0,40 (este último falla sin tolerancia: `0.40-0.30 <= 0.10` es falso), spread relativo exactamente 10 %, strikes exactos a ±20 % del spot (80 y 120 con spot 100), vencimientos a exactamente 7 y 120 días con `today` fijado, OI 100.
- [ ] Crear `datos/filters.py`: `LiquidityRules` (frozen, defaults del SPEC, constante `EPS = 1e-9`) y `DEFAULT_RULES`; `clean_row`, `dedupe` y `filter_chain`; comparaciones decimales `<= límite + EPS` (spread, ventana de strikes), OI y días enteros exactos; funciones puras, sin lanzar, sin NaN de salida.
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_filters.py -q` y luego `.venv/bin/pytest -q`.
- **Pass criteria:** tablas de borde verdes; ningún umbral fuera de `LiquidityRules`; 2330 existentes verdes.

### Bloque 3 — Bloqueo de red, fixtures, proveedor falso, servicio y caché (AC-C1-3, AC-C1-4, AC-C1-5, AC-C1-6, AC-C1-9, AC-C1-10, AC-C1-11, AC-C1-12, AC-C1-14)

Bloque dividido en 4 sub-bloques ordenados (C-V5): 3a conftest, 3b fixtures, 3c caché, 3d proveedor falso + servicio (el servicio usa la caché, C-V6); cada uno con sus comandos de gate, y ninguno empieza con el anterior en rojo. **Pass criteria del bloque 3 = suma de los pass criteria de 3a–3d.**

#### Bloque 3a — Bloqueo de red en `conftest.py` y suite completa (AC-C1-14)

**Explicación para el usuario:** antes de cualquier código de datos ponemos un candado: ningún test podrá abrir conexiones de red (salvo que actives `LIVE_DATA=1` a propósito). Lo probamos de inmediato contra los 2330 tests existentes para asegurar que el candado no rompe nada.

- [ ] Crear `tests/conftest.py` (en rojo primero: un test que intenta `socket.create_connection` y espera el error claro): fixture autouse función-scope que parchea con `monkeypatch` `socket.socket.connect` y `socket.getaddrinfo` para lanzar `RuntimeError("red bloqueada en tests: use LIVE_DATA=1")`; desactivado si `LIVE_DATA=1`; **no** parchear `socketpair` ni nada de `asyncio`. (Medido en VALIDATE: con este bloqueo la suite da 2330 passed + 2 skipped.)
- [ ] El test de bloqueo vive en `tests/test_datos_types.py` (sin archivos extra fuera de Touchpoints). Comandos: `.venv/bin/pytest tests/test_datos_types.py -q` y luego `.venv/bin/pytest -q` completo.
- **Pass criteria:** el test de bloqueo verde; **2330 existentes verdes + 2 skipped con el bloqueo activo**; si alguno falla por el bloqueo se resuelve en `conftest.py`, nunca cambiando tests existentes.

#### Bloque 3b — Fixtures y cifras medidas (AC-C1-5, AC-C1-6, AC-C1-12)

**Explicación para el usuario:** grabamos datos de prueba: filas reales recortadas de AAPL, SPY y SPX, más filas inventadas a propósito para los casos difíciles (justo en el límite de cada regla, filas sucias, precios viejos). Así los tests no dependen de Internet ni del día en que se ejecuten.

- [ ] Grabar fixtures en `tests/fixtures/` desde `chains.json` del scratchpad (recortadas a pocas filas por vencimiento): `aapl`, `spy`, `spx` (filas reales: strike, last, bid, ask, iv, vol, oi) + sintéticas: `bid_zero` (muchas filas bid = 0), `dirty` (columnas ausentes, strike duplicado, bid > ask, negativos, NaN), `stale_last` (último precio viejo muy distinto del mid, p. ej. put con último 176 frente a bid/ask 322/335) y **`edge_exact`** (filas de borde exacto, C-V3: strikes a ±20 % exactos, spread 10 % y 0,10 USD exactos con entradas binario-exactas, OI 99/100; los vencimientos de borde 7/120 días se generan relativos al reloj fijado, no como fechas absolutas). Las fixtures reales guardan fechas absolutas **solo como datos crudos**: cualquier test que dependa de la fecha rebasa/usa el reloj fijado (C-V2).
- [ ] **Recalcular** con los datos exactos grabados cuántas filas sobreviven (referencia de cordura medida por VALIDATE sobre las grabaciones completas: AAPL 27/28 (1 por spread), SPY 138/148 (10 por OI), ^SPX 21/41 con 4 calls y 17 puts (17 por OI, 3 por spread); las filas grabadas solo cubren ±10 % del spot y un vencimiento, por lo que **no** ejercitan el filtro de ±20 % ni la ventana 7–120 días: por eso existe `edge_exact`). Si las fixtures están recortadas, fijar el valor medido de la fixture recortada, no el del estudio. Anotar q medidos: AAPL 0,0030354 → `q_pct` 0,3; SPY 0,0079093 → 0,79; `^IRX` 4,122 → 0,04122 → `rate_pct` 4,12.
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_filters.py -q` (ampliado con las fixtures de borde) y luego `.venv/bin/pytest -q`.
- **Pass criteria:** tests de filtros verdes con las fixtures reales y sintéticas; valores medidos anotados; suite completa verde con el bloqueo activo.

#### Bloque 3c — Caché con regla parcial-vs-rico (AC-C1-10, AC-C1-11)

**Explicación para el usuario:** la caché guarda lo último cargado en un archivo (escrito de forma segura: o queda completo o no queda). Un archivo por ticker con el nombre limpio (`SPX.json`). Si una carga nueva sale incompleta no pisa una copia guardada más completa: se avisa y se conserva la buena. Va **antes** del servicio porque el servicio la usa (C-V6); aquí los tests construyen los snapshots a mano con los tipos del bloque 1 y los filtros del bloque 2, sin proveedor ni servicio.

- [ ] Crear `tests/test_datos_cache.py` (en rojo, siempre con `tmp_path`; snapshots armados con `MarketSnapshot`/`OptionQuote` y las fixtures de 3b, **sin** `FakeProvider` ni `service`): escribe y lee, atómica, nombre `SPX.json` para `^SPX` (nunca `^SPX.json`), JSON corrupto → sin caché, `schema_version` distinto → sin caché, filtros reaplicados al leer, días recomputados desde el reloj inyectado (`today`), sin caché → `None`; **parcial-vs-rico** con los helpers `richness(snapshot)` (nº de vencimientos, nº de cotizaciones) y `is_richer_or_equal(new, old)`: un snapshot con menos vencimientos (o menos cotizaciones) no sobrescribe el archivo más rico y `write_snapshot` devuelve el aviso; uno igual o más rico sí lo sustituye.
- [ ] Crear `datos/cache.py` (`.cache_datos/` resuelta desde la ruta del archivo, raíz del repo, o `cache_dir` inyectado; un JSON por etiqueta curada con `schema_version`, `loaded_at` ISO con zona, spot, rate, q, q_source y cotizaciones limpias por vencimiento; `richness`, `is_richer_or_equal`, `write_snapshot(...) -> (escrito: bool, aviso | None)`, `read_snapshot(label, cache_dir, today, rules)`; comparación por nº de vencimientos y nº de cotizaciones antes de escribir). No importa `service.py`.
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_cache.py tests/test_datos_filters.py -q`; `git status --short .cache_datos` (nada creado por los tests); luego `.venv/bin/pytest -q`.
- **Pass criteria:** tests verdes; **ninguna escritura fuera de `tmp_path`** (la carpeta real `.cache_datos/` no se toca desde la suite); 2330 existentes verdes con el bloqueo activo.

#### Bloque 3d — `FakeProvider`, servicio y reloj inyectable (AC-C1-3, AC-C1-4, AC-C1-6, AC-C1-9, AC-C1-10, AC-C1-11)

**Explicación para el usuario:** el "cerebro" de la carga: un proveedor falso (con fechas relativas al reloj, para que las pruebas no caduquen con el tiempo) y el servicio que junta precio + tasa + dividendos + cadenas filtradas y guarda en la caché del bloque 3c. Si Yahoo empieza a limitarnos (error 429) el servicio deja de pedir más y se queda con lo que ya tiene.

- [ ] Crear `tests/test_datos_service.py` (en rojo, con `cache_dir` en `tmp_path`): **todas las pruebas con el reloj fijado** (`today`/`now` inyectados); conversión r (4,12 % → 0,0412), q desde `trailingAnnualDividendYield` (fracción), q ausente → `q_source="no_disponible"` + aviso, índice → `q=None`/`q_source="indice"`; ventana de vencimientos 7–120 **con bordes exactos a nivel de servicio (A1)**: `FakeProvider(today=..., offsets=(6, 7, 120, 121))` → ofrece 7 y 120, excluye 6 y 121 (otra prueba con los `offsets` por defecto); vencimiento sin opciones que pasen no ofrecido; fallo parcial de cadenas (conteo + aviso, el resto sobrevive); **primer `RateLimitError` detiene las peticiones siguientes** (el `FakeProvider` cuenta las llamadas: tras el 429 no hay más `get_chain`); ≥1 cadena + 429 → snapshot parcial + aviso con el conteo; 0 cadenas + 429 → `RateLimitError`; errores: red, límite, respuesta vacía, "sin opciones líquidas ahora"; textos de antigüedad con reloj falso (zona: ver Public Contracts); la carga exitosa escribe la caché y un snapshot parcial no pisa una caché más rica ya guardada (usa `cache.py` de 3c); `FakeProvider` intercambiable (`fail_with`); ningún test falla al cambiar la fecha real del sistema (probar con dos relojes distintos que dan el mismo resultado relativo).
- [ ] Crear `datos/fake.py` (`FakeProvider(today=..., offsets=(10, 17, 45, 90, 150))`: expiraciones a `today + offset` días, `offsets` sobrescribible por prueba, respaldado por las fixtures) y `datos/service.py` (parámetros `today`/`now`, uso de `cache.write_snapshot`, política de fallos parciales y parada en el primer 429 descritas en Arquitectura).
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_service.py tests/test_datos_cache.py tests/test_datos_filters.py -q`; `git status --short .cache_datos`; luego `.venv/bin/pytest -q`.
- **Pass criteria:** tests verdes con reloj fijado; sin dependencia de la fecha real; bordes 6/7/120/121 correctos a nivel de servicio; ninguna escritura fuera de `tmp_path`; suite completa verde con el bloqueo activo.

### Bloque 4 — Adaptador de Yahoo, aislamiento de importaciones y prueba en vivo opcional (AC-C1-4, AC-C1-13, AC-C1-14, AC-C1-15)

**Explicación para el usuario:** este es el único archivo que habla con Yahoo Finance. Traduce lo que devuelve `yfinance` (tablas de pandas) a nuestras cajas simples y convierte sus fallos en mensajes en español. Lo probamos sin Internet con un "yfinance de mentira" y, a propósito y una sola vez, con la red real para confirmar que los campos existen y medir cuántas solicitudes hace una carga.

- [ ] Crear `tests/test_datos_yahoo.py` (en rojo): el adaptador con un módulo `yfinance` simulado (inyectado en `sys.modules`/parámetro): `^IRX` 4,12 → 0,0412; q desde `trailingAnnualDividendYield` y **no** desde `dividendYield`; `info` que falla → q no disponible + aviso; `fast_info` preferido para el spot; DataFrames → `list[dict]`; mapeo de excepciones a `NetworkError`/`RateLimitError`/`EmptyDataError`; **errores de conexión de `curl_cffi`/`requests` (p. ej. `ConnectionError`, timeout) → `NetworkError`** mediante un `except` amplio dentro del adaptador; el timeout por solicitud se pasa al cliente; `set_tz_cache_location` recibe el `tz_cache_dir` inyectado (**`tmp_path`**: los tests nunca crean `.cache_datos/` real).
- [ ] Crear `tests/test_datos_isolation.py`: subproceso (`sys.executable -c ...`) que importa `opciones` y `datos` y comprueba que `yfinance` y `pandas` **no** están en `sys.modules` (y que `import datos` funciona sin `yfinance` instalado simulado, p. ej. bloqueando la importación con un finder).
- [ ] Crear `tests/test_datos_live.py`: una única función de test con `pytest.mark.skipif(os.environ.get("LIVE_DATA") != "1", ...)` que carga SPY con `YahooProvider` real y comprueba campos (spot > 0, r en (0, 0,2), al menos un vencimiento, filas con bid/ask/OI). **Conteo esperado: 3 skipped** (2 previos + este).
- [ ] Crear `datos/yahoo.py` (`YahooProvider(tz_cache_dir=None, timeout=...)`; `import yfinance` dentro del constructor; pandas solo aquí; `yf.set_tz_cache_location(tz_cache_dir)`; timeout explícito; `except` amplio de errores de conexión → `NetworkError`).
- [ ] **Una ejecución manual en vivo** (`LIVE_DATA=1 .venv/bin/pytest tests/test_datos_live.py -q -s`; requiere red fuera del sandbox; la estimación de VALIDATE es SPY ≈ 18–22 solicitudes y ^SPX ≈ 32–35, **sin medir**: el permiso de la corrida en vivo fue denegado): anotar cuántas solicitudes hace una carga de SPY, si `Ticker.info` limita, y confirmar los campos; si hay 429, no reintentar en bucle: registrar y seguir con fixtures. Si la fuente falla, el bloque se marca `🔨 CODE DONE` y se avisa al usuario.
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_yahoo.py tests/test_datos_isolation.py tests/test_datos_live.py -q` (live omitido) y luego `.venv/bin/pytest -q`.
- **Pass criteria:** tests verdes; `import opciones`/`import datos` sin `yfinance`/`pandas`; `.venv/bin/pytest -q` → 2330 + nuevos passed, **3 skipped**; resultado de la corrida en vivo anotado para el informe.

### Bloque 5 — Lista curada, cascada de la barra lateral, "Cargar datos" y antigüedad (AC-C1-1, AC-C1-2, AC-C1-3, AC-C1-4, AC-C1-9, AC-C1-10, AC-C1-11, AC-C1-13)

**Explicación para el usuario:** en la barra lateral, debajo de "Tipo de subyacente", aparece el selector de ticker (solo los de la lista corta, o "Entrada manual"). Al pulsar "Cargar datos" la app rellena precio, tasa y dividendos (que puedes seguir editando) y muestra de cuándo son los datos. Si cambias de tipo, el ticker vuelve a "Entrada manual" y se olvidan los datos cargados; si cambias de ticker dentro del mismo tipo (SPY → QQQ), también se olvidan los datos hasta que pulses "Cargar datos" otra vez. Con "Entrada manual" todo es exactamente como antes.

- [ ] Crear `datos/tickers.py` (lista curada por tipo, `resolve_ticker`) y `tests/test_datos_tickers.py` (en rojo): lista por tipo, SPX→`^SPX`, ticker fuera de lista rechazado, "Entrada manual" no resuelve a ticker.
- [ ] Ampliar `tests/test_app_smoke.py` (en rojo) con `FakeProvider` inyectado vía `st.session_state["data_provider"]` y `cache_dir` en `tmp_path`: la cascada aparece; el botón "Cargar datos" está deshabilitado en modo manual; tras cargar (callback) `spot`, `rate_pct` y `q_pct` quedan escritos y editables; texto de antigüedad con la hora; Índice: q **no** cambia + nota C10; error de proveedor → mensaje en español y, con caché previa, datos guardados con su hora; cambiar el tipo reinicia `ticker_choice` y borra el snapshot; **C-V1: cargar SPY y cambiar a QQQ (mismo tipo) sin pulsar "Cargar datos" → desaparecen el selector de patas reales y el Vencimiento, no se ofrecen strikes de SPY y `snapshot`/`expiry_choice`/`load_notice` quedan vacíos**. **A2:** tras "Cargar datos" `expiry_choice` == primer vencimiento ofrecido, el selector Vencimiento lo muestra y `days == (vencimiento - hoy).days` con el reloj fijado. Reloj falso inyectado con `st.session_state["clock"]`: la aserción "HH:MM" y la ventana de vencimientos no dependen de la fecha real (C-V2). Recordar: AppTest corre todas las pestañas.
- [ ] Modificar `app.py`: `init_state` gana `snapshot = None`, `load_notice = []`, y las claves de widgets `ticker_choice = "Entrada manual"` y `expiry_choice = None` (selectbox en la barra lateral, siempre dibujada); `on_underlying_change` (on_change del selector de tipo: reinicia `ticker_choice` y borra el snapshot), **`on_ticker_change` (on_change de `ticker_choice`: limpia `snapshot`, `expiry_choice` y `load_notice`)** y `on_load_data` (callback del botón: **fija `expiry_choice` explícitamente al primer vencimiento ofrecido y `days` en el mismo callback** — la sonda mostró que dejar `expiry_choice = None` tras recargar no selecciona ningún Vencimiento ni fija `days` (A2); resuelve el proveedor con `st.session_state.get("data_provider") or YahooProvider()`, `cache_dir` con `st.session_state.get("cache_dir")` y el reloj con `st.session_state.get("clock")` (por defecto `datetime.now`), llama a `load_snapshot` con `today`/`now` de ese reloj, escribe `spot`, `rate_pct = round(rate*100, 2)`, `q_pct` (no índice; ausente → 0 + caption; índice → no tocar + nota C10) **antes de dibujar los widgets**; ante `DatosError` intenta `cache.read_snapshot` y guarda los avisos en `load_notice`); `render_sidebar` dibuja `ticker_choice` (selectbox: "Entrada manual" + lista del tipo), el botón (deshabilitado en manual), el caption de antigüedad (`"datos con ~15 min de retraso; cargados a las HH:MM"` o `"datos guardados de DD/MM HH:MM"`) y los avisos de `load_notice`. La importación de `YahooProvider` es diferida (dentro de la función) para que la app arranque aunque `yfinance` falle.
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_tickers.py tests/test_app_smoke.py -q` y luego `.venv/bin/pytest -q` (**emular el cambio de `app.py` contra la suite completa**).
- **Pass criteria:** smoke verde; modo manual idéntico (los tests existentes de la app sin tocar); 2330 existentes verdes; sin excepciones visibles ante errores de proveedor.

### Bloque 6 — Selector de patas reales, `premium_source`, IV de Yahoo como referencia y aviso de vencimiento (AC-C1-6, AC-C1-7, AC-C1-8, AC-C1-9, AC-C1-11)

**Explicación para el usuario:** con datos cargados, en el Constructor aparece un panel para añadir patas desde la cadena real: eliges call/put, comprar/vender y un strike de la lista (solo líquidos, con su bid, ask, mid y la IV de Yahoo a modo de referencia). La pata entra con prima = mid; la IV que la app muestra la calcula nuestro propio motor, y la de Yahoo se rotula como "referencia". Si editas la prima a mano, deja de ser "de mercado". Si una pata es de otro vencimiento que el elegido arriba, la app avisa.

- [ ] Crear `tests/test_datos_chain_picker.py` y ampliar `tests/test_app_smoke.py` (en rojo): con snapshot cargado (FakeProvider) el expander existe; la lista de strikes sale solo de `snapshot.chains[expiry]`; con la fixture `bid_zero` ninguna fila ilíquida aparece; "Añadir pata" crea una pata con `price == (bid+ask)/2` (`pytest.approx`), `premium_manual=True`, `premium_source="mercado"`, `bid`, `ask`, `iv_yahoo`, `expiry`; `refresh_auto_prices` no la toca al cambiar spot/modelo; con `stale_last` la prima ignora el último precio; la etiqueta de origen es "mercado (mid de bid X / ask Y)"; `on_premium_change` la pasa a `premium_source="manual"`; el reset y el cambio de `kind` limpian `premium_source`; "IV Yahoo (referencia): x %" aparece junto a la IV del motor y no altera el valor de la IV del motor; ida y vuelta del motor (precio del motor con la IV mostrada ≈ mid, **recalculado con las entradas exactas** de la fixture); pata con vencimiento distinto al seleccionado → `st.warning`; elegir un vencimiento en el selector fija `days` por callback (días naturales hasta esa fecha desde hoy, **con `today` tomado del reloj inyectable `session_state["clock"]`**; los tests fijan el reloj y los vencimientos del `FakeProvider` son relativos a él, así que no caducan, C-V2).
- [ ] Modificar `app.py`: selector **Vencimiento** en la barra lateral (solo claves de `snapshot.chains`; `on_change` fija `days`); en el Constructor, bajo "+ añadir pata", un `st.expander` con call/put, comprar/vender, cantidad y selectbox de strikes etiquetado con bid/ask/mid y IV Yahoo, y botón "Añadir pata" con callback que llama a `new_leg_dict(...)` extendido (precio = mid, `premium_manual=True`, `premium_source="mercado"`, `bid`, `ask`, `iv_yahoo`, `expiry`); `refresh_auto_prices` salta las patas con `premium_source == "mercado"` (ya saltan por `premium_manual`; se verifica que ningún camino las pisa); `price_origin` devuelve `"mercado (mid de bid X / ask Y)"`; `render_leg_iv` añade `st.caption("IV Yahoo (referencia): x %")` cuando la pata la tiene; `on_premium_change` fija `premium_source="manual"`; `reset_premium` y `on_kind_change` la limpian; aviso `st.warning` si el vencimiento de alguna pata no coincide con el seleccionado. Textos largos en `st.caption`, no `st.metric`.
- [ ] Comandos: `.venv/bin/pytest tests/test_datos_chain_picker.py tests/test_app_smoke.py -q` y luego `.venv/bin/pytest -q` (**emular contra la suite completa**).
- **Pass criteria:** smoke verde; prima = mid exacto; IV de Yahoo no entra en ningún cálculo; 2330 existentes verdes; modo manual idéntico.

### Bloque 7 — Smoke final, suite completa con red bloqueada y checklist manual (AC-C1-2, AC-C1-14, AC-C1-15, AC-C1-16)

**Explicación para el usuario:** cierre del ciclo: comprobamos que todo el flujo funciona de principio a fin con datos falsos, que la suite completa pasa sin Internet, que el motor no cambió ni una línea y que las dependencias están fijadas. Después te dejamos una lista corta para probar tú la app con datos reales.

- [ ] Ampliar `tests/test_app_smoke.py`: flujo completo con `FakeProvider` y reloj fijado (cargar → elegir vencimiento → añadir pata real → analizar sin excepciones ni NaN; cambiar SPY → QQQ no muestra la cadena de SPY); error de red con caché y sin caché; Índice con nota C10; modo manual idéntico (todos los tests existentes siguen verdes sin tocarlos).
- [ ] Gate de cierre: `.venv/bin/pytest -q` → **2330 + nuevos passed, 3 skipped**; `git diff --stat -- opciones/` vacío; `git diff requirements.txt` solo con las 2 líneas nuevas; `git check-ignore .cache_datos/x.json`; `.venv/bin/pip check` limpio; revisar con un grep que no quedan umbrales de liquidez fuera de `LiquidityRules`.
- [ ] Comprobar que la suite pasa de verdad sin red (el bloqueo autouse lo garantiza; opcional: `unshare -rn .venv/bin/pytest -q`, verificado como utilizable por VALIDATE: los 39 tests AppTest pasan en un espacio de red nuevo) y que ningún test escribe en `.cache_datos/` real.
- [ ] Checklist manual para el usuario (`.venv/bin/streamlit run app.py --server.port 8502`; **nunca 8501**; detener el servidor al terminar): (1) modo manual igual que antes; (2) elegir SPY → "Cargar datos": spot, r, q rellenados y editables; (3) texto de antigüedad con la hora; (4) vencimientos solo líquidos; (5) añadir una pata real: prima = mid, IV del motor y "IV Yahoo (referencia)"; (6) editar la prima a mano → deja de ser "de mercado"; (7) cambiar el tipo → ticker vuelve a "Entrada manual"; (8) Índice SPX: q intacto y nota "sin dividend yield para índices…"; (9) sin internet: mensaje en español y datos guardados con su hora; (10) pata de otro vencimiento → aviso.
- **Pass criteria:** gate de cierre completo en verde; checklist entregado; estado de bloques `🔨 CODE DONE` hasta que el usuario confirme.

## Verification Evidence

| Gate / Scenario | Strategy | Proves SPEC criterion |
|---|---|---|
| `.venv/bin/pytest tests/test_datos_tickers.py -q` (lista curada por tipo, ticker fuera de lista rechazado) + `.venv/bin/pytest tests/test_app_smoke.py -q` (cascada) + checklist manual ítems 2 y 7 | Hybrid | AC-C1-1 |
| `.venv/bin/pytest tests/test_app_smoke.py -q` (modo manual sin cambios) + `.venv/bin/pytest -q` completo (2330 existentes) | Fully-Automated | AC-C1-2 |
| `.venv/bin/pytest tests/test_datos_service.py tests/test_app_smoke.py -q` (carga rellena spot; valores editables tras la carga) | Fully-Automated | AC-C1-3 |
| `.venv/bin/pytest tests/test_datos_service.py tests/test_datos_yahoo.py tests/test_app_smoke.py -q` (r 4,12 → 0,0412; q desde `trailingAnnualDividendYield`; índice y ausente con aviso, nota C10) | Fully-Automated | AC-C1-4 |
| `.venv/bin/pytest tests/test_datos_filters.py -q` (tablas de borde de cada umbral; umbrales en `LiquidityRules`; filas sintéticas `edge_exact`: spread 0,10 con 0,30/0,40, ±20 %, 7 y 120 días con tolerancia `EPS`) | Fully-Automated | AC-C1-5 |
| `.venv/bin/pytest tests/test_app_smoke.py -q` (cargar SPY → cambiar a QQQ: desaparecen selector de patas y Vencimiento; `snapshot` limpio) | Fully-Automated | AC-C1-1, AC-C1-3 |
| `.venv/bin/pytest tests/test_datos_service.py tests/test_app_smoke.py -q` con reloj fijado (dos relojes distintos → mismo resultado relativo; sin dependencia de la fecha real) | Fully-Automated | AC-C1-9, AC-C1-16 |
| `.venv/bin/pytest tests/test_datos_cache.py tests/test_datos_service.py tests/test_datos_yahoo.py -q` (parada en el primer 429, parcial no pisa rico, `SPX.json`, timeout/conexión → `NetworkError`, `tz_cache_dir` en `tmp_path`) | Fully-Automated | AC-C1-10, AC-C1-11 |
| `.venv/bin/pytest tests/test_datos_filters.py tests/test_datos_service.py tests/test_datos_chain_picker.py -q` (ilíquidas y vencimientos vacíos no ofrecidos; fixture con bid cero) | Fully-Automated | AC-C1-6 |
| `.venv/bin/pytest tests/test_datos_chain_picker.py -q` (prima = mid exacto; fixture de último viejo ignorada) | Fully-Automated | AC-C1-7 |
| `.venv/bin/pytest tests/test_datos_chain_picker.py tests/test_app_smoke.py -q` (IV del motor ida y vuelta con mid; IV Yahoo solo con rótulo "referencia") | Fully-Automated | AC-C1-8 |
| `.venv/bin/pytest tests/test_datos_service.py tests/test_app_smoke.py -q` (texto de antigüedad con reloj falso; bordes 6/7/120/121 con `FakeProvider(offsets=...)`) | Fully-Automated | AC-C1-9 |
| `.venv/bin/pytest tests/test_datos_cache.py -q` (escribe/lee, sin red usa caché, sin caché aviso) + `git check-ignore .cache_datos/x.json` | Fully-Automated | AC-C1-10 |
| `.venv/bin/pytest tests/test_datos_service.py tests/test_datos_yahoo.py -q` (red, límite, vacío, mercado cerrado) + smoke AppTest + checklist manual ítem 9 | Hybrid | AC-C1-11 |
| `.venv/bin/pytest tests/test_datos_filters.py -q` (fixture sucia: duplicados, bid > ask, negativos, NaN, columnas ausentes) | Fully-Automated | AC-C1-12 |
| `.venv/bin/pytest tests/test_datos_isolation.py -q` (subproceso) + tests de contrato de `FakeProvider` + `git diff --stat -- opciones/` vacío | Hybrid | AC-C1-13 |
| `.venv/bin/pytest -q` completo (bloqueo de red autouse activo) + `.venv/bin/pytest tests/test_datos_live.py -q` → omitido por defecto | Fully-Automated | AC-C1-14 |
| `git diff requirements.txt` (solo `yfinance==1.8.0`, `pandas==3.1.1`) + `.venv/bin/pip check` + `.venv/bin/pytest -q` + smoke AppTest | Hybrid | AC-C1-15 |
| `.venv/bin/pytest -q` completo desde la raíz: 2330 existentes + nuevos passed, 3 skipped | Fully-Automated | AC-C1-16 |

**Qué demuestra y qué NO demuestra (known gaps, residual):**
- Los tests demuestran la lógica (filtros, conversión, caché, errores) con datos grabados y proveedor falso; **no** demuestran que Yahoo siga devolviendo esos campos hoy (C-G9): eso solo lo mira la prueba en vivo opcional (una ejecución manual en el bloque 4).
- AppTest ejecuta todas las pestañas en cada ejecución: no prueba persistencia entre pestañas lazy ni lo visual (C-G10; checklist manual). **Known-Gap, no apto para PASS por sí solo:** AC-C1-1, AC-C1-11 y AC-C1-13 (Hybrid) quedan condicionados a la revisión manual.
- Las cadenas fuera de horario pueden traer cotizaciones desactualizadas: solo el texto de antigüedad lo advierte (C-G5).
- Las cifras de supervivencia de filtros (AAPL 27/28, SPY 138/148, ^SPX 21/41) son del estudio previo y **VALIDATE las reprodujo exactamente** con un script independiente; las fixtures recortadas fijan sus propios valores medidos.
- **Hechos medidos por VALIDATE (outer PVL, primera pasada):** emulación del bloqueo de red sobre la suite completa → **2330 passed + 2 skipped** (47 s; `unshare -rn` también funciona); sondas de widgets AppTest todas OK; vencimientos dentro de la ventana 7–120 días: SPY 12, QQQ 11, IWM 9, AAPL 9, ^SPX 27 → carga ansiosa SPY ≈ 18–22 solicitudes y ^SPX ≈ 32–35 (**estimación, no medición**: la corrida en vivo fue denegada); dry-run de dependencias sin conflictos; expectativa de **3 skipped** confirmada (los 2 previos son un `pytest.skip` en tiempo de ejecución de `test_binomial_iv.py`; la prueba en vivo añade 1).

## Matriz de trazabilidad AC-C1-1..AC-C1-16

| AC | Bloque(s) | Archivo(s) de test |
|---|---|---|
| AC-C1-1 | 5 (incl. `on_ticker_change`) | `tests/test_datos_tickers.py`, `tests/test_app_smoke.py` |
| AC-C1-2 | 5, 7 | `tests/test_app_smoke.py` + tests existentes |
| AC-C1-3 | 3d, 5 | `tests/test_datos_service.py`, `tests/test_app_smoke.py` |
| AC-C1-4 | 3d, 4, 5 | `tests/test_datos_service.py`, `tests/test_datos_yahoo.py`, `tests/test_app_smoke.py` |
| AC-C1-5 | 2, 3b | `tests/test_datos_filters.py` (+ fixture `edge_exact`) |
| AC-C1-6 | 2, 3b, 3d, 6 | `tests/test_datos_filters.py`, `tests/test_datos_service.py`, `tests/test_datos_chain_picker.py` |
| AC-C1-7 | 6 | `tests/test_datos_chain_picker.py` |
| AC-C1-8 | 6 | `tests/test_datos_chain_picker.py`, `tests/test_app_smoke.py` |
| AC-C1-9 | 3d, 5, 6 | `tests/test_datos_service.py`, `tests/test_app_smoke.py` (reloj inyectable) |
| AC-C1-10 | 1, 3c, 3d | `tests/test_datos_cache.py`, `tests/test_datos_service.py` + `git check-ignore` |
| AC-C1-11 | 1, 3c, 3d, 4, 5 | `tests/test_datos_types.py`, `tests/test_datos_cache.py`, `tests/test_datos_service.py`, `tests/test_datos_yahoo.py`, `tests/test_app_smoke.py` |
| AC-C1-12 | 2, 3b | `tests/test_datos_filters.py` |
| AC-C1-13 | 1, 4, 7 | `tests/test_datos_isolation.py`, `tests/test_datos_types.py` + `git diff --stat -- opciones/` |
| AC-C1-14 | 3a, 4, 7 | `tests/conftest.py` (+ test de bloqueo en `tests/test_datos_types.py`), `tests/test_datos_live.py` |
| AC-C1-15 | 1, 7 | `requirements.txt` + `pip check` |
| AC-C1-16 | 7 | `.venv/bin/pytest -q` completo |

## Risk Predictions

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| R1 | **Límite de solicitudes (429) / muchas solicitudes:** estimación de VALIDATE: carga ansiosa de SPY ≈ 18–22 solicitudes (12 cadenas en ventana) y ^SPX ≈ 32–35 (27 cadenas); riesgo medio por carga, alto con clics repetidos; `Ticker.info` también puede ser limitado | Media | Parada en el primer 429 (se conserva lo descargado; 0 cadenas → `RateLimitError`); timeout por solicitud; un snapshot parcial no pisa una caché más rica; medir en la corrida en vivo del bloque 4 (si se permite); `info` fallido → q no disponible con aviso; mensaje `MSG_RATE_LIMIT` y caché |
| R2 | **Imports obsoletos en Streamlit:** tras editar `datos/` el servidor sigue con el código viejo | Alta | Reiniciar el servidor que se arranque; AppTest corre en proceso nuevo; documentado en las reglas de EXECUTE |
| R3 | **IV solo para patas elegidas:** calcular la IV de toda la cadena sería lento (binomial) | Media | Calcular IV del motor solo para las patas añadidas; la lista de strikes muestra solo IV de Yahoo como referencia |
| R4 | **Cotizaciones desactualizadas en fin de semana/fuera de horario** | Media | Los filtros descartan bid/ask = 0; el texto de antigüedad advierte; `MSG_NO_LIQUID` cuando no queda nada |
| R5 | **`st.metric` trunca textos largos** (visto dos veces) | Media | Antigüedad, avisos y notas en `st.caption`/`st.info`; revisión manual |
| R6 | **SPX con muchos vencimientos semanales:** selector largo y más solicitudes | Media | Ventana 7–120 días; solo vencimientos con opciones líquidas; ^SPX medido 21/41 |
| R7 | **El bloqueo de red en `conftest.py` rompe los 2330 tests existentes** (p. ej. Streamlit/AppTest abren sockets) | Baja (retirado por VALIDATE: emulación 2330 passed + 2 skipped) | No parchear `socketpair`; solo `connect`/`getaddrinfo`; ejecutar la suite completa inmediatamente tras crear el `conftest.py` (bloque 3a) y resolverlo allí |
| R8 | **Estado de widgets:** escribir `spot`/`days` fuera de un callback → `StreamlitWidgetAlreadyInstantiatedError`; el valor se pierde al cambiar de pestaña; **cambiar de ticker sin recargar mostraba la cadena del anterior** | Media | Todo cambio de estado desde `on_click`/`on_change`; `on_underlying_change` y `on_ticker_change` limpian `snapshot`/`expiry_choice`/`load_notice`; smoke AppTest SPY → QQQ |
| R9 | **Cadena de dependencias pesada o conflicto de versiones al instalar** (+~237 MB; dry-run limpio) | Baja | Versiones fijadas; `pip check`; instalación en el bloque 1 con aprobación del usuario si hace falta |
| R10 | **Cifras de referencia copiadas de un prototipo con otras entradas** | Media | Recalcular con las entradas exactas de cada fixture (lección A/B1) |
| R11 | **`import datos` carga `yfinance`/`pandas` por accidente** y el motor/arranque ya no es ligero | Baja-Media | `yfinance` importado en el constructor del adaptador; test en subproceso |
| R12 | **Caché corrupta o de otro esquema** rompe el arranque | Baja | `schema_version`; lectura defensiva devuelve `None`; escritura atómica |
| R13 | **Yahoo cambia su formato** y la suite normal no lo detecta | Media | Prueba en vivo opcional; mensajes claros; proveedor intercambiable |
| R14 | **Tests dependientes de fechas caducan** (las fixtures guardan vencimientos absolutos; con el tiempo salen de la ventana 7–120 días) | Alta | Reloj inyectable (`session_state["clock"]`, parámetros `today`/`now`); `FakeProvider` con vencimientos relativos; toda prueba dependiente de fechas fija el reloj (C-V2) |
| R15 | **Ruido de coma flotante en los umbrales** (`0.40-0.30 <= 0.10` es falso) rechaza filas que están exactamente en el límite | Media | `EPS = 1e-9` en `LiquidityRules`; filas sintéticas `edge_exact` con entradas binario-exactas (C-V3) |
| R16 | **Una carga parcial pisa una caché más rica**; escrituras de tests en el directorio real (`.cache_datos/`, tz de yfinance) | Media | Regla parcial-vs-rico en `cache.py`; `SPX.json` por etiqueta curada; `tz_cache_dir` y `cache_dir` inyectables, tests con `tmp_path` (C-V4) |

## Out of Scope

C2 (histórico del subyacente, backtest sintético y calibración); histórico de opciones de pago (C3); datos en tiempo real; operar, enviar órdenes o conectar con un bróker; cualquier opción de baja liquidez (ni siquiera con aviso); tickers fuera de la lista curada; **"abrir en el constructor" desde el catálogo con datos cargados** (las plantillas del catálogo siguen usando entrada manual/modelo); comisión de cierre racional (Etapa B2); cambios en el motor `opciones/`, en Monte Carlo, PoP o métricas; superficie/sonrisa de volatilidad y dividendos discretos; TTL o expiración de la caché; asesoría de inversión.

## Dependencies

- **Nuevas (fijadas):** `yfinance==1.8.0`, `pandas==3.1.1` (ya instalado por Streamlit). Dry-run sin conflictos; añade beautifulsoup4 4.15.0, cffi 2.1.1, curl_cffi 0.17.0, lxml 6.1.3, peewee 4.5.3, platformdirs 4.14.8, pycparser 3.12, pytz 2026.6, soupsieve 4.1.3.
- **Existentes:** numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0.
- **Orden:** bloques estrictamente secuenciales: 2 usa los tipos del 1; 3a–3b (conftest, fixtures) usan los filtros; 3c (caché) usa tipos y filtros; 3d (servicio) usa la caché 3c; 4 usa el servicio y los errores; 5 usa el servicio, la caché y el proveedor; 6 usa el estado y el snapshot del 5 (ambos tocan `app.py`); 7 cierra.
- **Red:** el bloque 1 (instalación) y la corrida en vivo del bloque 4 requieren red fuera del sandbox (puede pedirse aprobación al usuario).

## Test Infra Improvement Notes

(none identified yet)

## Resume and Execution Handoff

1. **Plan file:** `process/general-plans/completed/etapa-c1-datos-directo_20-11-26/etapa-c1-datos-directo_PLAN_20-11-26.md` (execute-anchor).
2. **Last completed phase/step:** PLAN escrito (20-11-26) y suplemento PVL aplicado (C-V1..C-V5: `on_ticker_change`, reloj inyectable + `FakeProvider` relativo, tolerancia `EPS` + filas de borde, robustez de carga/caché, bloque 3 dividido en 3a–3d); suplemento 2 (C-V6 + A1–A3): orden 3c caché → 3d servicio, `offsets` en `FakeProvider`, `expiry_choice`/`days` explícitos, zonas horarias; ningún bloque ejecutado.
3. **Validate-contract status:** first-pass CONDITIONAL (5 CONCERN) escrito; el suplemento está aplicado; vc-validate-agent debe re-validar desde V1 y emitir el nuevo veredicto (sustituye al anterior).
4. **Supporting context files loaded:** SPEC de la Etapa C1 (`process/general-plans/completed/etapa-c1-datos-directo_20-11-26/etapa-c1-datos-directo_SPEC_20-11-26.md`); `process/context/all-context.md`; `process/context/tests/all-tests.md`; `process/development-protocols/plan-lifecycle.md`; `implementation-standards.md`; plan de la Etapa B1 (formato); `app.py`; `opciones/__init__.py`; `tests/*`; scripts de investigación en el scratchpad `stageC/` (`chains.json`, `probe.py`, `dump.py`, `cmp.py`, solo referencia).
5. **Next step for a fresh agent:** tras VALIDATE, ejecutar el bloque 1 (TDD: `tests/test_datos_types.py` en rojo → `requirements.txt` + `.gitignore` + instalación en `.venv` + `datos/types.py`, `errors.py`, `provider.py`), gate `.venv/bin/pytest tests/test_datos_types.py -q` y luego `.venv/bin/pytest -q`; no empezar un bloque con el anterior en rojo; marcar `CODE DONE`, nunca `VERIFIED` sin confirmación del usuario.

**Instrucciones para el agente de EXECUTE (lecciones del MVP, A y B1, vinculantes):**
1. Bloques estrictamente en orden 1, 2, 3a, 3b, 3c (caché), 3d (proveedor falso + servicio), 4, 5, 6, 7; cada uno cierra con su gate y `.venv/bin/pytest -q` completo. Todo test dependiente de fechas fija el reloj; los tests no escriben fuera de `tmp_path`.
2. TDD: tests primero (rojo), luego implementación; código simple, identificadores en inglés, comentarios y docstrings en español.
3. **Los agentes de EXECUTE no pueden escribir bajo `process/`:** devolver estados de bloque, informe (tests nuevos, fixtures, cifras medidas, solicitudes de la corrida en vivo) y actualizaciones de contexto en el mensaje final.
4. **No modificar `opciones/`**; de los tests existentes solo se amplía `tests/test_app_smoke.py`; nunca cambiar números esperados de tests existentes.
5. **Servidores:** usar un puerto distinto de **8501** (nunca tocarla ni detenerla) y detener todo servidor arrancado; reiniciarlo tras cada cambio de código (Streamlit conserva imports obsoletos).
6. `st.metric` trunca textos largos: usar `st.caption`/`st.info`.
7. Estado de widgets solo desde callbacks (`on_click`/`on_change`).
8. AppTest ejecuta todas las pestañas y no puede vaciar un `number_input` a `None`.
9. Recalcular las cifras de referencia con las entradas exactas de cada fixture/test; anotar valor medido y tolerancia.
10. Emular los cambios transversales (`app.py`, `conftest.py`) contra la suite completa antes de darlos por buenos.
11. Sin red en la suite normal; red real solo con `LIVE_DATA=1`, a propósito (instalación y una corrida en vivo en los bloques 1 y 4).
12. EVL: un vc-tester independiente vuelve a ejecutar cada comando de gate.

## Validate Contract

Status: PASS
Date: 21-11-26
date: 2026-11-21
generated-by: outer-pvl
supersedes: 2026-11-21 (outer-pvl) — re-validation from V1 after PVL supplement cycle 2 (C-V6, A1-A3 applied)

Parallel strategy: sequential
Rationale: 1/7 signals (S7: 5+ files); blocks 1, 2, 3a-3d, 4-7 strictly dependent, 5 and 6 share `app.py`; no concurrent file ownership possible. Executor opus, tester/validators sonnet.

### Re-validation result (V1-V3, 2026-11-21, after cycle 2)
- Structural validator: 0 failures, 0 warnings. `results.tsv` = header + baseline + 2 cycle rows (4 lines). `opciones/` untouched (`git diff --stat` empty); tree clean except this task folder; 8501 not touched; no Streamlit server started. All referenced paths resolve (`app.py`, `requirements.txt`, `.gitignore`, `tests/test_app_smoke.py`; `zoneinfo` America/New_York available in `.venv`).
- **C-V6 RESOLVED.** Reordering is consistent everywhere: Status strip, Arquitectura (cache before service; `cache.py` does not import `service.py`), Public Contracts (`write_snapshot / richness / is_richer_or_equal`), Touchpoints (3c cache + test; 3d fake + service + test), block titles, Dependencies order, Verification Evidence, Traceability (AC-C1-10 -> 1, 3c, 3d; AC-C1-11 -> 1, 3c, 3d, 4, 5), Resume/Execute order 1, 2, 3a, 3b, 3c, 3d, 4, 5, 6, 7. Each gate only references modules that exist by then: 3a uses `test_datos_types.py` (block 1); 3b uses filters (block 2); 3c tests build snapshots by hand from types + filters + 3b fixtures, no `FakeProvider`/`service`; 3d uses cache (3c) + filters; 4 uses service/errors; 5/6 use service, cache, provider.
- **A1 resolved/testable:** `FakeProvider(today=..., offsets=(10, 17, 45, 90, 150))` overridable; service tests with `offsets=(6, 7, 120, 121)` expect 7 and 120 offered, 6 and 121 excluded (Block 3d, Verification Evidence AC-C1-9 row).
- **A2 resolved/testable:** `on_load_data` sets `expiry_choice` to the first offered expiry and `days` in the same callback; Block 5 smoke asserts `expiry_choice` == first expiry, selector shows it, `days == (expiry - today).days` with fixed clock.
- **A3 resolved/testable:** market dates in America/New_York; "HH:MM" texts via `now.astimezone()`; tests compare with `fixed.astimezone().strftime(...)`.
- C-V1..C-V5 remain resolved; carried evidence still valid (network-block emulation 2330 passed + 2 skipped, also `unshare -rn`; survival AAPL 27/28, SPY 138/148, ^SPX 21/41; windowed expirations SPY 12, QQQ 11, IWM 9, AAPL 9, ^SPX 27; dry-run deps clean; 3 skipped expected). AC-C1-1..16 and C1-C10 all traced.
- Cosmetic leftovers (no gate impact, advisory only): Complejidad paragraph still says "7 módulos" (there are 10) ; Block 2 says "bloque 3 las crea" (means 3b); Resume item 3 still describes the old first-pass contract; Arquitectura lists `datos/__init__.py` re-exports in final form.

### Dimension findings
- Infra fit: PASS — deps pinned, dry-run clean, injectable dirs/clock/provider; `.cache_datos/` ignore rule planned; `zoneinfo` available.
- Test coverage: PASS — every block gate references only existing modules; AC-C1-1..16 and C1-C10 traced with exact repo-root commands; 6/7/120/121 edges and `expiry_choice` assertions present.
- Breaking changes: PASS — `opciones/` untouched; manual mode guarded by AC-C1-2; only `tests/test_app_smoke.py` extended; network block emulated against the full suite.
- Security surface: PASS — closed ticker list, no secrets, defensive cache reads, atomic writes; high-risk pack not required.
- Section feasibility: Blocks 1, 2, 3a, 3b, 3c, 3d, 4, 5, 6, 7 PASS.

### Test gates (run from repo root; every block ends with the full `.venv/bin/pytest -q`)

| criterion id | behavior | strategy | proving test | gap-resolution |
|---|---|---|---|---|
| AC-C1-15 | Block 1: pinned deps, `.gitignore`, types, errors | Fully-Automated | `.venv/bin/pytest tests/test_datos_types.py -q`; `git diff requirements.txt`; `git check-ignore -v .cache_datos/x.json`; `.venv/bin/pip check`; `.venv/bin/python -c "import yfinance, pandas; print(yfinance.__version__, pandas.__version__)"` | B |
| AC-C1-5, 12 | Block 2: liquidity rules, EPS boundaries, dirty rows | Fully-Automated | `.venv/bin/pytest tests/test_datos_filters.py -q` | B |
| AC-C1-14 | Block 3a: network block, suite still 2330+2 skipped | Fully-Automated | `.venv/bin/pytest tests/test_datos_types.py -q`; `.venv/bin/pytest -q` | B |
| AC-C1-5, 6, 12 | Block 3b: fixtures + measured survival | Fully-Automated | `.venv/bin/pytest tests/test_datos_filters.py -q` | B |
| AC-C1-10, 11 | Block 3c: cache atomic, `SPX.json`, corrupt/schema, partial-vs-rich | Fully-Automated | `.venv/bin/pytest tests/test_datos_cache.py tests/test_datos_filters.py -q`; `git status --short .cache_datos` empty | B |
| AC-C1-3, 4, 6, 9, 10, 11 | Block 3d: service, clock, 6/7/120/121 edges, 429 stop, r/q, cache write | Fully-Automated | `.venv/bin/pytest tests/test_datos_service.py tests/test_datos_cache.py tests/test_datos_filters.py -q`; `git status --short .cache_datos` empty | B |
| AC-C1-4, 13, 14 | Block 4: Yahoo adapter (simulated client), import isolation, live skipped | Fully-Automated | `.venv/bin/pytest tests/test_datos_yahoo.py tests/test_datos_isolation.py tests/test_datos_live.py -q`; `.venv/bin/pytest -q` -> N passed, 3 skipped | B |
| AC-C1-1, 2, 3, 4, 9, 11 | Block 5: cascade, load, `expiry_choice`/`days`, SPY->QQQ clearing, age text, manual mode unchanged | Hybrid | `.venv/bin/pytest tests/test_datos_tickers.py tests/test_app_smoke.py -q` + manual checklist 2, 7, 8, 9 | B |
| AC-C1-6, 7, 8 | Block 6: liquid-only picker, premium = mid, engine IV, Yahoo IV as reference | Fully-Automated | `.venv/bin/pytest tests/test_datos_chain_picker.py tests/test_app_smoke.py -q` | B |
| AC-C1-13 | engine untouched | Hybrid | `git diff --stat -- opciones/` empty + `.venv/bin/pytest tests/test_datos_isolation.py -q` | A |
| AC-C1-16 | Block 7: final suite, no network | Fully-Automated | `.venv/bin/pytest -q` -> 2330 + new passed, 3 skipped; optional `unshare -rn .venv/bin/pytest -q` | B |
| C-G9 | Yahoo still returns the fields | Hybrid | `LIVE_DATA=1 .venv/bin/pytest tests/test_datos_live.py -q -s` (network, may be denied) | D |

Failing stubs: each Fully-Automated row starts as the plan's own "en rojo" test step (Block checklists); equivalent stub per planned test: `raise AssertionError("NOT IMPLEMENTED — TDD stub")`.

Legacy line form: Block 1: pytest types + git check-ignore + pip check | Block 2: pytest filters | 3a: pytest types + full suite | 3b: pytest filters + full suite | 3c: pytest cache/filters + full suite | 3d: pytest service/cache/filters + full suite | Block 4: pytest yahoo/isolation/live | Block 5: pytest tickers + smoke | Block 6: pytest chain_picker + smoke | Block 7: full suite + `git diff --stat -- opciones/` + pip check + `unshare -rn` + manual checklist 1-10.

### Execute-agent instructions (binding)
1. Block order strictly 1, 2, 3a, 3b, 3c (cache), 3d (fake + service), 4, 5, 6, 7; each ends with its gate and the full `.venv/bin/pytest -q`; never start a block on a red suite; final state `CODE DONE`, never `VERIFIED`.
2. No writes under `process/`; return block status, measured numbers, new tests, live-run request counts and context-update text in the final message. Lessons (MVP/A/B1): do not edit the plan/report from EXECUTE; never touch port 8501 (use 8502+, stop it, restart after code changes: stale imports); `st.metric` only for numbers, messages in `st.caption`/`st.info`; widget state only in `on_click`/`on_change`; AppTest runs all tabs and cannot blank a `number_input`; recompute reference numbers from exact fixture rows (AAPL 27/28, SPY 138/148, ^SPX 21/41 are sanity targets only); emulate `app.py`/`conftest.py` changes against the full suite.
3. `opciones/` untouched (`git diff --stat -- opciones/` empty after every block); of existing tests only `tests/test_app_smoke.py` is extended; never edit existing expected numbers.
4. Block 1 `.venv/bin/pip install -r requirements.txt` (`yfinance==1.8.0`, `pandas==3.1.1`) needs network and may be run by the orchestrator outside the sandbox; do not retry blindly. Block 4's single live run is also network-gated; if denied, mark Block 4 `CODE DONE` with "live run pending" and report request counts as unmeasured.
5. `conftest.py`: autouse function-scoped `monkeypatch` of `socket.socket.connect` and `socket.getaddrinfo`, off when `LIVE_DATA=1`; never patch `socketpair`/asyncio; run the full suite immediately.
6. Thresholds only in `LiquidityRules` with `EPS = 1e-9`; grep `datos/` for stray literals. `datos/__init__.py` grows its re-exports block by block (only import modules that already exist) and never imports `yfinance`/`pandas`/`streamlit`.
7. 3c tests use no `FakeProvider`/`service`; `cache.py` must not import `service.py`. `FakeProvider` offsets overridable; all date-dependent tests fix the clock (market dates America/New_York; displayed HH:MM via `.astimezone()`); no test writes outside `tmp_path`.
8. `on_load_data` sets `expiry_choice` (first expiry) and `days` in the same callback; `on_ticker_change` clears `snapshot`/`expiry_choice`/`load_notice`.
9. `YahooProvider` import lazy in the app callback; its tests use a simulated `yfinance` module and a `tmp_path` tz-cache dir. IV round-trip tests use identifiable near-ATM legs.
10. EVL: an independent vc-tester re-runs every gate command above.

### What this coverage does NOT prove
- Tests prove logic on recorded data and a fake provider, not that Yahoo still returns these fields today (C-G9); only the optional live run does.
- AppTest runs all tabs: no lazy-tab persistence, no visual truncation check (C-G10); manual checklist 1-10 remains.
- Off-hours stale quotes are only warned by the age text (C-G5).
- Request counts (SPY ~18-22, ^SPX ~32-35) are estimates; live measurement was denied.
- Recorded fixtures do not cover the +-20 % strike or 7-120 day edges; only synthetic `edge_exact` rows and `offsets` tests do.
- Hybrid AC-C1-1, 11, 13 stay conditional on the user's manual review.

### Known gaps
C-G5, C-G9, C-G10 (documented residuals, gap-resolution D); request-count measurement pending the optional live run; cosmetic text leftovers listed above.

Open gaps: none blocking (known gaps above only).
Gate: PASS — 0 FAILs, 0 CONCERNs; C-V1..C-V6 resolved, A1-A3 resolved; after 2 PVL supplement cycles.
Accepted by: n/a (PASS; known gaps C-G5, C-G9, C-G10 recorded as residuals)

## Autonomous Goal Block

SESSION GOAL: Etapa C1 — datos de mercado en directo (Yahoo, solo opciones líquidas, caché local) en Laboratorio de Opciones, bloques 1, 2, 3a-3d (3c caché, 3d servicio), 4, 5, 6, 7.
Charter + umbrella plan: N/A — single plan (process/general-plans/completed/etapa-c1-datos-directo_20-11-26/etapa-c1-datos-directo_PLAN_20-11-26.md; SPEC locked in the same folder).
Autonomy: per feedback_autonomous_phase_execution.md — no approval pauses between blocks; delegation to spawned agents stays mandatory (execute = opus, vc-tester EVL = sonnet); blocked network steps are reported, not retried.
Hard stop conditions / safety constraints:
- Never touch, restart or stop the user's Streamlit on port 8501; any manual server uses 8502+ and is stopped afterwards.
- Do not modify `opciones/` (`git diff --stat -- opciones/` must stay empty); no writes under `process/` from EXECUTE.
- No real network in the normal suite (only `LIVE_DATA=1`); never write to the real `.cache_datos/` from tests; never start a block on a red suite.
- No commits, installs outside `.venv`, or account/financial actions without explicit user approval; block 1 `pip install` needs network approval (orchestrator may run it).
Next phase: EXECUTE: process/general-plans/completed/etapa-c1-datos-directo_20-11-26/etapa-c1-datos-directo_PLAN_20-11-26.md (block 1 first)
Validate contract: inline in the plan (`## Validate Contract`), Gate: PASS.
Execute start: `.venv/bin/pytest tests/test_datos_types.py -q` then `.venv/bin/pytest -q` (2330 passed, 2 skipped baseline) | e2e: AppTest smoke `tests/test_app_smoke.py` | probe: manual checklist 1-10 on port 8502 | high-risk pack: no

## Current Execution State

- Fase: PLAN completo; pendiente VALIDATE → EXECUTE.
- Bloques: 0/7 ejecutados.

## Lessons Learned and Deviations (UPDATE PROCESS)

(vacío hasta el cierre; lo rellena UPDATE PROCESS)

## Next Step

Ejecutar VALIDATE (vc-validate-agent escribe `## Validate Contract`), luego ENTER EXECUTE MODE con el bloque 1. RIPER-5: PLAN → VALIDATE → EXECUTE.
