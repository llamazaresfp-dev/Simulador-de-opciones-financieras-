---
name: etapa-c2-historico-backtest SPEC
description: "SPEC (requisitos de producto) de la Etapa C2 de Laboratorio de Opciones: histórico del subyacente y pestaña Backtest que responde '¿se cumplen las probabilidades de la app?' (calibración de la PoP + diagnóstico de colas)."
date: 21-11-26
status: draft-para-revisión
---

# SPEC: Etapa C2 — Histórico del subyacente y calibración (Backtest)

**TL;DR:** una pestaña nueva "Backtest" toma años de precios diarios reales del subyacente (de la lista curada de C1), y para muchas fechas del pasado calcula "la probabilidad de ganar (PoP) que la app habría dicho ese día" para una plantilla (p. ej. iron condor). Luego mira qué pasó de verdad y compara: **si la app dice 70 %, ¿se gana ~70 % de las veces?** Es un estudio de **calibración de probabilidades**, no de rentabilidad real (no hay precios históricos de opciones). Incluye un diagnóstico de colas ("¿los movimientos reales tienen colas más gordas que la normal?"). El motor existente no cambia. Nada pesado corre sin pulsar un botón. Los valores marcados como "propuestos" son ajustables en la revisión del usuario.

## Summary

La app calcula una PoP con un modelo (lognormal, volatilidad constante). Pero nadie ha comprobado si esa PoP "acierta" en el mundo real. La Etapa C2 añade el histórico de precios diarios del subyacente (Yahoo Finance, gratis, detrás de una interfaz de proveedor intercambiable como en C1, con caché local) y una pestaña **Backtest**. El usuario elige una plantilla, un horizonte (p. ej. 30 días), una ventana de volatilidad y cuántos años usar. La app recorre fechas pasadas t: con solo datos conocidos hasta t (sin mirar el futuro) calcula la PoP de la plantilla, y mira el precio en t+H para ver si la estrategia habría ganado. Agrupa por la PoP predicha (por tramos de 10 %) y muestra el **gráfico de fiabilidad**: puntos cerca de la diagonal = la app está bien calibrada. Muestra también el puntaje de Brier, el número de casos y el número **efectivo** de casos independientes (las ventanas se solapan, así que hay menos información de la que parece), y un histograma de colas. Aviso permanente: mide **calibración de probabilidades, no ganancias reales**. Herramienta de estudio, no asesoría.

## User Stories / Jobs To Be Done

| # | Historia |
|---|---|
| C2-US1 | Como aprendiz, quiero **cargar años de histórico diario de un subyacente de la lista curada** (y guardarlo en caché), para estudiar el pasado sin depender de internet cada vez. |
| C2-US2 | Como usuario, quiero **elegir una plantilla, el horizonte, la ventana de volatilidad y los años**, para probar distintas situaciones. |
| C2-US3 | Como usuario, quiero ver un **gráfico de fiabilidad** ("PoP predicha vs. frecuencia real de ganar"), para saber si puedo fiarme de la PoP de la app. |
| C2-US4 | Como usuario, quiero saber **cuántos casos hay y cuántos son realmente independientes**, para no creerme un resultado con demasiada confianza. |
| C2-US5 | Como usuario, quiero un **diagnóstico de colas** (¿los movimientos extremos son más frecuentes que en la normal?), para entender por qué la PoP falla donde falla. |
| C2-US6 | Como usuario, quiero que el estudio **no mire el futuro** (volatilidad, tasa y dividendos solo con datos hasta la fecha t), para que el resultado sea honesto. |
| C2-US7 | Como usuario, quiero **avisos claros** de qué mide y qué no mide el backtest (no es rentabilidad real), y que **nada pesado corra solo**: solo al pulsar los botones. |
| C2-US8 | Como usuario, quiero que todo lo existente (constructor, C1, modelos) **siga funcionando igual**. |

## What The User Wants (Behavioral Outcomes)

