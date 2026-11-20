---
name: etapa-b1-binomial SPEC
description: "SPEC bloqueado (requisitos de producto) de la Etapa B1 de Laboratorio de Opciones: modelo binomial CRR para opciones americanas (Acción/ETF), con Black-Scholes seleccionable."
date: 20-11-26
status: locked
---

# SPEC: Etapa B1 — Modelo binomial para opciones americanas

**TL;DR:** para **Acción** y **ETF** (opciones americanas) la app pasa a calcular primas, curva "hoy", griegas y volatilidad implícita con un **modelo binomial** que sí contempla el ejercicio anticipado. En Ajustes hay un selector para volver a Black-Scholes y comparar (por defecto: binomial). **Índice** (europeo) no cambia. Monte Carlo, PoP exacta y métricas al vencimiento no cambian. La comisión de cierre racional es la Etapa B2 (otro ciclo). Todas las preguntas están resueltas (20-11-26); este documento queda bloqueado.

## Summary

Hasta ahora la app usa Black-Scholes, que valora opciones **europeas** (solo se ejercen al vencimiento). Las opciones sobre acciones y ETF de EE. UU. son **americanas** (se pueden ejercer antes), y por eso Black-Scholes **subvalora los puts americanos** (típicamente 1–8 %, y en casos extremos hasta ~24 %). La Etapa B1 añade el modelo binomial de Cox-Ross-Rubinstein para esos subyacentes: primas automáticas, curva "hoy", griegas y volatilidad implícita pasan a ser coherentes con el ejercicio americano. El usuario puede cambiar a Black-Scholes desde Ajustes para ver la diferencia. Lo que ocurre al vencimiento (P&L, métricas, PoP, Monte Carlo) no depende del ejercicio anticipado y no se toca. Sigue siendo una herramienta de estudio, no asesoría.

## User Stories / Jobs To Be Done

| # | Historia |
|---|---|
| B-US1 | Como aprendiz, quiero que las primas de opciones sobre **acciones y ETF** se calculen con un modelo **americano**, para que se parezcan más a lo que cotiza el mercado. |
| B-US2 | Como usuario, quiero un **selector en Ajustes** (binomial / Black-Scholes) para acciones y ETF, para **comparar** ambos modelos y aprender cuánto difieren. |
| B-US3 | Como usuario de **índices**, quiero que nada cambie (siguen siendo europeas con Black-Scholes), para no perder lo que ya funciona. |
| B-US4 | Como usuario, quiero que las **griegas** (delta, gamma, theta, vega, rho) también salgan del modelo americano, con las mismas unidades de ahora, para que coincidan con las primas. |
| B-US5 | Como usuario, quiero que la **volatilidad implícita** use el mismo modelo que la prima, para que "prima → IV → prima" sea coherente. |
| B-US6 | Como aprendiz, quiero **mensajes claros** cuando no se puede calcular la IV (p. ej. prima igual al valor intrínseco) y **avisos honestos** sobre qué modelo está activo y qué error tiene, para no fiarme de números sin sentido. |
| B-US7 | Como usuario, quiero que la app siga **respondiendo con fluidez** al cambiar precio, strike o volatilidad. |

## What The User Wants (Behavioral Outcomes)

