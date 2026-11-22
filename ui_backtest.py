"""Pestaña "Backtest" de la app (Etapa C2): calibración de la PoP con el histórico.

Qué hace: recorre fechas pasadas, calcula con los datos de ese día la PoP
que la app habría dado para una plantilla y mira si de verdad ganó. Mide
la CALIBRACIÓN de las probabilidades, no la rentabilidad real (no hay
precios históricos de opciones).

Reglas de esta pestaña (para que abrir la app sea rápido y seguro):
- Nada pesado sin pulsar un botón: el proveedor de datos se crea SOLO al
  pulsar "Cargar histórico" (se recibe una función, no el proveedor).
- Los controles siguen el patrón de Ajustes: cada widget (`bt_*_input`)
  copia su valor a una entrada simple (`bt_*`) con un callback, porque las
  pestañas son "perezosas" y un widget no dibujado pierde su valor.
- Lo que dejan los botones (`bt_history`, `bt_result`, `bt_error`) no son
  widgets, así que se puede escribir en el cuerpo de la pestaña.

Este archivo no importa app.py (app.py ejecuta la app al importarse).
"""

import streamlit as st

from datos import DatosError, HistoryProvider, history_age_text, load_history
from datos.tickers import MANUAL_ENTRY
from opciones import TEMPLATES
from opciones.backtest import first_analyzed_index, to_day_numbers

# ---------------------------------------------------------------------------
# Valores por defecto, rangos y textos
# ---------------------------------------------------------------------------

# Entradas simples de session_state y su valor inicial.
BT_DEFAULTS = {
    "bt_template": "iron_condor",
    "bt_horizon": 30,  # H: días naturales hasta el vencimiento
    "bt_window": 30,  # W: sesiones de la ventana de volatilidad realizada
    "bt_step": 5,  # cada cuántas sesiones se toma una fecha
    "bt_years": 10,  # años a analizar (se descarga uno más)
    "bt_fees": True,  # con comisiones de Ajustes
    "bt_use_mu": False,  # segunda línea con el μ histórico
}

# Rangos (mínimo, máximo) de los controles numéricos (todos enteros).
BT_LIMITS = {
    "bt_horizon": (7, 120),
    "bt_window": (10, 250),
    "bt_step": (1, 20),
    "bt_years": (1, 15),
}

# Etiquetas de las plantillas, calculadas una vez (format_func no puede
# leer session_state ni el reloj: AppTest la vuelve a llamar fuera del guion).
TEMPLATE_KEYS = [template.key for template in TEMPLATES]
TEMPLATE_NAMES = {template.key: template.name for template in TEMPLATES}
TEMPLATES_BY_KEY = {template.key: template for template in TEMPLATES}

MSG_BT_INTRO = (
    "Recorre fechas pasadas: con los datos de cada día calcula la PoP que habría dado "
    "la app y mira si la estrategia ganó de verdad al vencimiento."
)
MSG_BT_YEARS_CAPTION = (
    "Se descargan los años elegidos + 1 de calentamiento; "
    "cambiar a más años obliga a volver a descargar."
)
MSG_BT_MANUAL = (
    "Elige un ticker de la lista en la barra lateral para cargar su histórico "
    "(con «Entrada manual» no hay datos que estudiar)."
)
MSG_BT_NO_PROVIDER = (
    "No se pudo usar el proveedor de datos para descargar el histórico "
    "(no está disponible o no ofrece histórico)."
)
MSG_BT_HISTORY_RANGE = "{n} sesiones de {symbol}, del {first} al {last}."


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------


def init_backtest_state() -> None:
    """Crea las entradas de la pestaña la primera vez (sin pisar las existentes)."""
    for key, value in BT_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("bt_history", None)
    st.session_state.setdefault("bt_result", None)
    st.session_state.setdefault("bt_error", None)


def clear_backtest_state() -> None:
    """Olvida el histórico, el resultado y el error (p. ej. al cambiar de ticker)."""
    st.session_state["bt_history"] = None
    st.session_state["bt_result"] = None
    st.session_state["bt_error"] = None


def copy_bt_param(field: str) -> None:
    """Callback: copia el widget `field_input` a su entrada simple `field`."""
    st.session_state[field] = st.session_state[f"{field}_input"]


# ---------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------


def _number_control(label: str, field: str, help_text: str) -> None:
    """Un control numérico entero con su rango y el patrón de callback."""
    low, high = BT_LIMITS[field]
    st.number_input(
        label,
        min_value=low,
        max_value=high,
        step=1,
        value=int(st.session_state[field]),
        key=f"{field}_input",
        on_change=copy_bt_param,
        args=(field,),
        help=help_text,
    )