- **Pestaña nueva "Backtest"** junto a Catálogo / Constructor / Ajustes. Usa el ticker elegido en la barra lateral. Con "Entrada manual" muestra un mensaje pidiendo elegir un ticker de la lista curada.
- **Controles dentro de la pestaña (valores propuestos):** plantilla (una de las 8 del catálogo; por defecto iron condor), horizonte H en días naturales (por defecto 30; editable 7–120), ventana de volatilidad W en días de negociación (por defecto 30), paso entre fechas (por defecto 5 días de negociación), años de histórico (por defecto 10), y un interruptor "incluir comisiones" (por defecto sí, con los valores actuales de Ajustes).
- **Dos botones:** "Cargar histórico" (descarga y guarda en caché) y "Calcular" (ejecuta el backtest). Sin pulsarlos no se descarga ni se calcula nada. El resultado se recuerda mientras no cambien los parámetros.
- **Qué calcula en cada fecha t:** con datos hasta t estima la volatilidad (realizada W días), la tasa r y el dividend yield q; construye la plantilla con las reglas del catálogo, calcula la PoP con la fórmula exacta de la app (Black-Scholes) y mira el precio del subyacente en el vencimiento. "Ganar" = P&L al vencimiento > 0 (con comisiones si se incluyen). Las fechas donde los datos no son válidos se saltan.
- **Resultados:**
  - Gráfico de fiabilidad (eje x = PoP predicha, eje y = frecuencia real de ganar, línea y = x, puntos con barras de error por tramo).
  - Tabla por tramo (decil): PoP media predicha, frecuencia observada, intervalo, nº de casos.
  - Puntaje de Brier, nº de casos N y nº **efectivo** de casos (≈ años analizados / H), con aviso de que los intervalos ingenuos son demasiado estrechos por el solapamiento.
  - Una **segunda línea opcional** con la PoP calculada con la tendencia histórica real μ (en vez de la neutral al riesgo r − q), para ver cuánto pesa esa diferencia.
  - Diagnóstico de colas: histograma de los rendimientos estandarizados de H días frente a la normal, curtosis y cuantiles de cola.
- **Avisos fijos:** volatilidad realizada ≠ implícita (prima de riesgo de volatilidad); opciones americanas valoradas como europeas; dividendos aproximados con el rendimiento de los últimos 12 meses; **no hay precios históricos de opciones: se mide calibración, no rentabilidad real**; "estudio, no asesoría".
- **Sin internet:** con histórico en caché se puede calcular (se muestra la antigüedad); sin caché y sin red, mensaje en español.
- **Sin cambios:** el motor, el constructor, C1, los modelos, Monte Carlo y gráficos funcionan igual.

## Flow / State Diagram

```
[Barra lateral: ticker curado]            [Entrada manual] --> "elige un ticker curado"
        |
        v
[Pestaña Backtest: plantilla, H, W, paso, años, comisiones]
        |
        v
[Botón "Cargar histórico"] --> {¿caché al día?}
        | no / sin caché                     | sí --> [usa caché + antigüedad]
        v
{¿fuente responde?} -- no --> [mensaje ES] --> {¿hay caché?} sí --> [usa caché]
        | sí                                         | no --> [aviso, nada que calcular]
        v
[guarda caché] --> [aviso si el histórico es más corto que lo pedido]
        |
        v
[Botón "Calcular"]
        |
        v
Para cada fecha t (cada "paso" días de negociación):
   [vol, r, q solo con datos <= t] --> [plantilla] --> [PoP exacta (BS)]
   [precio en el último día de negociación <= t+H] --> [¿ganó? (P&L > 0)]
   (fecha inválida --> se salta)
        |
        v
[agrupar por tramos de PoP] --> [fiabilidad + Wilson + Brier + N / N efectivo]
[rendimientos H-días estandarizados] --> [diagnóstico de colas]
        |
        v
[gráficos, tabla, avisos fijos]   (resultado en caché de sesión)
```

## Acceptance Criteria (Testable Outcomes)

Escenarios tomados de `process/context/tests/all-tests.md`: pytest sobre código puro con **series sintéticas con respuesta conocida** (oráculos independientes) y **proveedor falso** (sin red); la interfaz con el smoke test AppTest (corre todos los cuerpos de pestaña, por eso nada pesado corre sin botón); lo visual, manualmente; pruebas con datos reales, solo opcionales.

**Histórico y caché**
- **AC-C2-1:** Un proveedor de histórico (interfaz separada de la de C1, que no cambia) entrega precios diarios (cierre, cierre ajustado, dividendos) de un ticker curado entre dos fechas; el proveedor falso entrega una serie sintética determinista (con semilla). Rango o ticker sin datos produce un error claro en español (no un DataFrame vacío silencioso); el límite de solicitudes y la falta de red tienen mensajes específicos.
  proven by: historial-proveedor-falso-determinista + historial-vacío-error-español + historial-sin-red + historial-límite-solicitudes (tests con proveedor falso)
  strategy: Fully-Automated
