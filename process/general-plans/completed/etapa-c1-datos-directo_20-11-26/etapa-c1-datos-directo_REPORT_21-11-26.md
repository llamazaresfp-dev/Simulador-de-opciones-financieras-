---
phase: etapa-c1-datos-directo-closeout
date: 2026-11-21
status: COMPLETE_WITH_GAPS
feature: none (general-plans)
plan: process/general-plans/completed/etapa-c1-datos-directo_20-11-26/etapa-c1-datos-directo_PLAN_20-11-26.md
---

# Informe de fase: Etapa C1, datos de mercado en directo (UPDATE PROCESS)

TL;DR: los 7 bloques están verificados, AC-C1-1..AC-C1-16 cumplidos, suite 2742 passed + 3 skipped (también bajo `unshare -rn`, sin red), checklist manual de 10 puntos pasada por el usuario el 21-11-26 ("todas las comprobaciones manuales funcionan correctamente"). Clasificación: COMPLETE_WITH_GAPS (3 huecos conocidos, ninguno bloquea). Plan archivado en `completed/`.

### What Was Done
- Paquete nuevo `datos/` (fuera del motor): `types.py` (OptionQuote, MarketSnapshot), `errors.py`, `provider.py` (Protocol MarketDataProvider), `filters.py` (LiquidityRules, DEFAULT_RULES: bid>0, ask>0, OI>=100, spread <=10% o <=0,10 si mid<1, +-20% del spot, 7-120 días), `cache.py` (`.cache_datos/`, ignorada por git, `SPX.json`, `schema_version`), `fake.py` (FakeProvider), `service.py` (`load_with_notices`, `load_or_cache`), `yahoo.py` (único lugar que importa yfinance/pandas), `tickers.py` (SPX->^SPX; SPY, QQQ, IWM; AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA; "Entrada manual").
- `app.py`: cascada Tipo -> Ticker -> "Cargar datos" -> Vencimiento, selector de patas reales (prima = mid, IV del motor, IV de Yahoo solo referencia), texto de antigüedad.
- Motor `opciones/`: diff vacío desde 3985dca. `requirements.txt` añade solo 2 pines (yfinance 1.8.0, pandas 3.1.1).
- Tests nuevos: test_datos_types, test_datos_filters, test_datos_cache, test_datos_service, test_datos_yahoo, test_datos_isolation, test_datos_live, test_datos_tickers, test_datos_chain_picker; smoke de la app ampliado. Bloqueo de red automático en `tests/conftest.py`.
- Commits: 78f48b4 (bloque 1), e2012b0 (2), e20f8f3 (3a-3b), a5e7ba8 (3c), 872c749 (3d), c48ede5 (4), 4d46e08 (5), f0d7194 (6), dcaec7e (7).
- PVL: 2 iteraciones; EVL: 2 iteraciones (informes 001/002 y `results.tsv` filas 0-7 en esta carpeta).
- Ejecución manual en vivo (21-11-26): carga de SPY con 25 peticiones HTTP; spot 689,81, r 0,04122, q 0,00791; 15 vencimientos líquidos; carga completa.

### What Was Skipped/Deferred
- Etapa B2 (comisión de cierre racional): sigue diferida; backlog `process/general-plans/backlog/close-fee-rational-close_20-11-26.md`.
- Etapa C3 (opciones históricas de pago): opcional, no planificada.
- Siguiente etapa: C2 (datos históricos del subyacente + página de backtest/calibración sintética) como plan nuevo.

### Test Gate Outcomes
- `.venv/bin/pytest -q`: 2742 passed, 3 skipped (EVL final, vc-tester), también bajo `unshare -rn` (sin red).
- 3 skips: 2 anteriores + la prueba en vivo opcional (requiere `LIVE_DATA=1`).
- Checklist manual de 10 puntos: OK por el usuario.
- Validadores (UPDATE PROCESS): ver mensaje de entrega.

