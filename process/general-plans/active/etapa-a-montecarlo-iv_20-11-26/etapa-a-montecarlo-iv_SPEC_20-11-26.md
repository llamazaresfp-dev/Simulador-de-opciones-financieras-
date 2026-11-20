---
name: etapa-a-montecarlo-iv SPEC
description: "SPEC bloqueado (requisitos de producto) de la Etapa A de Laboratorio de Opciones: simulación Monte Carlo del resultado de la estrategia y volatilidad implícita."
date: 20-11-26
status: locked
---

# SPEC: Etapa A — Monte Carlo + volatilidad implícita

**TL;DR:** en la pestaña Constructor, debajo de las métricas, un bloque desplegable muestra la **probabilidad de beneficio (PoP)** exacta, un histograma del P&L al vencimiento, el valor esperado y los percentiles 5/50/95 (con 100 000 simulaciones y semilla 42, resultados estables). Además, para cada pata cuya prima editaste a mano, la app calcula su **volatilidad implícita (IV)** y ofrece usarla como volatilidad global. Todas las preguntas están resueltas (20-11-26); este documento queda bloqueado.

## Summary

El MVP calcula el resultado de una estrategia en puntos concretos del precio; no dice **cuántas probabilidades hay** de ganar ni cuál es el resultado típico. La Etapa A añade dos cosas, siempre como herramienta de estudio (no asesoría). Primera: un modelo de escenarios (precio final lognormal, neutral al riesgo por defecto; el usuario puede indicar una rentabilidad esperada propia) que da la probabilidad de beneficio calculada de forma **exacta** por fórmula, y una simulación Monte Carlo que añade el histograma, el valor esperado y los percentiles, y sirve de comprobación cruzada de la PoP. Segunda: la volatilidad implícita de las primas que el usuario escribió a mano, con un botón para fijarla como volatilidad global. Todo vive en el Constructor, sin tocar el catálogo ni los ajustes de comisiones del MVP.

## User Stories / Jobs To Be Done

| # | Historia |
|---|---|
| A-US1 | Como aprendiz, quiero ver la **probabilidad de beneficio** de mi estrategia, para saber qué tan probable es ganar dinero al vencimiento. |
| A-US2 | Como usuario, quiero ver un **histograma del P&L** al vencimiento, su **valor esperado** y los **percentiles 5 %, 50 % y 95 %**, para entender el rango típico de resultados y los extremos razonables. |
| A-US3 | Como usuario, quiero elegir entre un escenario **neutral al riesgo** (por defecto) o uno con **mi propia rentabilidad esperada anual**, para explorar "qué pasa si creo que la acción sube un X % al año". |
| A-US4 | Como usuario, quiero que los resultados sean **estables y reproducibles** (misma semilla, mismo resultado) y poder cambiar número de simulaciones y semilla en Ajustes, para comparar sin ruido. |
| A-US5 | Como usuario, quiero ver la **volatilidad implícita** de cada pata cuya prima edité a mano, para saber qué volatilidad "piensa" el mercado (o mi prima) que tiene ese strike. |
| A-US6 | Como usuario, quiero un botón **"usar como volatilidad global"**, para llevar esa IV al resto del modelo, sabiendo claramente que cambia todas las primas automáticas y la curva "hoy". |
| A-US7 | Como aprendiz, quiero **mensajes claros** cuando no se puede calcular una IV o una simulación, y **avisos** sobre las limitaciones del modelo, para no fiarme de números que no significan nada. |

## What The User Wants (Behavioral Outcomes)