- **AC-C2-2:** La fila del día actual (posiblemente parcial con el mercado abierto) se descarta; las demás filas válidas se conservan; filas con precio NaN, negativo o fechas duplicadas se descartan sin romper la carga.
  proven by: fila-de-hoy-descartada + filas-sucias-descartadas (tests con fixtures)
  strategy: Fully-Automated
- **AC-C2-3:** El histórico se guarda en una caché local propia (carpeta ya ignorada por git, un archivo por ticker, versión de esquema propia, escritura atómica); se vuelve a descargar completo si la caché tiene más de 1 día de mercado; sin red se usa la caché mostrando su antigüedad; sin caché ni red, aviso y nada que calcular.
  proven by: historial-caché-escribe-y-lee + historial-caché-caducada-redescarga + historial-sin-red-usa-caché + historial-sin-red-sin-caché + carpeta-ignorada-por-git (tests con reloj y proveedor falsos)
  strategy: Fully-Automated
- **AC-C2-4:** Si el histórico disponible es más corto que los años pedidos, se muestra un aviso con los años reales disponibles y el backtest usa lo que hay.
  proven by: historial-corto-aviso (tests; smoke AppTest)
  strategy: Fully-Automated

**Sin mirar el futuro y reglas de fechas**
- **AC-C2-5:** En cada fecha t, la volatilidad (desviación típica de los log-rendimientos diarios del cierre ajustado de las últimas W sesiones × √252), r y q usan solo datos con fecha ≤ t. Cambiar datos posteriores a t no altera el resultado de esa fecha.
  proven by: vol-realizada-igual-a-cálculo-manual + sin-mirar-futuro-datos-posteriores-no-cambian-resultado (tests puros con oráculo)
  strategy: Fully-Automated
- **AC-C2-6:** El precio de vencimiento es el cierre (sin ajustar por dividendos) del **último día de negociación en o antes de t+H** (días naturales). Se muestrean fechas cada "paso" sesiones; las fechas sin vencimiento disponible (cola final de la serie) o sin ventana suficiente (inicio) se saltan.
  proven by: regla-vencimiento-último-día-≤-t+H + muestreo-por-paso + cola-y-arranque-saltados (tests con calendarios pequeños, incluyendo fines de semana y festivos)
  strategy: Fully-Automated
- **AC-C2-7:** Para cada fecha, el backtest fuerza Black-Scholes (no binomial), construye la plantilla con las reglas existentes, valida el mercado con la validación existente (las fechas que fallan se saltan y se cuentan), calcula la PoP exacta existente y define "ganar" como P&L al vencimiento > tolerancia cero, con comisiones según el interruptor.
  proven by: backtest-fuerza-bs + plantilla-reusa-build-legs + fecha-inválida-saltada-y-contada + ganar-con-comisiones + ganar-sin-comisiones (tests puros)
  strategy: Fully-Automated
- **AC-C2-8:** La tasa r de cada fecha sale del histórico de letras a 13 semanas (^IRX, en porcentaje, convertido a fracción) hasta t; si no hay histórico de la tasa, se usa la r actual de la barra lateral con un aviso. q de cada fecha = dividendos de los 12 meses previos / precio en t (0 para el índice, con nota).
  proven by: r-histórica-conversión-porcentaje + r-respaldo-constante-con-aviso + q-12-meses-previos + q-índice-cero-con-nota (tests puros con fixtures)
  strategy: Fully-Automated

**Calibración y colas**
- **AC-C2-9:** La calibración agrupa las PoP predichas en deciles y, por tramo, entrega PoP media, frecuencia observada de ganar, intervalo de Wilson y nº de casos; los tramos vacíos o muy pequeños se marcan, no se inventan.
  proven by: bins-por-decil + wilson-valores-conocidos + tramo-vacío-marcado (tests puros)
  strategy: Fully-Automated
- **AC-C2-10:** Con una serie sintética de movimiento browniano geométrico con volatilidad conocida, el backtest queda **cerca de la diagonal** (calibrado dentro de tolerancia estadística), y el puntaje de Brier es consistente con el esperado.
  proven by: oráculo-GBM-calibrado-cerca-de-diagonal + brier-valor-conocido (tests puros con semilla)
  strategy: Fully-Automated