- **Selector en Ajustes:** "Modelo de valoración para Acción/ETF": **Binomial (americano)** (por defecto) o **Black-Scholes (europeo)**. Un texto corto explica para qué sirve. Con subyacente **Índice** el selector no tiene efecto (y se indica).
- **Con binomial activo (Acción/ETF):** las primas automáticas, la curva "hoy", las griegas y la IV usan el modelo americano. Las primas editadas a mano se respetan como siempre (botón "↺ BS" sigue disponible; su texto y comportamiento se ajustan al modelo activo).
- **Con Black-Scholes seleccionado (Acción/ETF):** el resultado es **idéntico al de la Etapa A**; un aviso dice que Black-Scholes subvalora los puts americanos.
- **Índice:** todos los números y textos de Índice son iguales que en MVP/Etapa A.
- **Griegas:** delta, gamma y theta salen del propio modelo binomial; vega y rho se obtienen cambiando un poco la volatilidad o la tasa y recalculando la prima. Unidades prácticas de siempre: theta por día, vega y rho por cada 1 punto porcentual.
- **Volatilidad implícita:** para cada pata con prima manual, se muestra la IV con el mismo modelo que la prima (americano en Acción/ETF con binomial; Black-Scholes en Índice o si el usuario eligió Black-Scholes). Los límites sin arbitraje se ajustan al modelo (en americano, el límite inferior es el valor intrínseco **sin descontar**). Si la prima no permite identificar la IV (por ejemplo, prima igual al valor intrínseco, donde el precio no depende de σ), se muestra un mensaje claro en español.
- **Sin cambios:** P&L al vencimiento, métricas, breakevens, PoP exacta, simulación Monte Carlo, histograma, percentiles, catálogo y comisiones.
- **Avisos actualizados** (ver AC-B12): texto según el modelo activo; el aviso de escenarios de la Etapa A pasa a decir que solo queda el modelo lognormal de precio final de estilo europeo, donde el ejercicio anticipado no importa al vencimiento.
- **Velocidad:** recalcular no se nota (primas y griegas precisas con 500 pasos; la curva "hoy" con 200 pasos).

## Flow / State Diagram

```
[Constructor / Ajustes] --> {tipo de subyacente}
        |
        +-- Índice -------------------------------> [Black-Scholes europeo] (igual que antes)
        |
        +-- Acción / ETF --> {selector en Ajustes}
                |
                +-- Black-Scholes --> [BS: igual que Etapa A + aviso "subvalora puts americanos"]
                |
                +-- Binomial (por defecto)
                        |
                        +--> [prima / griegas]: 500 pasos, promedio N=500 y N=501
                        +--> [curva "hoy"]: 200 pasos sobre la malla de precios
                        +--> [delta, gamma, theta]: del árbol; [vega, rho]: recálculo con σ/r desplazadas
                        +--> [aviso: modelo binomial americano (aproximación)]

[Pata con prima manual] --> {IV con el mismo modelo que la prima}
        | americano: ¿intrínseco < prima < límite superior?
        | europeo : límites sin arbitraje de Black-Scholes
        | no  --> [mensaje en español: fuera de límites / no identificable / días = 0 / pata de acción]
        | sí  --> [IV %] --> [botón "usar como volatilidad global" (igual que Etapa A)]

[Sin cambios] --> P&L vencimiento, métricas, PoP exacta, Monte Carlo (PoP exacta de referencia 0,5721)
```

## Acceptance Criteria (Testable Outcomes)

Escenarios tomados de `process/context/tests/all-tests.md`: pytest sobre el motor puro con valores de referencia de libro o calculados por fórmula (`pytest.approx`); la interfaz con el smoke test AppTest; lo visual y la persistencia entre pestañas, manualmente. Las referencias de Hull se comprueban con el árbol **sin promediar** y el N indicado.

**Modelo binomial (motor)**
- **AC-B1:** El árbol reproduce las referencias de Hull para puts americanos: S=50, K=52, r=5 %, σ=30 %, T=2 años, N=2 → 7,4284; S=K=50, r=10 %, σ=40 %, T=5/12, N=5 → 4,4885.
  proven by: binomial-americano-hull-put-1 + binomial-americano-hull-put-2 (tests con approx)
  strategy: Fully-Automated
- **AC-B2:** Convergencia y coherencia con Black-Scholes: con ejercicio europeo el árbol converge a Black-Scholes (put de referencia, N=1000: 6,2384 vs 6,2402, tolerancia ≈ 2e-3); un call americano con q=0 vale lo mismo que el europeo (Merton); la prima de ejercicio anticipado (americano − europeo) es ≥ 0 en una malla de casos; un put americano muy dentro del dinero vale su valor intrínseco; se cumplen los límites S·e^(−qT) − K ≤ C − P ≤ S − K·e^(−rT) para americanas.
  proven by: binomial-europeo-vs-BS + call-americano-q0 + prima-ejercicio-anticipado-no-negativa + put-profundo-ITM-intrínseco + límites-paridad-americana (tests)
  strategy: Fully-Automated
