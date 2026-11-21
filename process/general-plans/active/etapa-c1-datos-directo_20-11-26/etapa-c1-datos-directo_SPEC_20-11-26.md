---
name: etapa-c1-datos-directo SPEC
description: "SPEC bloqueado (requisitos de producto) de la Etapa C1 de Laboratorio de Opciones: datos de mercado en directo (con ~15 min de retraso) en el constructor, solo para subyacentes de una lista curada y solo opciones líquidas."
date: 20-11-26
status: locked
---

# SPEC: Etapa C1 — Datos de mercado en directo en el constructor

**TL;DR:** en el selector "Tipo de subyacente" el usuario elige Acción / ETF / Índice y luego un **ticker de una lista corta de subyacentes muy líquidos**. Al pulsar "Cargar datos", la app rellena precio (spot), tasa (r) y dividend yield (q) y ofrece **solo vencimientos y strikes líquidos** de la cadena real. La prima es el **mid (bid+ask)/2** y la volatilidad implícita se calcula con nuestro propio motor. Datos con ~15 min de retraso; se guardan en una caché local para ver lo último cargado sin internet. Histórico y backtest (C2) quedan para otro ciclo. Las preguntas están resueltas (20-11-26); los valores marcados como "propuestos" son ajustables en la revisión del usuario.

## Summary

Hasta ahora el usuario escribe a mano precio, volatilidad, tasa y dividendos. La Etapa C1 conecta el constructor con datos reales de mercado: el usuario elige un subyacente conocido y muy líquido (p. ej. SPY, AAPL, SPX), la app trae el precio actual, la tasa libre de riesgo y el dividend yield, y muestra las opciones reales (vencimientos y strikes) con su prima de mercado. Para no enseñar números engañosos, **solo se ofrecen opciones líquidas**: con bid y ask válidos, spread estrecho, interés abierto suficiente y cerca del precio actual. Los datos vienen de una fuente gratuita (Yahoo Finance, uso personal, con ~15 min de retraso), detrás de una interfaz que permite cambiar de proveedor más adelante sin tocar el motor. La app guarda lo último cargado en una caché local para funcionar sin internet. El motor de cálculo no cambia. Sigue siendo una herramienta de estudio, no asesoría ni trading.

## User Stories / Jobs To Be Done

| # | Historia |
|---|---|
| C-US1 | Como aprendiz, quiero **elegir un subyacente real de una lista de los más conocidos y líquidos** desde el selector "Tipo de subyacente", para practicar con situaciones reales sin buscar tickers raros. |
| C-US2 | Como usuario, quiero que al **cargar datos** se rellenen solos precio, tasa y dividend yield (editables), para no escribirlos a mano. |
| C-US3 | Como usuario, quiero ver **solo vencimientos y strikes con buena liquidez**, para no armar estrategias con opciones que en la práctica no se pueden operar. |
| C-US4 | Como usuario, quiero que la **prima de cada pata sea el mid (bid+ask)/2** de la cadena, para que sea un precio razonable y no un último precio viejo. |
| C-US5 | Como usuario, quiero que la **volatilidad implícita** se calcule con el mismo modelo de la app (y ver la de Yahoo solo como referencia), para que todo sea coherente. |
| C-US6 | Como usuario, quiero saber **de cuándo son los datos** ("~15 min de retraso; cargados a las HH:MM"), para no confundirlos con tiempo real. |
| C-US7 | Como usuario, quiero que la app **siga funcionando sin internet** mostrando lo último cargado, y **mensajes claros en español** si la fuente falla o me limita. |
| C-US8 | Como usuario, quiero que lo que ya existe (entrada manual, patas, gráficos, modelos) **siga funcionando igual** si no cargo datos. |

## What The User Wants (Behavioral Outcomes)

