# Laboratorio de Opciones — Documento de diseño

> **Versión:** 0.1 · **Fecha:** 19/11/2026 · **Estado:** idea acordada, antes de programar

Este documento recoge qué vamos a construir y por qué. Sirve de guía mientras programamos: si surge una duda, se consulta aquí, y si cambiamos de idea, se actualiza aquí.

---

## 1. Visión

**Un laboratorio de estrategias con opciones:** construyes una estrategia, ves cómo gana o pierde, entiendes *por qué*, y la comparas con otras antes de operar.

El proyecto tiene **dos objetivos a la vez**:

| | **Aprender** | **Analizar** |
|---|---|---|
| Para qué | Entender cómo funciona cada estrategia | Evaluar una operación concreta |
| Datos | Ejemplos con números sencillos | Precios reales o introducidos a mano |
| Qué muestra | Explicaciones y escenarios "qué pasa si…" | Métricas, griegas y comparativas |

> **Por qué:** el objetivo es tanto aprender como usarlo de verdad. Las dos cosas comparten el mismo motor de cálculo, así que no cuesta el doble: solo cambia cómo se presenta la información.

> **Aviso:** es una herramienta de estudio y análisis, no un asesor de inversión. Los resultados dependen de modelos con supuestos simplificados.

---

## 2. Idea central: una estrategia es una lista de "patas"

Cualquier estrategia, por compleja que sea, se describe como una lista de **patas**. Cada pata tiene:

- **Tipo:** call, put o acción (el propio subyacente)
- **Dirección:** compra (long) o venta (short)
- **Strike, prima, cantidad y vencimiento**

Ejemplos: una *covered call* son 2 patas (acción comprada + call vendida) y un *iron condor* son 4 patas.

> **Por qué:** con una sola pieza básica, que sabe calcular su resultado y se puede sumar a otras, el programa puede simular **cualquier** estrategia, no solo las que programemos una a una. Además, el "diseñador de estrategias" sale gratis: diseñar es combinar patas.

---

## 3. Casos de uso

1. **"Quiero ver qué es un iron condor"** → lo abro desde el catálogo y veo su gráfico, su explicación y cuándo se usa.
2. **"Creo que Apple subirá algo en un mes"** → busco estrategias alcistas y las comparo. *(sugerencias automáticas: v4)*
3. **"Tengo esta idea de 3 patas"** → la construyo a mano y veo pérdida máxima, beneficio máximo y puntos de equilibrio.
4. **"¿Qué pasa si baja la volatilidad o pasan 10 días?"** → muevo deslizadores y el gráfico cambia al momento.
5. **"¿Qué probabilidad tengo de ganar?"** → la app hace una simulación Monte Carlo y me da un porcentaje. *(v2)*
6. **"Quiero guardar esta estrategia y revisarla mañana"** → la guardo con un nombre. *(v3)*

---

## 4. Pantallas

```
┌─────────────────────────────────────────────────────────┐
│  📚 Catálogo   🛠️ Constructor   🎲 Simulador   ⚖️ Comparar │
├───────────────┬─────────────────────────────────────────┤
│ Subyacente    │                                         │
│ Precio: 100   │        [ Gráfico de P&L ]               │
│ Volat.: 25%   │   curva hoy ---- / al vencimiento ___   │
│ Días: 30      │                                         │
│               ├─────────────────────────────────────────┤
│ Patas:        │ Máx. beneficio: 350 │ Máx. pérdida: -150│
│ + Compra Call │ Breakeven: 101.5    │ Comisiones: -2.60 │
│   K=100 x1    ├─────────────────────────────────────────┤
│ + Venta Call  │ Griegas: Δ 0.32  Γ 0.02  Θ -1.2  V 8.1  │
│   K=105 x1    │                                         │
│ [+ añadir]    │ 💡 "Ganas si sube moderadamente…"        │
└───────────────┴─────────────────────────────────────────┘
```

