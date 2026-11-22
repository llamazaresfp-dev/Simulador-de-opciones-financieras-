# 🎓 Laboratorio de Opciones

**Simulador de estrategias con opciones financieras del mercado de EE. UU., hecho para aprender.**

Construyes una estrategia (una *covered call*, un *iron condor*…), ves en un gráfico cuánto ganas o pierdes según el precio del subyacente, entiendes *por qué* y la comparas antes de operar.

> ⚠️ **Proyecto de aprendizaje.** Es una herramienta de estudio, **no un asesor de inversión**. Los resultados dependen de modelos con supuestos simplificados y de datos gratuitos con retraso. No lo uses para tomar decisiones reales de inversión.

---

## ¿Por qué existe este proyecto?

Lo construí para aprender dos cosas a la vez:

- **Opciones financieras:** cómo se valora una opción, qué son las griegas, qué hace cada estrategia y cuándo tiene sentido.
- **Programación en Python:** partiendo de nivel básico, con código sencillo y explícito, comentarios en español y tests para comprobar que los cálculos son correctos.

Se desarrolló por etapas pequeñas (MVP → Monte Carlo → modelo binomial → datos reales → backtest → comparar y guardar estrategias), cada una con su especificación, su plan y sus tests. El documento [`DISENO.md`](DISENO.md) explica qué se decidió y por qué.

---

## ✨ Qué hace

La app tiene seis pestañas:

| Pestaña | Para qué sirve |
|---|---|
| 📊 **Catálogo** | 8 estrategias clásicas (long call, long put, covered call, protective put, bull call spread, bear put spread, long straddle, iron condor) con explicación, riesgos y un botón para abrirlas en el constructor. |
| 🛠️ **Constructor** | Combina "patas" (calls, puts y acciones, compradas o vendidas) y ve al momento el gráfico de P&L hoy y al vencimiento, beneficio y pérdida máximos, puntos de equilibrio y griegas. Incluye una simulación **Monte Carlo** con la probabilidad de beneficio y la volatilidad implícita de cada pata. Al final puedes **guardar** la estrategia con un nombre. |
| ⚖️ **Comparar** | Hasta 4 estrategias (la del constructor y 3 guardadas) en el mismo gráfico al vencimiento, con una tabla lado a lado: beneficio y pérdida máximos, breakevens, comisiones, prima neta, probabilidad de beneficio y, si quieres, curvas "hoy" y griegas. Todas se valoran con el mercado actual. |
| 💾 **Mis estrategias** | Lista de estrategias guardadas: abrirlas en el constructor (con su mercado o solo sus patas), añadirlas a la comparación, borrarlas, y descargarlas o subirlas como archivo JSON. |
| ⚙️ **Ajustes** | Comisiones configurables (por contrato, recargo para índices, cierre) y el modelo de valoración (binomial o Black-Scholes). |
| 📈 **Backtest** | Comprueba con el histórico real del subyacente si la probabilidad de beneficio que da la app se cumple: gráfico de fiabilidad, puntuación de Brier y análisis de colas. |

**Otras características:**

- **Datos reales gratuitos** de Yahoo Finance (≈15 min de retraso) para una lista de subyacentes muy líquidos: SPX, SPY, QQQ, IWM, AAPL, MSFT, NVDA, AMZN, META, GOOGL y TSLA. Solo se ofrecen opciones con liquidez suficiente.
- **Modelos de valoración:** Black-Scholes para índices (opciones europeas) y árbol binomial de Cox-Ross-Rubinstein para acciones y ETF (opciones americanas).
- **Caché local:** los datos descargados se guardan en disco, así que la app funciona aunque falle la conexión.
- **Estrategias guardadas:** se guardan en la carpeta local `.estrategias/` (no se sube a git). Los archivos JSON que subes se revisan antes de usarlos: un archivo roto o manipulado da un mensaje claro y nunca rompe la app.
- **Más de 3000 tests** automáticos que comprueban los cálculos contra valores conocidos (Hull, paridad put-call, etc.).

---

## 🚀 Cómo ejecutarlo

### Requisitos

- **Python 3.12** (otras versiones 3.10+ probablemente funcionen, pero no están probadas).
- Conexión a internet solo para descargar datos reales; el resto funciona sin red.

### 1. Clonar el repositorio

```bash
git clone https://github.com/llamazaresfp-dev/Simulador-de-opciones-financieras-.git
cd Simulador-de-opciones-financieras-
```

### 2. Crear un entorno virtual e instalar dependencias

**Linux / macOS:**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