- **Selector en cascada:** el selector "Tipo de subyacente" sigue existiendo (Acción / ETF / Índice). Debajo aparece un segundo selector con los **tickers de la lista curada** para ese tipo, más la opción de **entrada manual** (como ahora).
- **Lista curada (valores propuestos, ajustables en la revisión):** Índice: SPX; ETF: SPY, QQQ, IWM; Acción: AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA. No se puede escribir un ticker fuera de la lista.
- **Botón "Cargar datos":** trae el precio actual y rellena el spot; rellena la tasa (r) con la tasa de letras del Tesoro a 13 semanas y el dividend yield (q) con el rendimiento por dividendos anual reciente. Para índices, q usa el valor manual por defecto. Todo sigue **editable**.
- **Vencimientos y strikes ofrecidos:** solo los que pasan los filtros de liquidez (tabla de valores propuestos abajo). Si un vencimiento no tiene ninguna opción que pase, **no se ofrece**. Las opciones poco líquidas **no aparecen** (no se muestran con aviso: simplemente no se ofrecen).
- **Prima:** al elegir una opción real, la prima de la pata es el **mid (bid+ask)/2**. Se muestran bid, ask y mid. No se usa "último precio" para opciones seleccionables.
- **Volatilidad implícita:** se recalcula con el motor (Black-Scholes europeo para Índice; binomial americano para Acción/ETF, según el modelo de la Etapa B1). La IV de Yahoo se muestra solo como referencia, rotulada así.
- **Antigüedad:** un texto visible dice "datos con ~15 min de retraso; cargados a las HH:MM".
- **Sin internet o error:** si la fuente falla, limita (demasiadas solicitudes) o no hay red, un mensaje en español lo explica y la app muestra **lo último guardado en la caché** (indicando su hora) si existe; si no existe, la entrada manual sigue disponible.
- **Sin cambios:** el motor, los modelos, los gráficos, el Monte Carlo y la entrada manual funcionan igual. Los precios automáticos de patas siguen usando el modelo; solo las patas elegidas de la cadena real usan el mid.

## Flow / State Diagram

```
[Barra lateral] --> {Tipo de subyacente: Acción / ETF / Índice}
        |
        v
{Ticker de la lista curada  o  Entrada manual}
        |                              |
        | ticker                       +--> [flujo manual de siempre]
        v
[Botón "Cargar datos"]
        |
        v
{¿fuente responde?}
   | no (sin red / límite / error)
   |     +--> [mensaje en español] --> {¿hay caché?} sí --> [muestra último guardado + su hora]
   |                                        | no --> [entrada manual sigue disponible]
   | sí
   v
[spot, r (^IRX), q (dividendos)] --> rellena y deja editar
   |
   v
[cadena de opciones] --> [filtros de liquidez]
   |   bid>0 y ask>0 | interés abierto | spread | strikes ±20 % | 7–120 días
   v
{¿vencimiento con al menos una opción que pasa?}
   | no --> [no se ofrece]
   | sí --> [se ofrece vencimiento + strikes líquidos]
                |
                v
        [usuario elige pata] --> [prima = mid] --> [IV recalculada por el motor; IV de Yahoo = referencia]
                |
                v
        [constructor / análisis de siempre] + [texto "~15 min de retraso; cargados a las HH:MM"]
   (cada carga exitosa se guarda en la caché local)
```

## Acceptance Criteria (Testable Outcomes)

Escenarios tomados de `process/context/tests/all-tests.md`: pytest sobre código puro con **fixtures grabadas** y un **proveedor falso** (sin red); la interfaz con el smoke test AppTest; lo visual, manualmente. Cualquier prueba con datos reales es **opcional** (activada a propósito) y no forma parte de la suite normal.

**Selección de subyacente**
- **AC-C1-1:** El selector "Tipo de subyacente" sigue con Acción / ETF / Índice y debajo ofrece los tickers de la lista curada de cada tipo (valores propuestos) más "entrada manual"; no admite tickers fuera de la lista.
  proven by: lista-curada-por-tipo + ticker-fuera-de-lista-rechazado (tests de lógica); selectores-en-cascada (smoke AppTest)
  strategy: Hybrid