- **AC-B3:** La prima y las griegas usan el promedio de los árboles de N=500 y N=501 pasos; el promedio reduce el error respecto a un solo N en casos suaves (comprobación con referencia de alta precisión).
  proven by: promedio-N-N+1-reduce-error + pasos-500-por-defecto (tests)
  strategy: Fully-Automated

**Selector y alcance por subyacente**
- **AC-B4:** Por defecto, Acción y ETF usan el binomial; Índice usa siempre Black-Scholes y **todos sus números (primas, curva "hoy", griegas, IV) son idénticos** a los de MVP/Etapa A, con el selector en cualquier posición.
  proven by: índice-idéntico-a-BS-con-ambos-selectores + defecto-binomial-acción-ETF (tests de motor y analyze)
  strategy: Fully-Automated
- **AC-B5:** Con Black-Scholes seleccionado, Acción y ETF reproducen exactamente los números de la Etapa A (primas automáticas, curva "hoy", griegas, IV).
  proven by: BS-seleccionado-igual-a-etapa-A (tests de regresión contra el motor BS existente)
  strategy: Fully-Automated
- **AC-B6:** En Ajustes hay un selector "Binomial (americano) / Black-Scholes (europeo)" para Acción/ETF con texto explicativo; al cambiarlo se recalculan las primas automáticas y las griegas, las primas editadas a mano se conservan, y con Índice la interfaz indica que no tiene efecto. El selector persiste al cambiar de pestaña.
  proven by: selector-ajustes-recalcula-y-conserva-manuales (smoke AppTest); persistencia entre pestañas y disposición (manual)
  strategy: Hybrid

**Curva "hoy" y griegas**
- **AC-B7:** La curva "hoy" de Acción/ETF con binomial usa 200 pasos sobre la malla de precios y es coherente con la prima de 500 pasos (diferencia pequeña y acotada en el punto S actual); cumple valor ≥ intrínseco para opciones americanas y no produce NaN.
  proven by: curva-hoy-200-pasos-vs-500 + hoy-≥-intrínseco + sin-NaN (tests)
  strategy: Fully-Automated
- **AC-B8:** Delta, gamma y theta se obtienen del árbol; vega y rho por recálculo con σ y r desplazadas; unidades: theta por día, vega y rho por 1 punto. Caso de referencia (put ATM, N=500): delta ≈ −0,4422, gamma ≈ 0,0233, theta ≈ −0,01564/día, vega (+1 pt) ≈ 0,2763, rho (+1 pt) ≈ −0,1897. Signos y rangos correctos (delta put ∈ [−1,0]; gamma ≥ 0; vega ≥ 0), y las griegas de posición siguen siendo la suma de las de cada pata.
  proven by: griegas-binomial-referencia-put-ATM + griegas-signos-rangos + griegas-posición-suma (tests con tolerancia)
  strategy: Fully-Automated

**Volatilidad implícita**
- **AC-B9:** La IV usa el mismo modelo que la prima: ida y vuelta (prima del árbol → IV → prima del árbol) con error despreciable para puts y calls americanos ATM/OTM/ITM con volatilidades razonables; con Índice o Black-Scholes seleccionado la IV es la de la Etapa A; una prima igual al precio del modelo devuelve la volatilidad global.
  proven by: iv-americana-ida-y-vuelta + iv-igual-σ-global-prima-modelo + iv-índice-y-BS-igual-etapa-A (tests)
  strategy: Fully-Automated
- **AC-B10:** Límites americanos: límite inferior = valor intrínseco (sin descontar), y se comprueba antes de resolver. Una prima igual al intrínseco (p. ej. put muy ITM) o fuera de límites, días = 0 o pata de acción dan un **mensaje específico en español** ("no se puede identificar la IV…"), nunca un número engañoso ni una excepción. Incluye un caso de prima en el valor intrínseco donde el precio no varía con σ.
  proven by: iv-americana-prima-igual-intrínseco + iv-fuera-de-límites + iv-días-0 + iv-pata-acción + iv-nunca-lanza-excepción (tests de mensajes)
  strategy: Fully-Automated