- **AC-C2-11:** Con una serie sintética con saltos (colas gordas), el diagnóstico de colas detecta exceso de curtosis y la PoP de las colas queda mal estimada (descalibración visible), a diferencia del caso GBM.
  proven by: oráculo-saltos-exceso-curtosis + oráculo-saltos-descalibración-colas (tests puros)
  strategy: Fully-Automated
- **AC-C2-12:** Se reporta el N de casos y un N efectivo (≈ años de datos analizados / H), con aviso de solapamiento de ventanas; la segunda línea con μ histórico usa solo datos ≤ t (ventana de 1 año) y se muestra como alternativa a la PoP neutral al riesgo.
  proven by: n-efectivo-fórmula + aviso-solapamiento + mu-histórico-sin-mirar-futuro (tests puros; smoke AppTest)
  strategy: Fully-Automated

**Interfaz**
- **AC-C2-13:** Existe la pestaña "Backtest" con los controles propuestos; **nada pesado corre al abrirla**: la descarga solo con "Cargar histórico" y el cálculo solo con "Calcular". Con "Entrada manual" muestra un mensaje pidiendo un ticker curado.
  proven by: pestaña-backtest-existe + sin-botón-no-calcula + entrada-manual-mensaje (smoke AppTest con proveedor y reloj falsos)
  strategy: Fully-Automated
- **AC-C2-14:** Con datos cargados y "Calcular" pulsado se muestran el gráfico de fiabilidad (línea y = x, puntos con barras de error), la tabla por tramo, Brier, N y N efectivo, los avisos fijos (incluido "no es rentabilidad real" y "estudio, no asesoría") y el histograma de colas; el resultado se reutiliza si los parámetros no cambian.
  proven by: resultados-completos-en-pantalla + avisos-fijos-presentes + resultado-en-caché-de-sesión (smoke AppTest); aspecto-del-gráfico (revisión manual)
  strategy: Hybrid
- **AC-C2-15:** Cálculo en tiempo razonable: un backtest de 10 años con paso 5 (≈ 500 fechas) en Black-Scholes corre en pocos segundos.
  proven by: tiempo-backtest-10-años-paso-5 (test con cota holgada)
  strategy: Hybrid

**Arquitectura y calidad**
- **AC-C2-16:** La lógica de backtest vive en un módulo puro nuevo del motor (solo numpy, sin E/S ni red); los módulos existentes del motor no cambian; `import datos` sigue sin cargar yfinance ni pandas; el acceso a histórico vive en `datos/` detrás de una interfaz sustituible.
  proven by: motor-existente-sin-diff (revisión de diff) + import-datos-sin-yfinance-ni-pandas + motor-importa-sin-streamlit (tests en subproceso) + proveedor-histórico-intercambiable (tests)
  strategy: Hybrid
- **AC-C2-17:** La suite normal **no usa internet** y los **2742 tests existentes (+ 3 omitidos)** siguen en verde sin conexión; los tests nuevos corren sin conexión; las pruebas contra la fuente real (disponibilidad de ^SPX/^GSPC, ^IRX, ^VIX y formato del histórico) son opcionales y quedan omitidas por defecto. Sin dependencias nuevas; `requirements.txt` sin cambios.
  proven by: suite-completa-sin-red (ejecución con red bloqueada) + prueba-en-vivo-histórico-omitida-por-defecto + requirements-sin-diff (revisión de diff)
  strategy: Fully-Automated

## Locked Decisions

Las decisiones del MVP, A, B1 y C1 siguen vigentes. Decisiones nuevas de C2 (derivadas de la intención del usuario y la investigación; las marcadas "propuesta" se revisan abajo):

| # | Decisión |
|---|---|
| C2-1 | C2 = **(a) calibración de la PoP + (c) diagnóstico de colas**. El replay de estrategias (b) queda fuera. |
| C2-2 | Mide **calibración de probabilidades, NO rentabilidad real**: no hay precios históricos de opciones (eso sería C3, de pago). Aviso permanente. |
| C2-3 | **Sin mirar el futuro:** vol, r, q (y μ) solo con datos ≤ t. |
| C2-4 | Backtest siempre con **Black-Scholes** (el binomial tardaría ~3 min por plantilla; BS ≈ 2,7 ms por fecha). Opciones americanas valoradas como europeas, con aviso. |
| C2-5 | Ganar = P&L al vencimiento > tolerancia cero con el **cierre sin ajustar**; el cierre ajustado solo para rendimientos/volatilidad. |
| C2-6 | Histórico detrás de una **interfaz separada** de la de C1 (la de C1 no se toca); datos diarios de Yahoo, la fila de hoy se descarta. |
| C2-7 | Los resultados se muestran con **N y N efectivo** y aviso de solapamiento (los intervalos ingenuos engañan). |
| C2-8 | **Nada pesado sin pulsar botón** (AppTest ejecuta todas las pestañas). |