- **AC-C1-2:** Con "entrada manual" (o sin cargar nada) la app se comporta exactamente como antes de C1.
  proven by: modo-manual-sin-cambios (smoke AppTest + regresión de tests existentes)
  strategy: Fully-Automated

**Carga de mercado**
- **AC-C1-3:** "Cargar datos" rellena spot con el último precio del proveedor; el spot, r y q siguen siendo editables a mano después.
  proven by: carga-rellena-spot + valores-editables-tras-carga (tests con proveedor falso; smoke AppTest)
  strategy: Fully-Automated
- **AC-C1-4:** La tasa r se obtiene de la tasa de letras a 13 semanas (el proveedor la da en porcentaje, p. ej. 4,12) y se convierte correctamente al formato de la app; el dividend yield q se obtiene del rendimiento por dividendos anual reciente (fracción); si no hay dato (índices o ausente) q usa el valor manual por defecto y se avisa.
  proven by: conversión-tasa-porcentaje-a-fracción + q-desde-dividendos-reciente + q-índice-valor-por-defecto + q-ausente-con-aviso (tests con fixtures)
  strategy: Fully-Automated

**Liquidez y cadena**
- **AC-C1-5:** Una opción es seleccionable solo si cumple todos los filtros: bid > 0 y ask > 0; interés abierto ≥ 100; spread relativo (ask − bid)/mid ≤ 10 % (o spread absoluto ≤ 0,10 USD si mid < 1 USD); strike dentro de ±20 % del spot; vencimiento entre 7 y 120 días. Los umbrales son valores propuestos y viven en un único lugar configurable.
  proven by: filtro-bid-ask-válidos + filtro-interés-abierto + filtro-spread-relativo + filtro-spread-absoluto-mid-menor-1 + filtro-strikes-±20% + filtro-vencimientos-7-120 + umbrales-en-un-solo-lugar (tests con tablas de casos en el borde)
  strategy: Fully-Automated
- **AC-C1-6:** Las opciones que no pasan los filtros **no se ofrecen** en ninguna parte de la interfaz; un vencimiento sin ninguna opción que pase no se ofrece. Con una cadena real grabada de baja liquidez (p. ej. con muchos bid = 0) no aparece ninguna de esas opciones.
  proven by: opciones-ilíquidas-no-ofrecidas + vencimiento-vacío-no-ofrecido + fixture-cadena-con-bid-cero (tests; smoke AppTest)
  strategy: Fully-Automated
- **AC-C1-7:** La prima de una pata elegida de la cadena es el mid (bid+ask)/2; nunca se usa el último precio operado, aunque exista y sea distinto (p. ej. un último precio viejo muy alejado del mid).
  proven by: prima-igual-mid + último-precio-ignorado-con-fixture-viejo (tests)
  strategy: Fully-Automated

**Volatilidad implícita**
- **AC-C1-8:** La IV mostrada para una opción real se recalcula con el motor (Black-Scholes para Índice; binomial americano para Acción/ETF), usando el mid como prima, y reproduce la prima: precio del motor con esa IV ≈ mid. La IV de Yahoo se muestra solo como referencia, con rótulo distinto, y nunca se usa en el cálculo.
  proven by: iv-motor-ida-y-vuelta-con-mid + iv-yahoo-solo-referencia (tests con fixtures); rótulo-referencia (smoke AppTest)
  strategy: Fully-Automated

**Antigüedad, caché y errores**
- **AC-C1-9:** Tras una carga se muestra el texto "datos con ~15 min de retraso; cargados a las HH:MM" con la hora real de la carga (o la de la caché cuando se muestran datos guardados).
  proven by: texto-antigüedad-con-hora (tests con reloj falso; smoke AppTest)
  strategy: Fully-Automated
- **AC-C1-10:** Cada carga exitosa se guarda en una caché local en una carpeta ignorada por git; con el proveedor sin red, la app muestra lo último guardado indicando su hora; sin caché, avisa y deja la entrada manual.
  proven by: caché-escribe-y-lee + sin-red-usa-caché + sin-red-sin-caché-aviso + carpeta-caché-ignorada-por-git (tests con proveedor falso que falla; revisión de ignorados)
  strategy: Fully-Automated