| Pantalla | Qué hace | Versión |
|---|---|---|
| **Catálogo** | Fichas de las estrategias clásicas: qué apuesta, riesgo, cuándo usarla y botón "abrir en el constructor" | MVP |
| **Constructor** | El corazón de la app: añadir o quitar patas y ver gráfico y métricas al momento | MVP |
| **Simulador** | Deslizadores de precio, tiempo y volatilidad, más simulación Monte Carlo | Deslizadores: MVP · Monte Carlo: v2 |
| **Comparar** | 2 o 3 estrategias superpuestas en el mismo gráfico | v3 |
| **Ajustes** | Comisiones y preferencias | MVP |

> **Por qué:** separar "aprender" (catálogo) de "construir" (constructor) mantiene cada pantalla sencilla. El constructor va primero porque todo lo demás se apoya en él.

---

## 5. Mercado y subyacentes

**Mercado: Estados Unidos.** Se admiten tres tipos de subyacente:

| Tipo | Ejemplos | Tipo de opción | Liquidación |
|---|---|---|---|
| Acciones | AAPL, MSFT, TSLA | Americana | Entrega de acciones |
| ETFs de índices | SPY, QQQ, IWM | Americana | Entrega de acciones |
| Índices | SPX, NDX, RUT | **Europea** | En efectivo |

- 1 contrato = **100 unidades** del subyacente (multiplicador 100).
- La app indica en cada caso si la opción es **americana** o **europea**.
- Si los datos de un índice salen incompletos, se puede usar su ETF equivalente (SPX → SPY, NDX → QQQ, RUT → IWM).

> **Por qué EE. UU.:** es el mercado de opciones más líquido del mundo y el único con datos gratuitos y fáciles de conseguir (Yahoo Finance). En Europa los datos gratuitos escasean.

> **Por qué incluir índices:** las opciones sobre índices son europeas, el caso exacto para el que está pensado Black-Scholes. Si Yahoo falla con ellas, los ETFs dan casi el mismo resultado con datos más fiables.

---

## 6. Modelo de valoración

- **Al vencimiento:** cálculo exacto (el valor intrínseco de cada pata).
- **Antes del vencimiento ("hoy", "en N días"):** modelo **Black-Scholes**.
- **Griegas:** delta, gamma, theta, vega y rho, calculadas con Black-Scholes.

**Limitación conocida:** Black-Scholes es exacto para opciones europeas y una aproximación para las americanas (porque permiten el ejercicio anticipado). La app lo avisa cuando aplica.

> **Por qué Black-Scholes:** es el modelo estándar, tiene una fórmula cerrada fácil de programar y entender, y para aprender y comparar estrategias la diferencia con modelos más complejos casi nunca importa. Si algún día hace falta, se puede añadir un modelo binomial para las americanas.

---

## 7. Comisiones

Configurables en **Ajustes**, con valores de partida:

| Parámetro | Valor de partida | Explicación |
|---|---|---|
| Comisión por contrato | **0,65 $** | Tarifa típica de broker minorista en EE. UU. |
| Recargo para opciones sobre índices | **0,60 $** por contrato | El SPX y similares tienen tasas de mercado más altas |
| Incluir cierre | **Sí** | Cuenta la comisión al abrir y también al cerrar |

Las comisiones se **restan del P&L**: mueven el gráfico, las métricas y los puntos de equilibrio.

> **Por qué configurables:** cada broker cobra distinto. Con valores de partida la app funciona desde el primer momento, pero puedes ajustarla a tu broker real.

> **Por qué importa:** en estrategias de varias patas con poco beneficio (un iron condor, por ejemplo), las comisiones pueden decidir si una operación compensa o no.

---

## 8. Catálogo de estrategias (MVP: 8)

| Estrategia | Visión de mercado | Patas |
|---|---|---|
| Long call | Alcista | 1 |
| Long put | Bajista | 1 |
| Covered call | Neutral / ligeramente alcista | 2 |
| Protective put | Alcista con protección | 2 |
| Bull call spread | Moderadamente alcista | 2 |
| Bear put spread | Moderadamente bajista | 2 |
| Long straddle | Gran movimiento (cualquier dirección) | 2 |
| Iron condor | Lateral, poco movimiento | 4 |