**Lo que no cambia**
- **AC-B11:** Los resultados al vencimiento no cambian: P&L, métricas y breakevens son idénticos a los de la Etapa A; la PoP exacta del iron condor de referencia (Market('Acción', 100, 0,25, 45, 0,04, 0,01), comisiones por defecto) sigue siendo 0,5721 con cualquiera de los dos modelos; la simulación Monte Carlo con semilla 42 da los mismos resultados que antes.
  proven by: métricas-vencimiento-sin-cambios + pop-exacta-0.5721-con-ambos-modelos + monte-carlo-semilla-42-sin-cambios (tests de regresión)
  strategy: Fully-Automated

**Avisos**
- **AC-B12:** Los avisos se actualizan según el modelo activo: con binomial (Acción/ETF), dicen que primas, curva "hoy", griegas e IV usan el modelo americano (aproximación binomial); con Black-Scholes seleccionado (Acción/ETF), dicen que Black-Scholes subvalora los puts americanos, con error típico de 1–8 % y a veces mayor (medido hasta ~24 % muy dentro del dinero, vencimiento largo y volatilidad baja); en Índice se indica que son europeas. El aviso de escenarios de la Etapa A dice ahora que solo queda el modelo lognormal de precio final de estilo europeo (el ejercicio anticipado no importa al vencimiento). Se mantienen "modelo ≠ predicción", colas gruesas y "no es asesoría".
  proven by: avisos-según-modelo-y-subyacente + aviso-escenarios-actualizado (tests de la lógica de avisos); presencia visual (smoke AppTest + manual)
  strategy: Hybrid

**Rendimiento y validación**
- **AC-B13:** El cálculo es lo bastante rápido para no notarse: una prima con 500 pasos (promedio N y N+1) en el orden de decenas de milisegundos; la curva "hoy" de 401 puntos con 200 pasos en el orden de décimas de segundo; una IV americana en el orden de décimas de segundo; una estrategia de 4 patas (iron condor) se recalcula completa en un tiempo que no entorpece la interfaz. Los tests usan cotas holgadas.
  proven by: rendimiento-prima-500 + rendimiento-curva-hoy-200 + rendimiento-iv-americana + rendimiento-iron-condor-analyze (tests con cota holgada)
  strategy: Fully-Automated
- **AC-B14:** Casos límite sin NaN, infinitos ni excepciones, con ambos modelos: días = 0 (valor intrínseco, griegas "—"), volatilidad en el mínimo permitido, vencimientos muy cortos (1 día), muy largos, strikes muy alejados, tasa o dividend yield negativos/altos, prima 0, patas de acción (no usan el árbol). Mensajes de validación claros en español.
  proven by: casos-límite-sin-NaN-binomial + validación-mensajes (tests del motor); mensajes en pantalla (smoke AppTest)
  strategy: Hybrid

**Calidad**
- **AC-B15:** El código nuevo vive en el paquete puro del motor (se importa sin Streamlit), sin dependencias nuevas ni cambios de versiones fijadas; la API pública conserva los nombres existentes (identificadores en inglés, comentarios en español).
  proven by: motor-importa-sin-Streamlit (test en subproceso) + requirements.txt sin cambios (revisión de diff)
  strategy: Hybrid
- **AC-B16:** Los 910 tests existentes siguen en verde, **o** se actualizan de forma explícita y justificada los que suponían primas Black-Scholes para Acción/ETF (cada cambio documentado en el informe); los tests de Black-Scholes de Hull (`tests/test_pricing.py`) siguen en verde sin cambios; los tests de Índice no cambian; `.venv/bin/pytest` pasa completa desde la raíz; las decisiones 1–14 del MVP y A1–A11 de la Etapa A siguen vigentes salvo lo cambiado aquí.
  proven by: ejecución de `.venv/bin/pytest` (puerta de EXECUTE) + lista de tests actualizados con justificación (informe)
  strategy: Fully-Automated

## Locked Decisions (20-11-26)

Las decisiones 1–14 del MVP y A1–A11 de la Etapa A siguen vigentes salvo lo cambiado abajo.