- **AC-C1-11:** Los fallos del proveedor (sin red, límite de solicitudes, respuesta vacía o rota, mercado cerrado/fin de semana sin datos frescos) producen **mensajes específicos en español**, nunca excepciones visibles ni números inventados ni NaN.
  proven by: error-red + error-límite-solicitudes + respuesta-vacía + mercado-cerrado (tests con proveedor falso); mensajes-en-pantalla (smoke AppTest)
  strategy: Hybrid
- **AC-C1-12:** Datos malformados o incoherentes de la fuente (columnas ausentes, strikes duplicados, bid > ask, precios negativos o NaN) se descartan por opción, sin romper la carga del resto.
  proven by: fixture-datos-sucios-descartados + bid-mayor-que-ask-descartado (tests)
  strategy: Fully-Automated

**Arquitectura y calidad**
- **AC-C1-13:** El acceso a datos vive en un paquete nuevo, fuera del motor puro; el motor sigue importándose sin Streamlit, sin red y sin librerías de datos, y no cambia. Existe una interfaz de proveedor que se puede sustituir por otro (o por uno falso) sin tocar el motor ni el resto de la lógica.
  proven by: motor-importa-sin-red-ni-datos (test en subproceso); proveedor-falso-intercambiable (tests); motor-sin-diff (revisión de diff)
  strategy: Hybrid
- **AC-C1-14:** La suite normal **no usa internet**: los tests corren con fixtures grabadas y proveedor falso, y pasan con la red desactivada. Cualquier prueba contra la fuente real es opcional (activada a propósito) y queda fuera de la ejecución normal.
  proven by: suite-completa-sin-red (ejecución con red bloqueada) + prueba-en-vivo-omitida-por-defecto (marcador opcional)
  strategy: Fully-Automated
- **AC-C1-15:** Las dependencias nuevas quedan con **versiones fijadas** (la librería de datos, lo que requiere y pandas si no estaba), y la app arranca con ellas.
  proven by: requirements-con-versiones-fijadas (revisión de diff) + instalación-limpia-y-arranque (ejecución de pytest + smoke AppTest)
  strategy: Hybrid
- **AC-C1-16:** Los **2330 tests existentes** (+ 2 omitidos) siguen en verde sin conexión; los tests nuevos también corren sin conexión; las decisiones del MVP, A y B1 siguen vigentes salvo lo cambiado aquí.
  proven by: ejecución completa de `.venv/bin/pytest` (puerta de EXECUTE)
  strategy: Fully-Automated

## Locked Decisions (20-11-26)

Las decisiones 1–14 del MVP, A1–A11 y B1–B6 siguen vigentes salvo lo cambiado abajo.

| # | Decisión |
|---|---|
| C1 | Fuente de datos: Yahoo Finance mediante `yfinance`, **detrás de una interfaz de proveedor intercambiable** (otro proveedor podrá sustituirlo sin tocar el motor). Herramienta de uso personal. |
| C2 | Se aceptan dependencias nuevas con **versiones fijadas** (yfinance y lo que requiere; pandas si no estuviera). Las versiones exactas se deciden en PLAN. |
| C3 | Prima = **mid (bid+ask)/2**. Como solo se ofrecen opciones con bid y ask válidos (C6), el "último precio" no se usa nunca como respaldo para opciones seleccionables. |
| C4 | Volatilidad implícita **recalculada con nuestro motor** (Black-Scholes europeo para Índice; binomial americano para Acción/ETF). La IV de Yahoo se muestra solo como referencia. |
| C5 | Caché local en una carpeta **ignorada por git** (CSV/JSON): la app muestra lo último cargado sin internet y los tests nunca necesitan internet. |
| C6 | **Solo opciones líquidas:** las poco líquidas no se ofrecen (no basta con avisar). La app ofrece solo los subyacentes más líquidos y, dentro de ellos, solo opciones que pasan los filtros de liquidez. |
| C7 | **Selección desde "Tipo de subyacente":** el usuario elige tipo (Acción / ETF / Índice) y luego un ticker de la lista curada; cargar rellena spot, tasa y dividend yield y ofrece vencimientos/strikes de la cadena filtrada. |
| C8 | Tasa y dividendos **autorrellenados** y editables: r desde la tasa de letras a 13 semanas (^IRX, que llega en porcentaje; se convierte); q desde el rendimiento por dividendos anual reciente (fracción); índices: q = valor manual por defecto. |
| C9 | Capa de datos en un **paquete nuevo de nivel superior** (p. ej. `datos/`), fuera del motor puro `opciones/` (sin E/S, sin cambios). Tests con fixtures grabadas y proveedor falso; sin red en la suite normal; cualquier prueba en vivo es opcional. |