- En la pestaña **Constructor**, **debajo de las métricas**, hay un bloque **desplegable** (colapsado o abierto, el usuario decide) con el análisis de escenarios. El gráfico, las métricas y las griegas del MVP quedan exactamente como están.
- **Escenario por defecto: neutral al riesgo.** El precio al vencimiento sigue una distribución lognormal con la volatilidad global y el crecimiento "tipo libre de riesgo − dividend yield". Hay un campo opcional **"rentabilidad esperada anual (%)"**: vacío = neutral al riesgo; con un valor = escenario "mundo real" con ese crecimiento.
- **Probabilidad de beneficio (PoP):** se muestra el valor **exacto** (por fórmula, usando los breakevens y quiebres exactos del P&L al vencimiento, comisiones incluidas) y, **al lado**, el valor de la simulación Monte Carlo como comprobación cruzada. Ambos deben coincidir salvo ruido de simulación.
- **Lo que añade Monte Carlo:** histograma del P&L al vencimiento, **valor esperado** (media del P&L al vencimiento tal como lo calcula el motor, **sin descontar**, etiquetado así claramente) y percentiles **5 %, 50 % y 95 %**.
- **Solo al vencimiento:** no hay Monte Carlo para la curva "hoy".
- **Ajustes:** número de simulaciones (por defecto 100 000) y semilla (por defecto 42) editables en la pestaña Ajustes. Con los mismos datos y la misma semilla, el resultado es idéntico en cada recálculo.
- **Volatilidad implícita:** para cada **pata de opción con prima editada a mano** se muestra su IV (en %). Junto a ella, un botón **"usar como volatilidad global"** que fija la volatilidad de la barra lateral en ese valor. El texto junto al botón dice que **cambia todas las primas automáticas y la curva "hoy"** y que **una sola σ global no puede ajustarse a todos los strikes**.
- Cuando no existe IV (prima fuera de los límites sin arbitraje, días = 0, pata de acción) se muestra un **mensaje claro en español** en lugar de un número.
- **Avisos visibles:** los resultados son un modelo, no una predicción; las distribuciones reales tienen colas más gruesas que la lognormal; para acciones/ETF las opciones americanas sesgan la IV y la simulación; se mantiene "no es asesoría".

## Flow / State Diagram

```
[Constructor con estrategia válida] --> [bloque desplegable "Escenarios (Monte Carlo)"]
        |
   {datos válidos? días>0, σ>0, patas}
        | no --> [mensaje en español, sin resultados]
        | sí
   {rentabilidad esperada vacía?}
        | sí --> escenario neutral al riesgo (crecimiento r − q)
        | no --> escenario con crecimiento μ del usuario
        v
   [PoP exacta (fórmula)]  +  [simulación: 100 000 trayectorias, semilla 42]
        |                         |
        |                 [PoP simulada (comprobación)]
        |                 [histograma P&L vencimiento]
        |                 [valor esperado (no descontado) + percentiles 5/50/95]
        v
   [avisos: modelo ≠ predicción / colas gruesas / americanas / no es asesoría]

[Pata con prima editada a mano] --> {IV existe?}
        | no --> [mensaje: prima fuera de límites / días = 0 / pata de acción]
        | sí --> [muestra IV %] --> [botón "usar como volatilidad global"]
                                          |
                          [barra lateral: σ = IV] --> (recalcula primas automáticas,
                                                       curva "hoy", PoP y Monte Carlo)
[Ajustes: nº simulaciones / semilla] --> (recalcula con los nuevos valores)
```

## Acceptance Criteria (Testable Outcomes)

Escenarios tomados de `process/context/tests/all-tests.md`: pytest sobre el motor puro con valores de referencia calculados a mano o por fórmula (`pytest.approx`); la interfaz se comprueba con el smoke test AppTest ya existente; lo visual y la persistencia entre pestañas, manualmente. Las pruebas estocásticas usan tolerancia basada en el error estándar (≈ 4·EE, con EE ≈ √(p(1−p)/n)) y semilla fija.

**Escenario y probabilidad exacta**
- **AC-A1:** Por defecto (rentabilidad esperada vacía) el escenario es neutral al riesgo: el precio final simulado tiene media ≈ S·e^((r−q)T) y la PoP exacta usa ese mismo crecimiento. Con un valor μ en el campo, el crecimiento pasa a ser μ (tanto en la PoP exacta como en la simulación) y cambia los resultados en el sentido esperado (μ mayor → PoP de un long call mayor).
  proven by: media-del-precio-simulado-neutral + modo-μ-cambia-resultado (tests del motor)
  strategy: Fully-Automated