### Valores propuestos, ajustables en la revisión del usuario

| # | Parámetro | Valor propuesto |
|---|---|---|
| 1 | Volatilidad | Realizada de 30 sesiones para todos los tickers; comparación con VIX para SPX/SPY queda como futuro |
| 2 | Deriva | PoP neutral al riesgo (r − q) como línea principal + segunda línea con μ histórico (media de log-rendimientos de los últimos 252 sesiones hasta t) |
| 3 | Horizonte H / paso / histórico | 30 días naturales (editable 7–120) / 5 sesiones / 10 años |
| 4 | Plantilla | Una a la vez de las 8 del catálogo; por defecto iron condor |
| 5 | Comisiones | Incluidas con los valores actuales de Ajustes; interruptor para excluir |
| 6 | Alcance | Calibración + colas; replay de estrategia fuera |
| 7 | Almacenamiento | `.cache_datos/history/<TICKER>.json`, sin caducidad dura (se redescarga si tiene más de 1 día de mercado); antigüedad visible |
| 8 | Tickers | Los mismos 11 de C1; aviso si el histórico es más corto; símbolo del índice (^SPX, con respaldo ^GSPC) decidido tras una prueba en vivo |
| 9 | r y q históricos | r: ^IRX por fecha (respaldo: r constante de la barra lateral con aviso); q: dividendos 12 meses previos / precio en t; índice: q = 0 con nota |
| 10 | Vencimiento | Último día de negociación en o antes de t+H |
| 11 | Tramos | Deciles de PoP predicha; mínimo de casos por tramo para mostrarlo sin marca: 10 |
| 12 | N efectivo | ≈ años analizados / H (aprox. de ventanas no solapadas) |

## Out Of Scope

- Replay de la estrategia / curva de P&L histórico (opción b) y cualquier afirmación de rentabilidad real.
- Histórico de precios de opciones (C3, de pago).
- Comparación de volatilidad realizada contra VIX (queda como mejora futura).
- Varios tickers a la vez, optimización de parámetros, o recomendación de estrategias.
- Modelo binomial en el backtest; dividendos discretos; superficie de volatilidad.
- Tickers fuera de la lista curada; datos intradía; datos en tiempo real.
- Cambios en los módulos existentes del motor, en Monte Carlo o en las métricas.
- Operar, órdenes, bróker; asesoría de inversión.
- Comisión de cierre racional (B2, diferida).

## Constraints

- **Usuario:** nivel básico de Python; código sencillo; explicaciones cortas; interfaz en español con términos de opciones en inglés; herramienta de uso personal.
- **Proceso:** cálculo en módulo puro (sin E/S); histórico en `datos/`; la app solo dibuja. Identificadores en inglés, comentarios/docstrings/UI en español. Tests con `.venv/bin/pytest`; floats con `pytest.approx`; suite sin red.
- **Técnico:** Python 3.12; numpy 2.5.5; yfinance 1.8.0 y pandas 3.1.1 ya fijados (sin dependencias nuevas, `requirements.txt` sin cambios); el módulo nuevo del motor solo usa numpy; `MarketDataProvider` de C1 no se modifica; `import datos` no carga yfinance ni pandas; Yahoo es no oficial y puede limitar solicitudes; ~2500 filas por 10 años, 1 solicitud por ticker.
- **Regresión:** los 2742 tests existentes (+ 3 omitidos) siguen en verde sin conexión.

## Open Questions

None bloqueantes. Los valores propuestos de la tabla anterior se aprueban o ajustan en la revisión del usuario. Quedan **verificaciones en vivo opcionales** (siguiente fase, coste: live-provider, opt-in): disponibilidad de historial de ^SPX frente a ^GSPC, de ^IRX y de ^VIX. Ningún criterio depende de ellas: el símbolo del índice y el respaldo de r (AC-C2-8) tienen salida definida en caso de fallo.

