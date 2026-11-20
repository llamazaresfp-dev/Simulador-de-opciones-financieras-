---
name: mvp-laboratorio SPEC
description: "SPEC bloqueado (requisitos de producto) del MVP v1 de Laboratorio de Opciones."
date: 20-11-26
status: locked
---

# SPEC: MVP (v1) de Laboratorio de Opciones

**TL;DR:** una app web en español donde introduces datos a mano, montas una estrategia con opciones (patas), ves su P&L "hoy" y "al vencimiento", sus métricas y griegas, y puedes abrir 8 estrategias clásicas desde un catálogo. Todas las preguntas abiertas están resueltas (20-11-26); este documento queda bloqueado.

## Summary

Laboratorio de Opciones es una herramienta de **estudio y análisis** (no asesoría de inversión) para construir, visualizar y entender estrategias con opciones de EE. UU. En el MVP el usuario escribe a mano precio, volatilidad, días al vencimiento, tipo de interés y dividendo; arma una estrategia con patas (call, put, acción); y ve al instante el gráfico de P&L, beneficio/pérdida máximos, breakevens, griegas y comisiones. Un catálogo de 8 estrategias explica cada una en español y la carga en el constructor. Sin datos de mercado en vivo: primero un motor correcto y entendido.

## User Stories / Jobs To Be Done

| # | Historia |
|---|---|
| US1 | Como aprendiz, quiero **introducir a mano** precio, volatilidad, días, tipo de interés y dividendo, para probar escenarios sin depender de datos externos. |
| US2 | Como usuario, quiero **añadir/quitar patas** (call, put, acción; long/short; strike, prima, cantidad), para montar cualquier estrategia. |
| US3 | Como usuario, quiero ver el **P&L "hoy" y "al vencimiento"** en un gráfico, para entender cómo gana o pierde la estrategia. |
| US4 | Como usuario, quiero ver **beneficio máximo, pérdida máxima y breakevens** (o "ilimitado"), para saber mi riesgo real. |
| US5 | Como usuario, quiero ver las **griegas** de la posición, para entender su sensibilidad al precio, tiempo, volatilidad y tipos. |
| US6 | Como usuario, quiero que las **comisiones** se resten del P&L y sean configurables, para que el resultado sea realista. |
| US7 | Como aprendiz, quiero un **catálogo de 8 estrategias** con explicación corta y un botón "abrir en el constructor", para aprender y experimentar. |
| US8 | Como usuario, quiero **mensajes claros** ante datos inválidos y **avisos** sobre las limitaciones del modelo, para no fiarme de números absurdos. |

## What The User Wants (Behavioral Outcomes)

- La app tiene **tres pestañas**: Catálogo, Constructor y Ajustes. Interfaz en español; términos como call, put, strike, delta, breakeven se mantienen en inglés.
- Los **datos globales** (tipo de subyacente: Acción / ETF / Índice; precio spot; volatilidad; días al vencimiento; tipo libre de riesgo; dividend yield q con valor por defecto 0) valen para todas las patas. Hay **un único vencimiento común**.
- Cada **pata de opción** tiene tipo, dirección, strike, cantidad y prima. La prima aparece **pre-rellenada** con el precio Black-Scholes calculado con los datos globales y el usuario puede **editarla** por pata.
- Una **pata de acción** tiene cantidad en acciones, dirección y precio de entrada (sin strike ni prima).
- El gráfico muestra la curva "al vencimiento" (exacta) y la curva "hoy" (Black-Scholes); el rango de precios se ajusta solo (~±30 % según spot y strikes).
- Las métricas (beneficio máx., pérdida máx., breakevens) se calculan **sobre el P&L al vencimiento**, de forma exacta; si crece o cae sin límite se muestra **"ilimitado"**. La curva "hoy" solo se dibuja.
- Las **griegas** de la posición se muestran en unidades prácticas (ver decisiones).
- Las **comisiones** se restan del P&L y por tanto desplazan gráfico, métricas y breakevens.
- Cada ficha del **catálogo** explica qué apuesta, beneficio/pérdida máximos, cuándo usarla y riesgos; "abrir en el constructor" carga sus patas.
- Con datos inválidos se ve un **mensaje en español**; la app no se rompe ni muestra números absurdos.
- Se avisa de que es una herramienta de estudio y, para acciones/ETFs, de que Black-Scholes es una aproximación.