> En Ubuntu/Debian, si `venv` da error, instala antes el paquete del sistema: `sudo apt install python3.12-venv`.

### 3. Arrancar la app

**Linux / macOS:**

```bash
.venv/bin/streamlit run app.py
```

**Windows:**

```powershell
.venv\Scripts\streamlit run app.py
```

Se abrirá en el navegador en <http://localhost:8501>.

### 4. Primeros pasos

1. En **📊 Catálogo**, elige una estrategia y pulsa **"Abrir en el constructor"**.
2. En **🛠️ Constructor**, cambia el precio, la volatilidad o los días en la barra lateral y mira cómo cambia el gráfico.
3. Para usar datos reales: en la barra lateral elige un **ticker** (p. ej. SPY), pulsa **"Cargar datos"**, elige un vencimiento y añade patas desde la cadena real.
4. Al final del constructor, escribe un nombre y pulsa **"Guardar"**. En **💾 Mis estrategias** añade varias a la comparación y míralas juntas en **⚖️ Comparar**.
5. En **📈 Backtest**, con un ticker elegido, pulsa **"Cargar histórico"** y luego **"Calcular"**.

---

## 🧪 Tests

```bash
.venv/bin/pytest -q
```

Los tests **no usan internet**: trabajan con datos grabados y un proveedor falso. Hay una prueba opcional contra Yahoo real que solo se ejecuta si la activas a propósito:

```bash
LIVE_DATA=1 .venv/bin/pytest tests/test_datos_live.py -q
```

---

## 📁 Estructura del proyecto

```
app.py            Interfaz web (Streamlit): pestañas, barra lateral y gráficos
ui_backtest.py    Pestaña "Backtest"
ui_comparar.py    Pestaña "Comparar"
ui_estrategias.py Pestaña "Mis estrategias" y apartado "Guardar"
opciones/         Motor de cálculo puro (sin interfaz ni red)
  pricing.py        Black-Scholes y griegas
  binomial.py       Árbol binomial para opciones americanas
  payoff.py         P&L al vencimiento y "hoy"
  metrics.py        Beneficio/pérdida máximos y puntos de equilibrio
  simulation.py     Probabilidad exacta y Monte Carlo
  implied_vol.py    Volatilidad implícita
  catalog.py        Las 8 estrategias del catálogo
  backtest.py       Backtest histórico
  calibration.py    Estadísticas de calibración (Brier, Wilson, colas)
datos/            Descarga de datos de mercado, filtros de liquidez y caché local
estrategias/      Guardar, cargar y validar estrategias (JSON) y cálculos de la comparación
tests/            Tests automáticos (pytest)
DISENO.md         Documento de diseño: qué se decidió y por qué
process/          Especificaciones, planes e informes de cada etapa
```

La idea central: **una estrategia es una lista de patas**. Cada pata sabe calcular su resultado y el total es la suma, así que la app puede simular cualquier combinación, no solo las del catálogo.

---

## 🛠️ Tecnologías

[Python](https://www.python.org/) · [Streamlit](https://streamlit.io/) · [NumPy](https://numpy.org/) · [SciPy](https://scipy.org/) · [Plotly](https://plotly.com/python/) · [yfinance](https://github.com/ranaroussi/yfinance) · [pytest](https://pytest.org/)

---

## ⚠️ Limitaciones conocidas

- **Modelos simplificados:** Black-Scholes y el árbol binomial suponen volatilidad constante y precios lognormales; los mercados reales tienen saltos y "colas gordas".
- **Datos de Yahoo Finance:** gratuitos pero no oficiales, con ≈15 min de retraso y límites de peticiones. Con el mercado cerrado puede no haber opciones líquidas (por ejemplo, el SPX en fin de semana).
- **El backtest mide probabilidades, no rentabilidad real:** no hay precios históricos de opciones gratuitos, así que usa la volatilidad realizada en lugar de la implícita.
- **Comisiones orientativas:** ajústalas en ⚙️ Ajustes a las de tu broker.

---

## 📚 Para aprender más

- **John C. Hull**, *Options, Futures and Other Derivatives*: la referencia clásica de la teoría.
- **Sheldon Natenberg**, *Option Volatility and Pricing*: más práctico, centrado en estrategias y volatilidad.

---

## 🤖 Cómo se hizo

Desarrollado con ayuda de [Claude Code](https://claude.com/claude-code), siguiendo una metodología por fases (investigar → especificar → diseñar → planificar → validar → implementar), con tests en cada paso. Los documentos de cada etapa están en [`process/general-plans/completed/`](process/general-plans/completed/).