def render_controls() -> None:
    """Plantilla, horizonte, ventana, paso, años, comisiones y línea μ."""
    st.selectbox(
        "Plantilla",
        TEMPLATE_KEYS,
        index=TEMPLATE_KEYS.index(st.session_state["bt_template"]),
        format_func=TEMPLATE_NAMES.get,
        key="bt_template_input",
        on_change=copy_bt_param,
        args=("bt_template",),
    )
    left, right = st.columns(2)
    with left:
        _number_control("Horizonte H (días)", "bt_horizon", "Días naturales hasta el vencimiento.")
        _number_control(
            "Ventana de volatilidad W (sesiones)",
            "bt_window",
            "Sesiones de bolsa con las que se mide la volatilidad realizada.",
        )
    with right:
        _number_control("Paso (sesiones)", "bt_step", "Se analiza una fecha cada este número de sesiones.")
        _number_control("Años a analizar", "bt_years", "Años de historia que se recorren.")
        st.caption(MSG_BT_YEARS_CAPTION)
    st.checkbox(
        "Con comisiones (las de Ajustes)",
        value=st.session_state["bt_fees"],
        key="bt_fees_input",
        on_change=copy_bt_param,
        args=("bt_fees",),
    )
    st.checkbox(
        "Añadir línea con la tendencia histórica (μ de 12 meses)",
        value=st.session_state["bt_use_mu"],
        key="bt_use_mu_input",
        on_change=copy_bt_param,
        args=("bt_use_mu",),
    )


# ---------------------------------------------------------------------------
# "Cargar histórico"
# ---------------------------------------------------------------------------


def load_clicked(get_provider, ticker: str, now, cache_dir) -> None:
    """Pulsado "Cargar histórico": crea el proveedor (solo aquí) y carga.

    Escribe `bt_history` ({"ticker", "load", "notices"}) o `bt_error`.
    """
    provider = get_provider()
    if provider is None or not isinstance(provider, HistoryProvider):
        st.session_state["bt_history"] = None
        st.session_state["bt_error"] = MSG_BT_NO_PROVIDER
        return
    years = int(st.session_state["bt_years"])
    try:
        with st.spinner("Cargando histórico…"):
            load, notices = load_history(provider, ticker, years, now=now, cache_dir=cache_dir)
    except DatosError as error:
        st.session_state["bt_history"] = None
        st.session_state["bt_error"] = error.message
        return
    st.session_state["bt_history"] = {"ticker": ticker, "load": load, "notices": list(notices)}
    st.session_state["bt_error"] = None


def current_history(ticker: str):
    """El histórico cargado de ESTE ticker, o None."""
    loaded = st.session_state.get("bt_history")
    if loaded is None or loaded["ticker"] != ticker:
        return None
    return loaded


def render_history_status(loaded, now) -> None:
    """Antigüedad, rango de fechas, avisos de la carga y aviso de años cortos."""
    load = loaded["load"]
    history = load.history
    st.caption(history_age_text(load, now))
    st.caption(
        MSG_BT_HISTORY_RANGE.format(
            n=len(history.dates),
            symbol=load.symbol or history.ticker,
            first=history.dates[0],
            last=history.dates[-1],
        )
    )
    for message in loaded["notices"]:
        st.warning(message)
    _index, _years, short_warning = first_analyzed_index(
        to_day_numbers(history.dates),
        int(st.session_state["bt_window"]),
        int(st.session_state["bt_years"]),
    )
    if short_warning:
        st.warning(short_warning)


# ---------------------------------------------------------------------------
# Pestaña
# ---------------------------------------------------------------------------


def render_backtest(get_provider, now, settings, underlying, ticker, fallback_rate, cache_dir) -> None:
    """Dibuja la pestaña Backtest.

    - get_provider: FUNCIÓN que devuelve el proveedor (o None); solo se
      llama al pulsar "Cargar histórico".
    - now: hora actual (reloj inyectable); settings: comisiones de Ajustes;
      underlying: tipo de subyacente; ticker: etiqueta curada o "Entrada
      manual"; fallback_rate: tasa de la barra lateral (fracción);
      cache_dir: carpeta de la caché (None = .cache_datos/).
    """
    st.subheader("📈 Backtest de calibración de la PoP", divider=True)
    st.caption(MSG_BT_INTRO)
    render_controls()

    manual = ticker == MANUAL_ENTRY
    if manual:
        st.info(MSG_BT_MANUAL)

    if st.button("📥 Cargar histórico", key="bt_load", disabled=manual):
        load_clicked(get_provider, ticker, now, cache_dir)

    if st.session_state.get("bt_error"):
        st.error(st.session_state["bt_error"])
    loaded = None if manual else current_history(ticker)
    if loaded is not None:
        render_history_status(loaded, now)

    st.button("▶️ Calcular", key="bt_run", disabled=manual)