## Flow / State Diagram

```
[Abrir app] --> {pestaña}
   |-- Catálogo --> [leer ficha] --> [Abrir en el constructor] --+
   |-- Ajustes  --> [editar comisiones] ------------------------+
   '-- Constructor <--------------------------------------------+
          |
   [datos globales] --> {válidos?} --no--> [mensaje en español, sin resultados]
          | sí
   [patas: añadir / quitar / editar prima]
          |
   [recalcular] --> [gráfico hoy + vencimiento]
                --> [métricas (vencimiento, con comisiones)]
                --> [griegas de la posición]
                --> [avisos: americana / no es asesoría]
          |
   [usuario cambia cualquier dato] --> (vuelve a "recalcular")
```

## Acceptance Criteria (Testable Outcomes)

Escenarios tomados de `process/context/tests/all-tests.md`: pytest sobre el motor puro con valores de libro (Hull), `pytest.approx` para floats; la interfaz Streamlit no tiene tests automáticos en el MVP (verificación manual, ver Known gaps).

**Datos globales y validación**
- **AC1:** Si el usuario introduce días = 0, volatilidad = 0, valores negativos o vacíos donde no se permiten, ve un mensaje claro en español y la app no falla ni muestra números absurdos. Con días = 0 la curva "hoy" coincide con el valor intrínseco.
  proven by: validación-entradas-inválidas + hoy-igual-intrínseco-en-días-0 (tests del motor); comprobación manual de mensajes
  strategy: Hybrid
- **AC2:** Con q = 0 por defecto, cambiar q altera los precios y griegas según la fórmula con dividendo.
  proven by: precio-con-dividendo (test)
  strategy: Fully-Automated

**Constructor de patas**
- **AC3:** El usuario puede añadir, editar y quitar patas de tipo call, put y acción, long o short, con cantidad; las patas de acción usan precio de entrada y las de opción strike y prima.
  proven by: modelo-de-pata + resultado-por-pata-al-vencimiento (tests); manual para la interfaz
  strategy: Hybrid
- **AC4:** La prima de una pata nueva coincide con el precio Black-Scholes de los datos globales y se puede sobrescribir; la prima editada se respeta en el P&L.
  proven by: prima-por-defecto-igual-a-BS + prima-editada-usada (tests)
  strategy: Fully-Automated
- **AC5:** El P&L de una pata es lado × cantidad × multiplicador × (valor − prima), con multiplicador 100 por contrato de opción y 1 por acción.
  proven by: payoff-por-tipo-de-pata (tests: long/short call, put, acción)
  strategy: Fully-Automated

**Precios y griegas**
- **AC6:** El precio Black-Scholes (con q) coincide con los valores de referencia: Hull S=42, K=40, r=10 %, σ=20 %, T=0,5 da call 4,7594, put 0,8086, delta call 0,7791; S=K=100, r=5 %, σ=20 %, T=1, q=0 da call 10,4506, put 5,5735.
  proven by: precios-referencia-Hull (tests con approx)
  strategy: Fully-Automated
- **AC7:** Se cumple la paridad put-call: C − P = S·e^(−qT) − K·e^(−rT).
  proven by: paridad-put-call (test, varios casos incl. q > 0)
  strategy: Fully-Automated
- **AC8:** Las griegas de referencia (S=K=100, r=5 %, σ=20 %, T=1, q=0) son delta 0,6368, gamma 0,018762, vega 0,3752 por punto, theta −0,01757 por día, rho 0,5323 por punto; theta es por día natural (/365), vega y rho por 1 punto porcentual; las griegas de posición = griega × 100 × cantidad × signo de dirección (pata de acción: delta ±cantidad, resto 0).
  proven by: griegas-referencia + griegas-de-posición-signos (tests)
  strategy: Fully-Automated

**Gráfico**
- **AC9:** El gráfico muestra la curva "al vencimiento" y la curva "hoy" con el rango de precios automático (~±30 % según spot y strikes, cubriendo todos los strikes). La curva al vencimiento coincide con el cálculo exacto de patas.
  proven by: curva-vencimiento-igual-suma-de-patas + rango-automático-cubre-strikes (tests); lectura visual manual
  strategy: Hybrid