- **AC-A2:** La PoP exacta de un long call es N(d2) evaluado en su breakeven (el de las métricas, con comisiones) y la de un long put N(−d2); caso de referencia: S=100, σ=25 %, 45 días, r=4 %, q=1 %, call ATM con breakeven ≈ 103,69 → PoP ≈ 0,3392.
  proven by: pop-exacta-long-call-put-oráculo (tests con approx)
  strategy: Fully-Automated
- **AC-A3:** Para estrategias con varios tramos de beneficio (long straddle, iron condor, bull call spread, covered call, protective put) la PoP exacta es la probabilidad lognormal total de los intervalos donde el P&L al vencimiento del motor es > 0, usando sus breakevens y quiebres exactos con comisiones incluidas; coincide con una integración numérica independiente y con el caso sin beneficio posible (PoP = 0) y siempre beneficio (PoP = 1) cuando corresponda.
  proven by: pop-exacta-multi-intervalo-vs-integración-independiente + pop-extremos-0-y-1 (tests)
  strategy: Fully-Automated
- **AC-A4:** La PoP simulada se muestra junto a la exacta y la diferencia está dentro de ≈ 4 errores estándar (±0,3 puntos porcentuales típicos con 100 000 simulaciones) en las estrategias del catálogo.
  proven by: pop-mc-vs-exacta-catálogo (tests con tolerancia por EE)
  strategy: Fully-Automated

**Lo que añade Monte Carlo**
- **AC-A5:** Se muestran histograma del P&L al vencimiento, valor esperado y percentiles 5 %, 50 % y 95 %. Los percentiles son monótonos (p5 ≤ p50 ≤ p95) y caen dentro de [pérdida máxima, beneficio máximo] cuando estos son finitos; los datos del histograma suman el total de simulaciones.
  proven by: estadísticos-mc-forma-y-rango (tests del motor); presencia del histograma (smoke AppTest + manual)
  strategy: Hybrid
- **AC-A6:** El "valor esperado" es la media del P&L al vencimiento tal como lo calcula el motor, **sin descontar**, y la interfaz lo etiqueta así. Para un long call neutral al riesgo coincide (dentro de ≈ 4 EE) con 100·prima·(e^(rT) − 1) − comisión de apertura − comisión de cierre·P(S_T > K).
  proven by: valor-esperado-long-call-oráculo (test con tolerancia por EE); etiqueta (smoke AppTest)
  strategy: Hybrid
- **AC-A7:** Solo hay análisis al vencimiento: no existe simulación ni PoP para la curva "hoy", y la interfaz no sugiere lo contrario.
  proven by: alcance-solo-vencimiento (smoke AppTest: el bloque no contiene controles ni resultados para "hoy")
  strategy: Fully-Automated

**Estabilidad y ajustes**
- **AC-A8:** Por defecto se usan 100 000 simulaciones y semilla 42; con los mismos datos, repetir el cálculo da resultados idénticos; cambiar la semilla cambia el resultado simulado (no la PoP exacta); ambos valores son editables en Ajustes y la validación rechaza con mensaje claro valores no válidos (simulaciones no enteras, ≤ 0 o por encima de un máximo razonable; semilla no entera).
  proven by: reproducibilidad-semilla-42 + parámetros-editables-y-validados (tests del motor); edición en Ajustes (smoke AppTest + manual)
  strategy: Hybrid
- **AC-A9:** El cálculo con 100 000 simulaciones sobre un iron condor es lo bastante rápido para no notarse al recalcular (orden de décimas de segundo en el motor; la app sigue respondiendo con normalidad).
  proven by: rendimiento-iron-condor-100k (test con cota holgada de tiempo)
  strategy: Fully-Automated