### Valores propuestos, ajustables en la revisión del usuario

| Parámetro | Valor propuesto |
|---|---|
| Índice | SPX (^SPX) |
| ETF | SPY, QQQ, IWM |
| Acciones | AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA |
| Excluidos por mala liquidez | NDX, RUT (muchos bid = 0); podrán añadirse si pasan los filtros |
| Cotización válida | bid > 0 y ask > 0 |
| Interés abierto mínimo | ≥ 100 |
| Spread máximo | (ask − bid)/mid ≤ 10 %, o spread absoluto ≤ 0,10 USD si mid < 1 USD |
| Strikes | dentro de ±20 % del spot |
| Vencimientos | entre 7 y 120 días naturales |
| Vencimiento sin opciones que pasen | no se ofrece |
| Antigüedad mostrada | "datos con ~15 min de retraso; cargados a las HH:MM" |

## Out Of Scope

- C2: histórico del subyacente, backtest sintético y calibración (otro ciclo).
- Histórico de opciones de pago (C3 de la hoja de ruta).
- Datos en tiempo real (los datos tienen ~15 min de retraso).
- Operar, enviar órdenes o conectar con un bróker.
- Cualquier opción de baja liquidez, ni siquiera con aviso.
- Tickers fuera de la lista curada.
- Comisión de cierre racional (Etapa B2, diferida).
- Cambios en el motor de cálculo, en Monte Carlo, PoP o métricas.
- Superficie/sonrisa de volatilidad, dividendos discretos.
- Asesoría de inversión.

## Constraints

- **Usuario:** nivel básico de Python; código sencillo; explicaciones cortas y claras; interfaz en español con términos de opciones en inglés; herramienta de uso personal.
- **Proceso:** el cálculo vive en el motor puro (sin E/S); la capa de datos es un paquete aparte; la app solo dibuja. Identificadores en inglés, comentarios/docstrings en español, UI en español. Tests con `.venv/bin/pytest`; floats con `pytest.approx`; suite normal sin red.
- **Técnico:** Python 3.12; numpy 2.5.5 fijado; dependencias nuevas con versión fija; Yahoo es una fuente no oficial de "uso personal" que puede limitar solicitudes; datos con ~15 min de retraso; solo EE. UU.; multiplicador 100 por contrato.
- **Dependencias:** actuales: numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0. Se añaden las de datos (decididas en PLAN).

## Open Questions

None. (Las decisiones C1–C9 del usuario del 20-11-26 cierran las preguntas; los valores propuestos se revisan al aprobar el SPEC.)

## Background / Research Findings