**Métricas**
- **AC10:** Beneficio máximo, pérdida máxima y breakevens son exactos sobre el P&L al vencimiento: bull call spread, bear put spread, iron condor, covered call, protective put y long call/put dan sus valores de libro (ej.: un bull spread nunca pierde más de lo pagado).
  proven by: métricas-por-estrategia-del-catálogo (tests)
  strategy: Fully-Automated
- **AC11:** Si el beneficio o la pérdida son ilimitados (p. ej. beneficio de un long call o straddle; pérdida de un call corto) se muestra "ilimitado" en vez de un número.
  proven by: detección-de-ilimitado (tests: long call, short call, straddle; long put y short put no son ilimitados)
  strategy: Fully-Automated
- **AC12:** Se muestran todos los breakevens, incluso varios (straddle y iron condor tienen dos), y ninguno si no existe.
  proven by: breakevens-múltiples + sin-breakeven (tests)
  strategy: Fully-Automated

**Comisiones y Ajustes**
- **AC13:** Por defecto: 0,65 USD por contrato de opción, +0,60 USD por contrato si el subyacente es "Índice", "incluir cierre" activado; sin comisión de cierre en patas de opción que vencen sin valor; sin comisión en patas de acción.
  proven by: comisiones-por-defecto + sin-cierre-si-expira-sin-valor + acción-sin-comisión (tests)
  strategy: Fully-Automated
- **AC14:** Las comisiones restan del P&L y desplazan los breakevens (y reducen beneficio máx./aumentan pérdida máx.). Todos los parámetros se editan en la pestaña Ajustes y la estrategia se recalcula con ellos.
  proven by: comisiones-mueven-breakeven (test); edición-en-Ajustes (manual)
  strategy: Hybrid

**Catálogo**
- **AC15:** El catálogo lista exactamente 8 estrategias (long call, long put, covered call, protective put, bull call spread, bear put spread, long straddle, iron condor), cada una con explicación en español (qué apuesta, beneficio/pérdida máx., cuándo usarla, riesgos).
  proven by: catálogo-completo-y-campos-presentes (test de datos del catálogo)
  strategy: Fully-Automated
- **AC16:** "Abrir en el constructor" carga las patas de la plantilla (con strikes/primas coherentes con el spot actual) y el constructor muestra gráfico y métricas de esa estrategia sin pasos extra. Cada plantilla produce métricas de libro correctas.
  proven by: plantillas-generan-patas-válidas (tests del motor); navegación del botón (manual)
  strategy: Hybrid

**Avisos**
- **AC17:** Para subyacentes Acción/ETF se muestra un aviso visible de que Black-Scholes aproxima las opciones americanas (más para puts; infravaloración medida de hasta ~7 %); para Índice se indica que son europeas. Siempre se indica que es una herramienta de estudio, no asesoría.
  proven by: aviso-según-tipo-de-subyacente (test de la lógica de avisos); presencia visual (manual)
  strategy: Hybrid

**Calidad**
- **AC18:** La suite `pytest` pasa completa desde la raíz del repo y el motor funciona sin la interfaz.
  proven by: ejecución de `.venv/bin/pytest` (puerta de EXECUTE)
  strategy: Fully-Automated

## Locked Decisions (20-11-26)

| # | Decisión |
|---|---|
| 1 | Dividend yield q: entrada global, valor por defecto 0. |
| 2 | Métricas (máx. beneficio, máx. pérdida, breakevens) sobre el P&L **al vencimiento**, exactas; ilimitado se detecta y se muestra "ilimitado". La curva "hoy" solo va en el gráfico. |
| 3 | Un único vencimiento común para todas las patas (días al vencimiento es un dato global). |
| 4 | Prima de opción pre-rellenada con el precio Black-Scholes de los datos globales, editable por pata. |
| 5 | Pata de acción: cantidad en acciones, long/short, precio de entrada (sin strike/prima). |
| 6 | Comisiones: 0,65 USD/contrato; +0,60 USD/contrato si subyacente "Índice"; "incluir cierre" activo por defecto; sin comisión de cierre en patas que vencen sin valor; sin comisión en acciones; todo configurable en Ajustes; restan del P&L y mueven breakevens. |
| 7 | Unidades de griegas: theta por día natural (/365); vega y rho por 1 punto porcentual; griega de posición = griega × 100 × cantidad × signo. |
| 8 | Aviso visible para acciones/ETF (americanas): Black-Scholes es aproximación, más fuerte en puts (~7 % de infravaloración medida); índices son europeas. |
| 9 | UI con pestañas Catálogo, Constructor, Ajustes; textos del catálogo redactados por el asistente; "abrir en el constructor" carga las patas. |
| 10 | Entradas inválidas (días = 0, vol = 0, negativos, vacíos): validadas con mensajes claros en español, sin fallos ni números absurdos. Con días = 0 la curva "hoy" = valor intrínseco. |
| 11 | Dependencias fijadas a las instaladas: numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0. |
| 12 | Rango de precios del gráfico automático según strikes y spot (~±30 %). |