| # | Decisión |
|---|---|
| B1 | Modelo: binomial Cox-Ross-Rubinstein (ejercicio americano) para Acción y ETF; Black-Scholes (europeo) se mantiene para Índice sin cambios. Un selector en Ajustes permite pasar Acción/ETF a Black-Scholes para comparar; por defecto binomial. Índice ignora el selector. |
| B2 | Pasos: 500 para primas y griegas, promediando N=500 y N=501 para amortiguar la oscilación; 200 pasos para la curva "hoy" sobre la malla de precios. |
| B3 | La volatilidad implícita usa el mismo modelo que la prima: árbol americano para Acción/ETF (límites sin arbitraje americanos: límite inferior = valor intrínseco, sin descontar) y Black-Scholes europeo para Índice; mensaje claro en español cuando la IV no se puede identificar (p. ej. prima en el valor intrínseco, donde el precio no depende de σ). |
| B4 | Monte Carlo, PoP exacta y métricas al vencimiento no cambian (el ejercicio anticipado no afecta al P&L al vencimiento); solo se actualiza el texto del aviso relacionado. |
| B5 | Avisos: con binomial activo, primas/"hoy"/griegas/IV usan el modelo americano (aproximación binomial); con Black-Scholes en Acción/ETF, subvalora los puts americanos (error típico 1–8 %, puede ser mayor; medido hasta ~24 % muy ITM, vencimiento largo, volatilidad baja). El aviso de escenarios de la Etapa A queda: solo permanece el modelo lognormal de estilo europeo (el ejercicio anticipado es irrelevante al vencimiento). |
| B6 | Griegas americanas: delta, gamma y theta del árbol (primeros pasos nativos); vega y rho por recálculo con desplazamiento; mismas unidades prácticas (theta por día, vega/rho por 1 punto). |

## Out Of Scope

- Comisión de cierre racional al vencimiento (Etapa B2, ciclo aparte; el elemento de backlog se mantiene y la decisión 6 del MVP sigue tal cual).
- Variantes del árbol más precisas (Leisen-Reimer u otras).
- Dividendos discretos (se mantiene el dividend yield continuo q).
- Datos de mercado en vivo y cadenas de opciones (Etapa C).
- Cambios en la lógica de Monte Carlo, PoP o métricas al vencimiento.
- Cambios en el comportamiento de Índice.
- Superficie/sonrisa de volatilidad, modelos de colas gruesas, reglas dependientes de la trayectoria.
- Asesoría de inversión.

## Constraints

- **Usuario:** nivel básico de Python; código sencillo; explicaciones cortas y claras; interfaz en español con términos de opciones en inglés.
- **Proceso:** el cálculo va en el paquete puro del motor (sin Streamlit); la app solo dibuja. Identificadores en inglés, comentarios/docstrings en español, UI en español. Tests con pytest (`.venv/bin/pytest`), floats con `pytest.approx`.
- **Técnico:** modelo CRR con dt=T/N, u=e^(σ√dt), d=1/u, p=(e^((r−q)dt) − d)/(u − d), descuento e^(−r·dt), valor de nodo = máx(continuación, intrínseco). Presupuesto de rendimiento: ≈ 18 ms por precio con N=500 y ≈ 59 ms para 401 puntos con N=200 (N=1000 sobre la malla, 2,7 s, es demasiado lento y queda descartado).
- **Dependencias:** sin dependencias nuevas; versiones fijadas (numpy 2.5.5, scipy 1.18.1, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0).
- **Mercado:** solo EE. UU.; multiplicador 100 por contrato y 1 por acción; índices europeos, acciones/ETF americanas.

## Open Questions

None. (Las decisiones B1–B6 del usuario del 20-11-26 cierran todas las preguntas abiertas.)

## Background / Research Findings