### Plan Deviations
- Fixtures regrabadas el sábado 21-11-26: aapl y spy reales; spx_weekend real con todos los bid en 0; spx sintética más bid_zero/dirty/stale_last/edge_exact sintéticas.
- Contrato de claves de fila cruda: kind, strike, bid, ask, oi obligatorias; last, volume, iv_yahoo opcionales.
- Bandera `complete` en MarketSnapshot y regla de caché (las cargas completas siempre escriben; las parciales solo si no son más pobres dentro de la ventana de hoy) tras el ciclo 1 de EVL, que halló que la riqueza por conteo bruto bloqueaba cargas nuevas tras el cambio de vencimientos.
- `load_with_notices` / `load_or_cache` en `service.py`; parámetros `yf_module` / `session` en YahooProvider; editar el strike de una pata de mercado la vuelve manual.
- Corrección de `format_func` (etiquetas calculadas dentro de la ejecución del script; test de regresión `test_expiry_labels_do_not_read_clock_outside_script_run`) tras el ciclo 2 de EVL, que halló envejecimiento de fecha pasada la medianoche de Nueva York.

### Test Infra Gaps Found
- La prueba en vivo es solo opcional (`LIVE_DATA=1`): los cambios de formato de Yahoo no los detecta la suite normal (hueco 2).

### SPEC Achievement
AC-C1-1..AC-C1-16: todos **met** (Fully-Automated por gates pytest verdes; Hybrid por gates automáticos más la checklist manual de 10 puntos). Ninguno unmet ni basado solo en Known-Gap.

## SPEC Gaps
Ninguno de criterios. Huecos conocidos: (1) Yahoo es no oficial y frágil, retraso ~15 min, límites 429 (mitigado con caché y mensajes); (2) la prueba en vivo es opcional, los cambios de formato de Yahoo no se detectan en la suite normal; (3) con mercado cerrado o fin de semana SPX queda con todos los bid en 0 y sin opciones líquidas (por diseño, se muestra mensaje). Sin stubs de seguimiento.

### Closeout Packet
1. Plan seleccionado: `process/general-plans/completed/etapa-c1-datos-directo_20-11-26/etapa-c1-datos-directo_PLAN_20-11-26.md` (antes en `active/`).
2. Clasificación: COMPLETE_WITH_GAPS (gates verdes; known_gaps: 3; follow_up_stubs: 0).
3. Qué se terminó: ver What Was Done.
4. Verificado vs no verificado: todo verificado; los 3 huecos son límites conocidos y aceptados.
4b. Validate-contract: Gate PASS tras 2 iteraciones de PVL.
5. Limpieza: contexto actualizado, plan cerrado, carpeta archivada.
6. Siguiente estado válido: Etapa C2 como plan nuevo; B2 diferida; C3 opcional.
7. Commit: commits de código ya hechos; cierre de proceso en un commit aparte.
8. Regresión: plan único; suite completa 2742 passed + 3 skipped.
9. SPEC achievement: 16/16 met.

### Lessons (Streamlit)
- AppTest vuelve a invocar `format_func` fuera de la ejecución del script: no debe leer `session_state` ni el reloj.
- Cambiar el estado de widgets solo en callbacks.
- Reiniciar el servidor tras cambios de paquete.

### Forward Preview

#### Test Infra Found
Bloqueo de red autouse, `FakeProvider` con reloj inyectado, fixtures grabadas en `tests/fixtures/`, prueba en vivo opt-in.

#### Blast Radius Changes
Paquete nuevo `datos/`; `app.py` ampliado; motor intacto.

#### Commands to Stay Green
`.venv/bin/pytest -q` (2742 passed + 3 skipped); `LIVE_DATA=1 .venv/bin/pytest tests/test_datos_live.py -q` (opcional, requiere red).

#### Dependency Changes
`yfinance==1.8.0`, `pandas==3.1.1` en `requirements.txt`.

### Context Audit
- `process/context/all-context.md`: actualizado (estructura con `datos/`, stack, entorno/config, comportamientos C1, estado, metadatos).
- `process/context/tests/all-tests.md`: actualizado (archivos nuevos, 2742 + 3 skipped, bloqueo de red, LIVE_DATA=1, fixtures, huecos).
- `process/context/planning/all-planning.md`: revisado, sin cambios.