**Validación y casos límite**
- **AC-A10:** Con días = 0, volatilidad = 0, sin patas, μ no numérica o fuera de un rango razonable, o simulaciones/semilla inválidas, el bloque muestra un mensaje claro en español y no devuelve números absurdos (ni NaN ni infinitos); la app no se rompe.
  proven by: validación-escenarios + sin-NaN-en-resultados (tests del motor); mensajes (smoke AppTest)
  strategy: Hybrid

**Volatilidad implícita**
- **AC-A11:** Para cada pata de opción con prima editada a mano se muestra su IV en %, y solo para esas patas; la IV recuperada reproduce la prima: recalcular el precio Black-Scholes con esa IV devuelve la prima original (ida y vuelta con error numérico despreciable) en casos ATM/OTM/ITM, volatilidades de 1 % a 300 % y T = 1 día. Una prima igual al precio del modelo devuelve la volatilidad global.
  proven by: iv-ida-y-vuelta-ATM-OTM-ITM + iv-igual-a-σ-global-con-prima-modelo + iv-solo-patas-premium-manual (tests)
  strategy: Fully-Automated
- **AC-A12:** Se comprueban primero los límites sin arbitraje (call: máx(S·e^(−qT) − K·e^(−rT), 0) < C < S·e^(−qT); put: máx(K·e^(−rT) − S·e^(−qT), 0) < P < K·e^(−rT)). Si la prima está en el límite o fuera, si días = 0 o si la pata es de acción, se muestra un mensaje en español específico para cada caso; nunca un número engañoso (p. ej. una prima de 0,00 muy fuera del dinero no devuelve una IV falsa del mínimo) ni una excepción.
  proven by: iv-fuera-de-límites + iv-prima-cero + iv-días-0 + iv-pata-acción (tests de mensajes)
  strategy: Fully-Automated
- **AC-A13:** Junto a cada IV válida hay un botón **"usar como volatilidad global"** que fija la volatilidad de la barra lateral en ese valor; la interfaz dice explícitamente que esto cambia todas las primas automáticas y la curva "hoy" y que una σ global no encaja con todos los strikes. Tras pulsarlo, el resto de resultados (incluida la PoP) se recalculan con la nueva σ.
  proven by: botón-fija-σ-global-y-recalcula (smoke AppTest); texto de aviso (smoke AppTest + manual)
  strategy: Hybrid

**Ubicación y avisos**
- **AC-A14:** El análisis aparece en el Constructor, en un bloque desplegable situado debajo de las métricas; el gráfico, las métricas y las griegas del MVP no cambian de valor ni de posición, y el catálogo y los Ajustes de comisiones siguen funcionando igual.
  proven by: bloque-desplegable-bajo-métricas (smoke AppTest: estructura); disposición visual (manual)
  strategy: Hybrid
- **AC-A15:** Se muestran avisos visibles: los resultados son un modelo y no una predicción; las distribuciones reales tienen colas más gruesas que la lognormal; en acciones/ETF las opciones americanas sesgan la IV y la simulación (para índices se indica que son europeas); y se mantiene "no es asesoría".
  proven by: avisos-etapa-A-según-subyacente (test de la lógica de avisos); presencia visual (manual)
  strategy: Hybrid

**Calidad**
- **AC-A16:** El código nuevo de cálculo está separado de la interfaz (se importa sin Streamlit, como el motor del MVP) y no añade dependencias ni cambia las versiones fijadas.
  proven by: motor-importa-sin-Streamlit (test en subproceso, extensión del existente) + requirements.txt sin cambios (revisión de diff)
  strategy: Hybrid
- **AC-A17:** Los 479 tests existentes siguen en verde y los tests nuevos de la Etapa A también; `.venv/bin/pytest` pasa completa desde la raíz y el comportamiento del MVP (decisiones 1–14) no cambia.
  proven by: ejecución de `.venv/bin/pytest` (puerta de EXECUTE)
  strategy: Fully-Automated

## Locked Decisions (20-11-26)

Las decisiones 1–14 del MVP siguen vigentes (en especial la 6: comisiones; la regla de "cierre racional" queda en backlog). Las de la Etapa A:

| # | Decisión |
|---|---|
| A1 | Modelo de escenario: neutral al riesgo por defecto (precio final lognormal, crecimiento r − q, σ global). Campo opcional "rentabilidad esperada anual (%)" μ para explorar escenarios reales; vacío = neutral al riesgo. |
| A2 | PoP calculada **exactamente por fórmula** (distribución lognormal sobre los intervalos donde el P&L al vencimiento > 0, con los breakevens/quiebres exactos del motor y comisiones incluidas). La PoP de Monte Carlo se muestra al lado como comprobación cruzada. |
| A3 | Lo que añade Monte Carlo: histograma del P&L al vencimiento, media del P&L, percentiles 5 %, 50 % y 95 %. |
| A4 | "Valor esperado" = media del P&L al vencimiento tal como lo da el motor (no descontado), etiquetado con claridad. |
| A5 | Alcance: solo al vencimiento; sin Monte Carlo para la curva "hoy". |
| A6 | 100 000 simulaciones y semilla fija 42 por defecto, ambos editables en Ajustes; resultados estables entre recálculos. |
| A7 | Ubicación: pestaña Constructor, bloque desplegable debajo de las métricas. |
| A8 | Volatilidad implícita por pata de opción con prima editada a mano (premium_manual), con botón "usar como volatilidad global" que fija la volatilidad de la barra lateral (la UI avisa de que cambia todas las primas automáticas y la curva "hoy"; una σ global no encaja con todos los strikes). |
| A9 | Método de IV: resolver Black-Scholes para σ con un buscador de raíces robusto por intervalo, **después** de comprobar los límites sin arbitraje (call: máx(S·e^−qT − K·e^−rT, 0) < C < S·e^−qT; put: máx(K·e^−rT − S·e^−qT, 0) < P < K·e^−rT); mensajes claros en español si no hay IV (prima fuera de límites, días = 0, pata de acción). |
| A10 | Avisos: resultados = modelo, no predicción; colas más gruesas que lognormal; opciones americanas (acción/ETF) sesgan IV y Monte Carlo; se mantiene "no es asesoría". |

## Out Of Scope

- Regla de cierre racional de la comisión de cierre (backlog, Etapa B; la decisión 6 del MVP sigue aplicando tal cual).
- Modelo binomial / valoración americana exacta.
- Datos de mercado en vivo, cadenas de opciones (Etapa C).
- Monte Carlo o PoP para la curva "hoy".
- Reglas dependientes de la trayectoria (stops, cierres anticipados, rolls).
- Modelos de colas gruesas o volatilidad estocástica (solo se avisa de la limitación).
- Comparador de estrategias, guardar/cargar estrategias.
- IV por strike combinada en una superficie/sonrisa de volatilidad (se usa una única σ global).
- Asesoría de inversión.

## Constraints

- **Usuario:** nivel básico de Python; código sencillo; explicaciones cortas y claras; interfaz en español con términos de opciones en inglés.
- **Proceso:** el cálculo nuevo va en el paquete puro `opciones/` (sin Streamlit); `app.py` solo dibuja. Identificadores en inglés, comentarios/docstrings en español, UI en español. Tests con pytest (`.venv/bin/pytest`), floats con `pytest.approx`; pruebas estocásticas con semilla fija y tolerancia por error estándar.
- **Técnico:** un solo vencimiento común (el precio final se obtiene de forma exacta en un paso, sin simular trayectorias); el P&L al vencimiento usado es el del motor del MVP (incluye la regla de comisión de cierre solo si la pata acaba estrictamente en el dinero); la PoP exacta debe usar los mismos breakevens y quiebres que las métricas.
- **Dependencias:** sin dependencias nuevas; versiones fijadas del MVP (numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0).
- **Mercado:** solo EE. UU.; multiplicador 100 por contrato de opción y 1 por acción; índices europeos, acciones/ETF americanas (decisión 8 del MVP).

## Open Questions