- **Hull (referencias de test):** put americano S=50, K=52, r=5 %, σ=30 %, T=2, N=2 → 7,4284; S=K=50, r=10 %, σ=40 %, T=5/12, N=5 → 4,4885. Con ejercicio europeo el árbol converge a Black-Scholes (N=1000 put 6,2384 vs 6,2402). Call americano con q=0 = europeo (Merton). Prima de ejercicio anticipado ≥ 0; put profundo ITM = intrínseco. Límites S·e^(−qT) − K ≤ C − P ≤ S − K·e^(−rT).
- **Oscilación:** promediar N y N+1 baja el error a ≈ 3e-3 con N=100 y ≈ 2e-4 con N=1000 en casos suaves.
- **Rendimiento medido (numpy vectorizado sobre precios):** un precio N=500 ≈ 18 ms; malla de 401 puntos con N=200 ≈ 59 ms; N=1000 sobre la malla 2,7 s.
- **Griegas del árbol (put ATM, N=500):** delta −0,4422, gamma 0,0233, theta −0,01564/día frente a Black-Scholes −0,4291 / 0,0221 / −0,01473; vega (+1 pt) 0,2763; rho (+1 pt) −0,1897 (BS −0,2457).
- **IV americana:** buscador de raíces sobre el precio del árbol converge en ≈ 7 evaluaciones (≈ 41 ms con N=200); los puts muy ITM en su valor intrínseco no tienen IV identificable (el precio es plano en σ).
- **Sesgo de Black-Scholes en puts americanos (r=4 %):** 30 días, q=0, σ 20 %: 0,5–2,3 %; 1 año, q=0, σ 20 %: 4,9–8,0 %; máximo visto 24 % (K=110, T=1 año, σ=10 %).
- **Tests existentes:** `tests/test_pricing.py` (valores de Hull de Black-Scholes) debe seguir en verde; los tests que asumen primas BS para Acción/ETF necesitarán actualización; la PoP exacta 0,5721 no depende de la prima.
- Fuentes: `DISENO.md` (hoja de ruta), SPEC y REPORT del MVP y de la Etapa A, `process/context/all-context.md`, backlog `process/general-plans/backlog/close-fee-rational-close_20-11-26.md`.

### Known gaps / Risks

| # | Riesgo o hueco | Tratamiento |
|---|---|---|
| B-G1 | **Rendimiento:** el árbol es mucho más caro que una fórmula; N=1000 sobre la malla es inviable (2,7 s). | 500 pasos para primas y 200 para la curva "hoy"; cotas de tiempo en tests (AC-B13). |
| B-G2 | **IV no identificable:** con la prima en el valor intrínseco (puts muy ITM) el precio no depende de σ. | Mensaje claro en español, nunca un número falso (AC-B10). |
| B-G3 | **Árbol = aproximación:** oscilación residual aun promediando N y N+1; la curva "hoy" (200 pasos) es algo menos precisa que la prima (500). | Aviso "aproximación binomial" (AC-B12); promedio N/N+1 (AC-B3); diferencia acotada (AC-B7). |
| B-G4 | **Dividendos continuos solamente:** el dividend yield q no representa dividendos discretos, que afectan al ejercicio anticipado de calls. | Fuera de alcance; se mantiene la limitación conocida. |
| B-G5 | **Vega y rho por recálculo** dependen del tamaño del desplazamiento y heredan el ruido del árbol. | Tolerancias razonables frente a la referencia (AC-B8). |
| B-G6 | **Tests existentes** que asumen BS para Acción/ETF fallarán. | Actualización explícita y justificada (AC-B16). |
| B-G7 | **Sin tests de UI visuales ni de persistencia entre pestañas** (mismo hueco que MVP y Etapa A). | Smoke AppTest para estructura; revisión manual del usuario. |
| B-G8 | **Dos modelos conviven:** Índice (BS) y Acción/ETF (binomial) pueden confundir al comparar. | Textos del selector y avisos según subyacente (AC-B6, AC-B12). |

## Definition of Done (Etapa B1)

- Los 16 criterios AC-B1…AC-B16 se cumplen; los Hybrid pasan además la revisión manual del usuario.
- Los 910 tests existentes siguen en verde o se actualizan de forma explícita y justificada; los tests de Black-Scholes de Hull y los de Índice no cambian; `.venv/bin/pytest` completa desde la raíz.
- La app arranca con `.venv/bin/streamlit run app.py`: Acción/ETF usan el binomial por defecto, el selector de Ajustes permite comparar con Black-Scholes, Índice no cambia.
- Resultados al vencimiento, PoP exacta (0,5721 de referencia) y Monte Carlo idénticos a la Etapa A.
- Avisos actualizados y textos de UI en español; cero fallos ante entradas inválidas; sin dependencias nuevas.