- **Verificado (20-11-26):** yfinance 1.8.0 funciona en Python 3.12 con numpy 2.5.5. El precio actual sale de `fast_info['last_price']` (también para índices); los vencimientos de `Ticker.options`; `option_chain(fecha)` trae strike, lastPrice, bid, ask, impliedVolatility, volume, openInterest, inTheMoney, lastTradeDate.
- **Liquidez real:** bid = 0 es común en cadenas poco líquidas (^RUT 60/102, ^NDX 53/117, ^SPX 9/194, AAPL 4/48 calls en el 5.º vencimiento). De ahí la lista curada y los filtros.
- **Último precio poco fiable:** puede tener semanas (put SPX 7125: último 176 frente a bid/ask 322/335). La IV basada en el mid es suave; la basada en el último precio no es fiable. De ahí el mid (C3).
- **IV propia vs Yahoo:** en ATM líquidas, difiere ~0,3–1,2 puntos; en ITM y puts, 1–4 puntos.
- **Tasa y dividendos:** ^IRX llega en porcentaje (4,12); `dividendYield` llega en porcentaje y `trailingAnnualDividendYield` como fracción; los índices no traen dividend yield.
- **Fuente:** Yahoo es de "uso personal", no oficial; puede limitar solicitudes (429). Huella en el entorno ≈ 237 MB (incluye curl_cffi, lxml, peewee).
- Fuentes: `DISENO.md`, SPEC y REPORT del MVP, Etapa A y B1, `process/context/all-context.md`, `process/context/tests/all-tests.md`.

### Known gaps / Risks

| # | Riesgo o hueco | Tratamiento |
|---|---|---|
| C-G1 | **Fragilidad y condiciones de Yahoo:** fuente no oficial, uso personal, puede cambiar o dejar de funcionar. | Interfaz de proveedor intercambiable (C1); caché local (C5); mensajes claros (AC-C1-11). |
| C-G2 | **Retraso ~15 min:** no son datos en tiempo real. | Texto visible de antigüedad (AC-C1-9). |
| C-G3 | **Límite de solicitudes (429):** Yahoo puede bloquear temporalmente. | Mensaje en español y uso de la caché (AC-C1-10, AC-C1-11). |
| C-G4 | **Peso de dependencias:** ≈ 237 MB extra en el entorno. | Aceptado por el usuario (C2); versiones fijadas (AC-C1-15). |
| C-G5 | **Mercado cerrado / fin de semana:** bid/ask pueden estar en 0 o desactualizados, y quedar pocas opciones o ninguna. | Los filtros lo excluyen; mensaje "sin opciones líquidas ahora" (AC-C1-11). |
| C-G6 | **Calidad de datos de índices:** SPX es bueno pero hay anomalías en otros; q de índices no existe. | Lista curada solo con SPX; q manual por defecto (AC-C1-4). |
| C-G7 | **Fiabilidad del dividend yield:** el rendimiento anual reciente puede no reflejar dividendos futuros. | Es editable y se avisa (AC-C1-3, AC-C1-4). |
| C-G8 | **Filtros demasiado estrictos o laxos:** los umbrales propuestos pueden dejar pocas opciones o admitir algunas flojas. | Valores propuestos revisables por el usuario; umbrales en un solo lugar (AC-C1-5). |
| C-G9 | **Sin pruebas en vivo en la suite:** un cambio de formato de Yahoo no lo detectarían los tests normales. | Prueba en vivo opcional (AC-C1-14); fixtures grabadas. |
| C-G10 | **Sin tests visuales ni de persistencia entre pestañas** (mismo hueco que etapas previas). | Smoke AppTest + revisión manual del usuario. |

## Definition of Done (Etapa C1)

- Los 16 criterios AC-C1-1…AC-C1-16 se cumplen; los Hybrid pasan además la revisión manual del usuario.
- Los 2330 tests existentes (+ 2 omitidos) siguen en verde **sin conexión**; los tests nuevos corren **sin conexión** con fixtures y proveedor falso.
- La app arranca con `.venv/bin/streamlit run app.py`: se elige tipo y ticker de la lista curada, "Cargar datos" rellena spot/r/q y ofrece solo opciones líquidas con prima = mid; la entrada manual sigue igual.
- Motor sin cambios; dependencias nuevas con versiones fijadas; caché en carpeta ignorada por git.
- Valores propuestos (lista curada y filtros) aprobados o ajustados por el usuario al revisar el SPEC.