Cada ficha incluye: qué apuesta, beneficio y pérdida máximos, cuándo usarla y sus riesgos.

> **Por qué estas 8:** cubren todas las visiones de mercado (alcista, bajista, lateral, volátil) y van de 1 a 4 patas, así que sirven de curso progresivo. Añadir más después es solo añadir plantillas.

---

## 9. Hoja de ruta por versiones

### MVP (v1): el motor y el constructor
- Datos introducidos **a mano**: precio, volatilidad, días al vencimiento y tipo de interés
- Constructor de patas: call, put y acción
- Gráfico de P&L **hoy** y **al vencimiento**
- Métricas: beneficio máximo, pérdida máxima y breakeven
- Griegas
- Comisiones configurables
- Catálogo de 8 estrategias

### v2: datos reales y probabilidades
- Cadenas de opciones desde Yahoo Finance (acciones, ETFs e índices)
- Cálculo propio de la volatilidad implícita
- Simulación Monte Carlo: probabilidad de beneficio y valor esperado

### v3: comparar y guardar
- Comparador de 2 o 3 estrategias
- Guardar y cargar estrategias con nombre

### v4: asistente
- Sugerencias de estrategias según tu visión del mercado (dirección, plazo, volatilidad)

### Más adelante (opcional)
- Backtesting histórico (los datos históricos de opciones suelen ser de pago)
- Modelo binomial para opciones americanas

> **Por qué empezar sin datos reales:** conectar con un servicio externo da problemas (caídas, formatos raros, mercado cerrado) que distraen de lo importante. Primero hay que tener un motor correcto y entendido; los datos reales se enchufan después sin cambiarlo.

---

## 10. Tecnología

| Herramienta | Para qué | Por qué |
|---|---|---|
| **Python** | Lenguaje del proyecto | Fácil de leer, es el estándar en finanzas cuantitativas |
| **numpy** | Cálculos con muchos precios a la vez | Rápido y sencillo |
| **scipy** | Distribución normal para Black-Scholes | Ya trae lo necesario |
| **plotly** | Gráficos interactivos | Zoom y valores al pasar el ratón, sin esfuerzo |
| **Streamlit** | App web | Se escribe en Python puro, sin HTML ni JavaScript |
| **yfinance** | Datos de mercado (v2) | Gratuito y sin registro |
| **pytest** | Tests | En finanzas, un error de signo cambia todo el resultado |

> **Por qué Streamlit:** con nivel básico de Python permite tener una app web funcional muy rápido. El estilo es sencillo, que es justo lo acordado.

---

## 11. Datos: limitaciones conocidas

- Los datos de Yahoo llegan con **unos 15 minutos de retraso**: válidos para analizar, no para operar al instante.
- La **volatilidad implícita** de Yahoo a veces es poco fiable, por eso la app la calculará ella misma a partir del precio de la opción.
- Los datos de **índices** pueden venir incompletos; la alternativa es el ETF equivalente.
- Con el mercado cerrado, los precios pueden estar desactualizados o vacíos.

---

## 12. Forma de trabajo

- Se avanza **por bloques pequeños**: cada uno se explica brevemente, se programa y se revisa juntos.
- Explicaciones **claras y cortas**, centradas en el porqué.
- Interfaz **en español**, manteniendo los términos en inglés habituales (call, put, strike, delta…), que son los que encontrarás en brokers y libros.
- Cada parte del motor tendrá **tests** que comprueben casos conocidos (por ejemplo, que un bull spread nunca pierde más de lo pagado).

> **Por qué así:** el objetivo también es aprender. Con bloques pequeños entiendes cada pieza y puedes modificarla tú mismo, en lugar de recibir una app grande que no sabrías tocar.

---

## 13. Lecturas recomendadas

- **John Hull**, *Options, Futures and Other Derivatives*: la referencia clásica de la teoría.
- **Sheldon Natenberg**, *Option Volatility and Pricing*: más práctico, centrado en estrategias y volatilidad.
