---
phase: etapa-c2-historico-backtest-closeout
date: 2026-11-22
status: COMPLETE_WITH_GAPS
feature: none (general-plans)
plan: process/general-plans/completed/etapa-c2-historico-backtest_21-11-26/etapa-c2-historico-backtest_PLAN_21-11-26.md
---

# Informe de fase: Etapa C2, histórico del subyacente y calibración de la PoP (UPDATE PROCESS)

TL;DR: los 10 bloques están verificados, AC-C2-1..AC-C2-17 cumplidos, suite 3029 passed + 4 skipped (también bajo `unshare -rn`, sin red), checklist manual de 8 puntos pasada por el usuario el 22-11-26 ("Todo bien"). Clasificación: COMPLETE_WITH_GAPS (3 huecos conocidos, ninguno bloquea). Plan archivado en `completed/`.

### What Was Done
- Dos módulos puros nuevos en el motor (solo numpy, sin E/S): `opciones/calibration.py` (deciles, intervalos de Wilson, Brier, curtosis, histograma de colas) y `opciones/backtest.py` (ayudantes sobre números de día enteros y `run_backtest`, que recibe un objeto Template). Los módulos existentes del motor no cambian; `requirements.txt` sin cambios.
- Paquete `datos/` ampliado: `PriceHistory`, `HistoryProvider` (interfaz separada de la de C1), `history_cache.py` (`.cache_datos/history/`, un archivo por ticker, esquema propio, escritura atómica, reutilización con comprobación de cobertura), `history_service.py` (limpieza: descarta la fila de hoy, NaN, negativos y duplicados; recorte de años; ^IRX y dividendos), `YahooProvider.get_history` (único lugar con yfinance/pandas; SPX prueba ^GSPC y solo si viene vacío ^SPX; fallo de ^IRX no fatal) y `FakeProvider` con parámetros sigma/mu/seed/dividends/irx_percent_series/history_empty_symbols/history_fail_symbols/history_years e `history_calls`.
- Interfaz: 4.ª pestaña "📈 Backtest" en `ui_backtest.py` (raíz): controles, "Cargar histórico", "Calcular", gráfico de fiabilidad, tabla por tramo, Brier, N y N efectivo, avisos fijos e histograma de colas; sin E/S ni cálculo sin pulsar botones.
- Tests nuevos: test_calibration, test_backtest_helpers, test_backtest, synthetic.py (series GBM, regímenes y saltos), test_datos_history_types, test_datos_history_cache, test_datos_history_service, test_datos_yahoo_history, test_app_backtest; ampliados test_datos_isolation, test_datos_live (prueba en vivo opcional de histórico) y test_app_smoke.
- Commits: SPEC 14858a2; plan 45233d6 y 1127078 (cambio del usuario); bloques 1e26837 (1), 3c7e3d2 (2), d99a92e (3), 4c57c52 (4), fe64a9a (5), de2812c (6), 5452155 (7), 492b47d (8), 1219a3f (9), 65ecebb (10); fila EVL 4a21c2c.
- Rediseño visual de `app.py` por el usuario (a29af3e): etiquetas de pestañas con emoji ("📊 Catálogo", "🛠️ Constructor", "⚙️ Ajustes"), tarjetas del catálogo con insignias de color, iconos ➕/➖/🔄, subtítulos con divisor, constantes COLOR_SYSTEM/COLOR_STRATEGY/ICON_*. Su refactor dict->Leg quedó a medias y rompió 48 tests; se arregló restaurando las patas como diccionarios, revirtiendo `models.py` del motor, recuperando la línea de breakevens y el botón de reinicio, colores seguros en modo oscuro y 6 ediciones de tests solo de etiquetas. El original del usuario se conserva en `~/proyectos-claude/backup-app-usuario-22-11-26/`.
- PVL: 3 ciclos de suplemento (C-V1..C-V4 pereza del proveedor, tolerancias de oráculos, huella de caché, parámetros de FakeProvider; desviación (i) por cambio del usuario; S-1 `bt_window` 10-250, S-2 `requested_start` Optional). EVL: sin ciclos de arreglo (`results.tsv` filas 0-7 en esta carpeta).
- Oráculos medidos (40 años sintéticos, iron condor, H=30, W=30, paso 10): GBM |PoP media - observada| 0,008/0,028 (tolerancia 0,05); regímenes desviación máxima por decil (n>=100) 0,083/0,110 (<=0,15), habilidad 0,060/0,061 (>=0,03), |Brier - Σp(1-p)/N| 0,007/0,017 (<=0,04); saltos: curtosis 4,79, desviación máxima 0,447. Tiempo: 499 fechas en 0,74 s con BS y 1,33 s con la línea de μ.
- Ejecución manual del usuario (22-11-26): checklist de 8 puntos, "Todo bien".

### What Was Skipped/Deferred
- Etapa B2 (comisión de cierre racional): sigue en backlog `process/general-plans/backlog/close-fee-rational-close_20-11-26.md`.
- Etapa C3 (opciones históricas de pago): opcional, no planificada.
- Posible trabajo futuro: comparación con VIX (volatilidad implícita) y repetición de estrategias; sin plan.