## Out Of Scope

- Datos de mercado en vivo / yfinance, cadenas de opciones.
- Volatilidad implícita.
- Simulación Monte Carlo y probabilidades.
- Comparador de estrategias.
- Guardar / cargar estrategias.
- Sugerencias de estrategias (asistente).
- Backtesting.
- Modelo binomial / valoración americana exacta.
- Spreads calendar y diagonal (varios vencimientos).
- Asesoría de inversión.

## Constraints

- **Usuario:** nivel básico de Python; código sencillo; explicaciones cortas y claras; interfaz en español con términos de opciones en inglés.
- **Proceso:** motor de cálculo puro (paquete `opciones/`) separado de la interfaz (`app.py` en la raíz); identificadores en inglés, comentarios/docstrings en español; tests con pytest (`.venv/bin/pytest`), floats con `pytest.approx`.
- **Mercado:** solo EE. UU.; multiplicador 100 por contrato de opción y 1 por acción; índices (SPX/NDX/RUT) europeas con liquidación en efectivo; acciones y ETFs (SPY/QQQ/IWM) americanas con entrega de acciones.
- **Técnico:** un solo vencimiento; modelo Black-Scholes-Merton con dividendo continuo (fórmulas y griegas según Hull); el P&L al vencimiento es lineal a tramos (extremos exactos en S=0 y en los strikes; la pendiente de las colas decide si es ilimitado).
- Las versiones de dependencias son las de la decisión 11.

## Open Questions

None. (Las 12 decisiones del usuario del 20-11-26 cierran todas las preguntas abiertas.)

## Background / Research Findings

- Fórmulas BSM con q: d1 = [ln(S/K)+(r−q+σ²/2)T]/(σ√T), d2 = d1 − σ√T; call = S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2); put = K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1).
- Valores de referencia verificados en RESEARCH (20-11-26): ver AC6 y AC8.
- Breakevens del P&L al vencimiento: cambio de signo + interpolación lineal; pueden ser varios.
- Fuente de visión y alcance: `DISENO.md` (§9 v1). Documento y Streamlit sin tests de UI automáticos en el MVP.

### Known gaps / Risks

| # | Riesgo o hueco | Tratamiento |
|---|---|---|
| G1 | **Recargo de 0,60 USD en índices no verificado** contra una tarifa real de broker. | Es un valor por defecto configurable; se verifica con el broker del usuario. |
| G2 | **Aproximación americana:** Black-Scholes infravalora puts americanas hasta ~7 %; los números "hoy" de acciones/ETFs son aproximados. | Aviso visible (AC17); modelo binomial queda fuera del MVP. |
| G3 | **Sin tests automáticos de la UI Streamlit.** `streamlit.testing.v1.AppTest` es un posible smoke test; **no decidido** (se decide en INNOVATE/PLAN). | Verificación manual; los criterios Hybrid dependen de ella. |
| G4 | Prima editada a mano puede ser incoherente con el modelo (el usuario manda). | Se respeta la prima editada; "hoy" sigue usando Black-Scholes con datos globales. |
| G5 | Ejercicio anticipado, dividendos discretos y tipo de interés constante no se modelan. | Documentado como limitación; no es asesoría. |

## Definition of Done (MVP)

- Los 18 criterios AC1–AC18 se cumplen; los Hybrid pasan además la revisión manual del usuario.
- `.venv/bin/pytest` en verde; valores de referencia de Hull reproducidos.
- La app arranca con `.venv/bin/streamlit run app.py` y muestra las tres pestañas.
- Las 8 estrategias del catálogo se abren en el constructor con gráfico y métricas correctos.
- `requirements.txt` con las versiones de la decisión 11.
- Todos los textos de UI en español; avisos presentes; cero fallos ante entradas inválidas.