## Background / Research Findings

- **yfinance 1.8.0 (sin verificación en red):** `Ticker.history(start, end, interval='1d')`; inicio inclusivo, fin exclusivo; solo días de negociación; la fila de hoy puede ser parcial con el mercado abierto; un ticker o rango sin datos devuelve un DataFrame **vacío en silencio**, de ahí el error propio; el límite de solicitudes ya se traduce a nuestro error. Se usa sin ajuste automático y con acciones: **Close** (ajustado por splits, no por dividendos; para el payoff), **Adj Close** (rendimientos y volatilidad) y **Dividends**. ~2500 filas por 10 años; 1 solicitud por ticker.
- **Sin verificar:** disponibilidad de historial para ^SPX (^GSPC es el canónico), ^IRX (porcentaje) y ^VIX; prueba en vivo opcional.
- **Motor:** `build_legs`, `exact_pop`, `pnl_expiry`, `CommissionSettings` y `validate_market` se reutilizan tal cual. Black-Scholes ≈ 2,7 ms por fecha; el binomial ≈ 3 min por plantilla (descartado).
- **Trampas que el SPEC cubre:** ventanas solapadas (intervalos ingenuos demasiado estrechos → N efectivo y aviso); mirar el futuro (vol, q, r solo ≤ t); deriva neutral al riesgo frente a deriva real (segunda línea); dividendos aproximados con los 12 meses previos; opciones americanas valoradas como europeas; volatilidad realizada ≠ implícita; sin precios históricos de opciones: mide calibración, no rentabilidad.
- **Oráculos de prueba:** GBM sintético con volatilidad conocida → cerca de la diagonal; serie con saltos → colas mal estimadas.
- Fuentes: `DISENO.md`, SPEC de C1, `process/context/all-context.md`, `process/context/tests/all-tests.md`, investigación de vc-research-agent.

### Known gaps / Risks

| # | Riesgo o hueco | Tratamiento |
|---|---|---|
| C2-G1 | **Solapamiento de ventanas:** la muestra efectiva es pequeña; los intervalos ingenuos engañan. | N efectivo y aviso visibles (AC-C2-12); decisión C2-7. |
| C2-G2 | **Volatilidad realizada ≠ implícita:** la PoP con vol realizada no es la de mercado. | Aviso fijo (AC-C2-14); comparación con VIX queda para el futuro. |
| C2-G3 | **Sin precios históricos de opciones:** no se mide rentabilidad real. | Aviso permanente (C2-2); C3 en la hoja de ruta. |
| C2-G4 | **Americanas como europeas; q aproximado:** pequeños sesgos. | Aviso fijo; decisión C2-4. |
| C2-G5 | **Historial de ^SPX/^IRX/^VIX sin verificar.** | Prueba en vivo opcional; respaldos definidos (^GSPC; r constante con aviso). |
| C2-G6 | **Yahoo no oficial / 429 / filas sucias o vacías.** | Error propio en vacío, mensajes específicos, caché, descarte de filas (AC-C2-1…3). |
| C2-G7 | **Resultado dependiente del periodo** (p. ej. 10 años alcistas). | El usuario ve el rango de fechas usado; no se generaliza. |
| C2-G8 | **Sin tests visuales ni de persistencia entre pestañas** (hueco heredado). | Smoke AppTest + revisión manual. |
| C2-G9 | **Tiempo de cálculo** si el usuario baja el paso a 1 sesión. | AC-C2-15 y barra de progreso/aviso; paso mínimo documentado en PLAN. |

## Definition of Done (Etapa C2)

- Los 17 criterios AC-C2-1…AC-C2-17 se cumplen; los Hybrid pasan además la revisión manual del usuario.
- Los 2742 tests existentes (+ 3 omitidos) siguen en verde **sin conexión**; los tests nuevos corren sin conexión con series sintéticas y proveedor falso.
- La app arranca con `.venv/bin/streamlit run app.py`: la pestaña Backtest carga histórico y calcula solo con los botones, y muestra el gráfico de fiabilidad, Brier, N/N efectivo, avisos y el histograma de colas.
- Módulos existentes del motor sin cambios; sin dependencias nuevas.
- Valores propuestos aprobados o ajustados por el usuario al revisar el SPEC.