### Test Gate Outcomes
- `.venv/bin/pytest -q`: 3029 passed, 4 skipped (EVL final, vc-tester), también bajo `unshare -rn`.
- 4 skips: 2 de binomial (IV) + 2 en vivo opcionales (C1 y C2, requieren `LIVE_DATA=1`).
- Diff del motor y dependencias: solo 2 archivos nuevos; huella de `.cache_datos` sin cambios; sin fugas a `.cache_datos/history`.
- Validadores (UPDATE PROCESS): ver mensaje de entrega.

### Plan Deviations
- Firmas de los ayudantes sobre números de día enteros; `first_analyzed_index` devuelve (índice, años disponibles, aviso); `expiry_index` devuelve None si no hay sesión en (t, t+H]; `run_backtest` recibe un objeto Template.
- Estado del backtest limpiado en `on_ticker_change`/`on_underlying_change`, no en `clear_loaded_data` (que "Cargar datos" de C1 también llama); `build_tails_figure(z)`; `init_backtest_state()`.
- Desviación (i) por cambio del usuario: descargar los años elegidos + 1 de calentamiento con reutilización de caché comprobada por cobertura (rechazada la descarga fija de 16 años).
- `clean_history` descarta dividendos con fecha de hoy o posterior; SPX prueba ^GSPC y luego ^SPX solo si viene vacío.
- Rediseño visual del usuario y su reparación (ver arriba), fuera del plan.

### Test Infra Gaps Found
- La prueba en vivo de histórico (^GSPC/^SPX, ^IRX, historial máximo) es opcional y no corre en la suite; solo la ejecución manual del usuario la ha comprobado (hueco 1).
- Un refactor de UI asistido por IA puede cambiar el estado en silencio: la suite completa debe correr tras cualquier cambio visual.

### SPEC Achievement
AC-C2-1..AC-C2-17: todos **met** (Fully-Automated por gates pytest verdes; Hybrid por gates automáticos más la checklist manual de 8 puntos). Ninguno unmet ni basado solo en Known-Gap.

## SPEC Gaps
Ninguno de criterios. Huecos conocidos: (1) el histórico real de Yahoo (^GSPC/^SPX, ^IRX, historial máximo) solo lo ha verificado la ejecución manual del usuario; la prueba en vivo opcional no está en la suite; (2) no hay volatilidad implícita histórica: se usa volatilidad realizada, así que la calibración mezcla error del modelo y prima de riesgo de volatilidad (comparación con VIX diferida); (3) ventanas solapadas: el N efectivo es una aproximación; la lógica `is_fresh` solo de días laborables puede volver a descargar una vez tras un festivo de mercado. Sin stubs de seguimiento.

### Closeout Packet
1. Plan seleccionado: `process/general-plans/completed/etapa-c2-historico-backtest_21-11-26/etapa-c2-historico-backtest_PLAN_21-11-26.md` (antes en `active/`).
2. Clasificación: COMPLETE_WITH_GAPS (gates verdes; known_gaps: 3; follow_up_stubs: 0).
3. Qué se terminó: ver What Was Done.
4. Verificado vs no verificado: todo verificado salvo el hueco 1 (solo manual).
4b. Validate-contract: Gate PASS tras 3 ciclos de PVL.
5. Limpieza: contexto actualizado, plan cerrado, carpeta archivada.
6. Siguiente estado válido: B2 (backlog), C3 opcional, comparación con VIX / repetición de estrategias como trabajo futuro.
7. Commit: commits de código ya hechos; cierre de proceso en un commit aparte.
8. Regresión: plan único; suite completa 3029 passed + 4 skipped.
9. SPEC achievement: 17/17 met.

### Lessons
- AppTest ejecuta el cuerpo de todas las pestañas: una pestaña no debe hacer E/S ni cálculo sin clics.
- Pasar el proveedor como callable (`data_provider()` construye YahooProvider y traga excepciones): en tests usar un espía que registre llamadas.
- `.cache_datos` está ignorada por git: detectar fugas con sha256 de `find .cache_datos -type f -printf '%p %s %T@\n' | sort` y rebasear por sesión (los servidores Streamlit del usuario también escriben ahí).
- Los cambios de UI asistidos por IA pueden refactorizar el estado en silencio: ejecutar siempre la suite completa tras cambios visuales.

### Forward Preview

#### Test Infra Found
`tests/synthetic.py` (series GBM, regímenes, saltos), `FakeProvider` con parámetros de histórico e `history_calls`, espía de proveedor, huella de caché.

#### Blast Radius Changes
Módulos nuevos `opciones/calibration.py`, `opciones/backtest.py`, `datos/history_cache.py`, `datos/history_service.py`, `ui_backtest.py`; `app.py` con 4.ª pestaña y rediseño visual; motor existente intacto.

#### Commands to Stay Green
`.venv/bin/pytest -q` (3029 passed + 4 skipped); `LIVE_DATA=1 .venv/bin/pytest tests/test_datos_live.py -q` (opcional, requiere red).

#### Dependency Changes
Ninguno.

### Context Audit
- `process/context/all-context.md`: actualizado (estructura, 4.ª pestaña, rediseño, comportamientos C2, lecciones, abiertos, metadatos).
- `process/context/tests/all-tests.md`: actualizado (archivos nuevos, 3029 + 4, huella, tolerancias de oráculos, huecos).
- `process/context/planning/all-planning.md`: revisado, sin cambios.