None. (Las decisiones A1–A10 del usuario del 20-11-26 cierran todas las preguntas abiertas.)

## Background / Research Findings

- Precio final con un único vencimiento: S_T = S0·exp((μ − ½σ²)T + σ√T·Z), exacto, sin simular trayectorias; neutral al riesgo usa μ = r − q.
- El cálculo del P&L al vencimiento del motor ya está vectorizado (acepta arrays de precios) e incluye la regla de comisión de cierre con ITM estricto; 100 000 trayectorias sobre un iron condor ≈ 0,02 s.
- Error estándar de la PoP simulada ≈ √(p(1−p)/n): ±0,3 pp con 100 000; con 10 000 es demasiado ruidoso para mostrarlo.
- Oráculos: long call PoP = N(d2) en su breakeven b (comisiones incluidas): S=100, σ=25 %, 45 días, r=4 %, q=1 % → b ≈ 103,69, PoP 0,3392; long put N(−d2(b)). La PoP exacta por intervalos es un segundo oráculo para Monte Carlo. E_RN[P&L] de un long call = 100·prima·(e^(rT) − 1) − comisión de apertura − comisión de cierre·P(S_T > K) (no "− comisiones" a secas).
- IV: un buscador de raíces por intervalo (brentq) hace ida y vuelta precio→IV→precio con error ≤ 1,5e−15 en ATM/OTM/ITM, σ 0,01–3,0, T = 1 día. Una prima de 0,0 muy fuera del dinero devuelve en silencio el límite inferior del intervalo, por lo que los límites sin arbitraje se comprueban **antes**; una prima por encima del límite superior hace fallar al buscador (se convierte en mensaje en español); con T = 0 no hay IV.
- Fuente de visión y alcance: `DISENO.md` (§9 v2). Backlog relacionado: `process/general-plans/backlog/close-fee-rational-close_20-11-26.md`.

### Known gaps / Risks

| # | Riesgo o hueco | Tratamiento |
|---|---|---|
| A-G1 | **La IV de una pata americana (acción/ETF) está sesgada** (Black-Scholes es europeo) y la simulación también. | Aviso visible (AC-A15); modelo binomial fuera de alcance. |
| A-G2 | **Colas más finas que las reales:** la lognormal subestima los movimientos extremos; PoP y percentiles 5/95 son optimistas en las colas. | Aviso visible (AC-A15); modelos de colas gruesas fuera de alcance. |
| A-G3 | **Una σ global no encaja con todos los strikes** (sonrisa de volatilidad): "usar como volatilidad global" cambia primas automáticas y curva "hoy" de todas las patas. | Texto explícito junto al botón (AC-A13). |
| A-G4 | **Escenario μ ≠ neutral al riesgo** es subjetivo: el usuario puede introducir un μ poco razonable. | Validación de rango razonable (AC-A10) y etiqueta clara del escenario. |
| A-G5 | **Valor esperado no descontado:** no es un precio justo ni un valor actual. | Etiqueta explícita (AC-A6, decisión A4). |
| A-G6 | **Sin tests de UI visuales ni de persistencia entre pestañas** (mismo hueco que el MVP). | Smoke AppTest para estructura y mensajes; revisión manual del usuario para lo visual. |

## Definition of Done (Etapa A)

- Los 17 criterios AC-A1…AC-A17 se cumplen; los Hybrid pasan además la revisión manual del usuario.
- Los 479 tests existentes siguen en verde, junto con los nuevos; `.venv/bin/pytest` completa desde la raíz.
- La app arranca con `.venv/bin/streamlit run app.py`; el Constructor muestra el bloque desplegable bajo las métricas con PoP exacta y simulada, histograma, valor esperado y percentiles, y la IV por pata con prima manual.
- Resultados estables entre recálculos con la semilla por defecto 42 y 100 000 simulaciones; ambos editables en Ajustes.
- Avisos presentes y textos de UI en español; cero fallos ante entradas inválidas.
- Sin dependencias nuevas; `requirements.txt` sin cambios.
