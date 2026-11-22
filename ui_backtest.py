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

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from scipy.stats import norm

from datos import (
    DatosError,
    HistoryProvider,
    covers,
    history_age_text,
    load_history,
    start_for_years,
)
from datos.tickers import MANUAL_ENTRY
from opciones import TEMPLATES, CommissionSettings
from opciones.backtest import MSG_NO_DATES, first_analyzed_index, run_backtest, to_day_numbers
from opciones.calibration import (
    EXPECTED_GT2,
    EXPECTED_LT_M2,
    brier_score,
    brier_skill,
    calibration_bins,
    climatological_brier,
    effective_n,
    max_deviation,
    tail_diagnostics,
)
from opciones.validation import MSG_NOT_ADVICE

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
MSG_BT_ESTIMATE = "≈ {n} fechas, ~{seconds} s"
MSG_BT_NEED_HISTORY = "Primero pulsa «Cargar histórico»: no hay histórico cargado de este ticker."
MSG_BT_NOT_COVERED = "El histórico cargado no cubre {years} años: pulsa «Cargar histórico»"
MSG_BT_PARAMS_CHANGED = (
    "Los parámetros cambiaron: pulsa «Calcular» para ver el resultado con los valores nuevos."
)

# Avisos fijos del resultado (qué mide y qué no).
MSG_BT_WHAT = (
    "Mide calibración de probabilidades, no rentabilidad real: "
    "no hay precios históricos de opciones."
)
MSG_BT_REALIZED_VOL = (
    "La volatilidad usada es la realizada (histórica) de las últimas W sesiones, "
    "no la implícita que cobraba el mercado ese día."
)
MSG_BT_AMERICAN = (
    "Las opciones se valoran como europeas (Black-Scholes), aunque las de acciones y ETF "
    "sean americanas."
)
MSG_BT_Q = "El dividendo q se aproxima con los dividendos pagados en los 12 meses previos."
MSG_BT_OVERLAP = (
    "Las ventanas de H días de fechas cercanas se solapan: los casos no son independientes. "
    "N efectivo ≈ años analizados · 365 / H es el número de casos «de verdad» distintos."
)
MSG_BT_TAILS = (
    "Si los movimientos extremos son más frecuentes que en la normal, la causa son las "
    "colas gordas del modelo + ruido de volatilidad: la PoP de estrategias que dependen "
    "de que no haya grandes movimientos sale optimista."
)

# Coste medido por fecha (motor, Black-Scholes): ~3 ms; con la línea μ, el doble.
SECONDS_PER_DATE = 0.003

# Colores (los mismos tonos que COLOR_SYSTEM de app.py; sirven en ambos temas).
COLOR_POINTS = "#3b82f6"
COLOR_MU = "#f59e0b"
COLOR_FEW = "#64748b"
COLOR_DIAGONAL = "#8a8985"


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

    if loaded is not None:
        st.caption(estimate_text(loaded))

    if st.button("▶️ Calcular", key="bt_run", disabled=manual):
        run_clicked(now, settings, underlying, ticker, fallback_rate)

    if not manual:
        render_result_area(settings, underlying, ticker, fallback_rate)


# ---------------------------------------------------------------------------
# "Calcular"
# ---------------------------------------------------------------------------


def _first_index(history) -> int:
    """Primera sesión analizada según la ventana y los años elegidos."""
    index, _years, _warning = first_analyzed_index(
        to_day_numbers(history.dates),
        int(st.session_state["bt_window"]),
        int(st.session_state["bt_years"]),
    )
    return index


def _decimal(value: float, digits: int = 1) -> str:
    """Número con coma decimal (estilo español)."""
    return f"{value:.{digits}f}".replace(".", ",")


def estimate_text(loaded) -> str:
    """Caption "≈ N fechas, ~X s" antes de calcular."""
    history = loaded["load"].history
    count = len(range(_first_index(history), len(history.dates), int(st.session_state["bt_step"])))
    seconds = count * SECONDS_PER_DATE * (2 if st.session_state["bt_use_mu"] else 1)
    return MSG_BT_ESTIMATE.format(n=count, seconds=_decimal(seconds))


def effective_settings(settings) -> CommissionSettings:
    """Comisiones de Ajustes, o ninguna si la casilla está desmarcada (IP-5)."""
    if st.session_state["bt_fees"]:
        return settings
    return CommissionSettings(per_contract=0.0, index_surcharge=0.0, include_close=False)


def result_key(settings, underlying, ticker, fallback_rate, load) -> tuple:
    """Clave del resultado: si cambia algo de esto, el resultado viejo no vale."""
    params = tuple(st.session_state[field] for field in BT_DEFAULTS)
    fees = None
    if st.session_state["bt_fees"]:
        fees = (settings.per_contract, settings.index_surcharge, settings.include_close)
    history = load.history
    # Huella del histórico: primera y última fecha y número de filas.
    history_print = (history.dates[0], history.dates[-1], len(history.dates))
    rates = load.rates
    rates_print = None if rates is None else (rates.dates[0], rates.dates[-1], len(rates.dates))
    # La tasa de la barra lateral solo importa si no hay histórico de ^IRX.
    rate = fallback_rate if rates is None else None
    return (ticker, underlying, params, fees, rate, history_print, rates_print)


def compute_backtest(load, settings, underlying, fallback_rate):
    """Llama al motor con el histórico cargado y los controles de la pestaña."""
    history = load.history
    rates = load.rates
    first = min(_first_index(history), len(history.dates) - 1)
    return run_backtest(
        dates=history.dates,
        close=history.close,
        adj_close=history.adj_close,
        div_dates=[day for day, _amount in history.dividends],
        div_amounts=[amount for _day, amount in history.dividends],
        rate_dates=None if rates is None else rates.dates,
        rate_values=None if rates is None else rates.close,
        template=TEMPLATES_BY_KEY[st.session_state["bt_template"]],
        underlying=underlying,
        horizon_days=int(st.session_state["bt_horizon"]),
        vol_window=int(st.session_state["bt_window"]),
        step=int(st.session_state["bt_step"]),
        settings=effective_settings(settings),
        fallback_rate=fallback_rate,
        first_date=history.dates[first],
        with_mu=bool(st.session_state["bt_use_mu"]),
    )


def run_clicked(now, settings, underlying, ticker, fallback_rate) -> None:
    """Pulsado "Calcular": comprueba histórico y cobertura (IP-11) y calcula."""
    loaded = current_history(ticker)
    if loaded is None:
        st.warning(MSG_BT_NEED_HISTORY)
        return
    load = loaded["load"]
    years = int(st.session_state["bt_years"])
    need_start = start_for_years(now, years)
    if not covers(load.history.dates[0], load.requested_start, need_start):
        st.warning(MSG_BT_NOT_COVERED.format(years=years))
        return
    with st.spinner("Calculando el backtest…"):
        result = compute_backtest(load, settings, underlying, fallback_rate)
    key = result_key(settings, underlying, ticker, fallback_rate, load)
    st.session_state["bt_result"] = {"key": key, "result": result}


# ---------------------------------------------------------------------------
# Resultado: gráficos, tabla, métricas y avisos
# ---------------------------------------------------------------------------


def _fmt(value, digits: int = 3) -> str:
    """Número con coma decimal, o "—" si no hay dato (nunca NaN)."""
    if value is None or not np.isfinite(value):
        return "—"
    return _decimal(value, digits)


def _pct(value) -> str:
    """Fracción como porcentaje con 1 decimal, o "—"."""
    if value is None or not np.isfinite(value):
        return "—"
    return f"{_decimal(value * 100)} %"


def _points_trace(rows, name: str, color: str) -> go.Scatter | None:
    """Puntos (PoP media, ganó) con barras de error de Wilson; huecos si hay pocos casos."""
    shown = [row for row in rows if not row.empty]
    if not shown:
        return None
    return go.Scatter(
        x=[row.mean_pop for row in shown],
        y=[row.observed for row in shown],
        mode="markers",
        name=name,
        marker=dict(
            size=11,
            color=[COLOR_FEW if row.few else color for row in shown],
            symbol=["circle-open" if row.few else "circle" for row in shown],
            line=dict(width=2, color=[COLOR_FEW if row.few else color for row in shown]),
        ),
        error_y=dict(
            type="data",
            symmetric=False,
            array=[row.ci_high - row.observed for row in shown],
            arrayminus=[row.observed - row.ci_low for row in shown],
            thickness=1.5,
        ),
        customdata=[[row.n] for row in shown],
        hovertemplate="PoP media %{x:.1%}<br>Ganó %{y:.1%}<br>Casos %{customdata[0]}<extra></extra>",
    )


def build_reliability_figure(rows, rows_mu=None) -> go.Figure:
    """Gráfico de fiabilidad: diagonal y = x (calibración perfecta) y los tramos."""
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            name="Calibración perfecta",
            line=dict(color=COLOR_DIAGONAL, dash="dash"),
            hoverinfo="skip",
        )
    )
    for trace in (
        _points_trace(rows, "PoP neutral al riesgo", COLOR_POINTS),
        _points_trace(rows_mu, "PoP con μ histórico", COLOR_MU) if rows_mu is not None else None,
    ):
        if trace is not None:
            figure.add_trace(trace)
    figure.update_layout(
        title="¿Cuando la app dice X %, gana X %?",
        xaxis=dict(title="PoP que dio la app", range=[0, 1], tickformat=".0%"),
        yaxis=dict(title="Frecuencia con la que ganó", range=[0, 1], tickformat=".0%"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=10, r=10, t=60, b=10),
    )
    return figure


def build_tails_figure(z) -> go.Figure:
    """Histograma de z (en densidad) con la curva normal estándar encima."""
    z = np.asarray(z, dtype=float)
    z = z[np.isfinite(z)]
    limit = max(4.0, float(np.max(np.abs(z))) if z.size else 4.0)
    grid = np.linspace(-limit, limit, 201)
    figure = go.Figure()
    figure.add_trace(
        go.Histogram(
            x=z,
            histnorm="probability density",
            name="Movimientos reales (z)",
            marker_color=COLOR_POINTS,
            opacity=0.6,
        )
    )
    figure.add_trace(
        go.Scatter(x=grid, y=norm.pdf(grid), mode="lines", name="Normal estándar", line=dict(color=COLOR_MU))
    )
    figure.update_layout(
        title="Colas: movimientos estandarizados frente a la normal",
        xaxis_title="z (movimiento hasta el vencimiento, en desviaciones típicas)",
        yaxis_title="Densidad",
        bargap=0.05,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=10, r=10, t=60, b=10),
    )
    return figure


def calibration_table(rows) -> list[dict]:
    """Filas de la tabla por tramo (todo texto: nunca NaN en pantalla)."""
    table = []
    for row in rows:
        if row.empty:
            note = "sin casos"
        elif row.few:
            note = "pocos casos"
        else:
            note = ""
        interval = "—"
        if row.ci_low is not None and row.ci_high is not None:
            interval = f"{_decimal(row.ci_low * 100)}–{_decimal(row.ci_high * 100)} %"
        table.append(
            {
                "Tramo de PoP": f"{row.lo * 100:.0f}–{row.hi * 100:.0f} %",
                "Casos": str(row.n),
                "N ef.": _decimal(row.n_eff),
                "PoP media": _pct(row.mean_pop),
                "Ganó": _pct(row.observed),
                "IC 95 %": interval,
                "Nota": note,
            }
        )
    return table


def quantile_table(tail) -> list[dict]:
    """Cuantiles de z frente a los de la normal."""
    return [
        {
            "Nivel": f"{_decimal(level * 100, 0)} %",
            "z real": _fmt(empirical, 2),
            "Normal": _fmt(normal, 2),
        }
        for level, (empirical, normal) in tail.quantiles.items()
    ]


def render_result_area(settings, underlying, ticker, fallback_rate) -> None:
    """El resultado guardado si sigue valiendo; si no, el aviso de pulsar Calcular."""
    stored = st.session_state.get("bt_result")
    loaded = current_history(ticker)
    if stored is None or loaded is None:
        return
    key = result_key(settings, underlying, ticker, fallback_rate, loaded["load"])
    if stored["key"] != key:
        st.info(MSG_BT_PARAMS_CHANGED)
        return
    render_result(stored["result"])


def render_result(result) -> None:
    """Métricas, gráfico de fiabilidad, tabla, colas y avisos fijos."""
    for message in result.warnings:
        if message == MSG_NO_DATES:
            st.warning(message)
        else:
            st.caption(message)
    skipped = result.skipped
    st.caption(
        f"Fechas saltadas: sin ventana completa {skipped['no_window']}, "
        f"sin vencimiento en los datos {skipped['no_expiry']}, "
        f"mercado no válido {skipped['invalid_market']}, sin tasa {skipped['no_rate']}."
    )
    if result.n == 0:
        return

    horizon = int(st.session_state["bt_horizon"])
    n_eff = effective_n(result.n, result.years_analyzed, horizon)
    deff = n_eff / result.n if result.n else 1.0
    rows = calibration_bins(result.pop, result.win, deff=deff)
    rows_mu = None if result.pop_mu is None else calibration_bins(result.pop_mu, result.win, deff=deff)

    st.subheader("🎯 Calibración de la PoP", divider=True)
    col_brier, col_n, col_neff = st.columns(3)
    col_brier.metric("Brier", _fmt(brier_score(result.pop, result.win)))
    col_n.metric("Casos (N)", str(result.n))
    col_neff.metric("N efectivo", _decimal(n_eff, 0))
    st.caption(MSG_BT_OVERLAP)
    st.caption(
        f"Brier de referencia (decir siempre la tasa media de acierto, "
        f"{_pct(float(np.mean(result.win)))}): {_fmt(climatological_brier(result.win))}; "
        f"habilidad {_fmt(brier_skill(result.pop, result.win), 2)} (> 0 = mejor que la referencia). "
        f"Mayor desviación entre tramos con casos suficientes: {_pct(max_deviation(rows))}."
    )
    if result.pop_mu is not None:
        st.caption(
            f"Con μ histórico: Brier {_fmt(brier_score(result.pop_mu, result.win))}, "
            f"mayor desviación {_pct(max_deviation(rows_mu))}."
        )
    st.plotly_chart(build_reliability_figure(rows, rows_mu), width="stretch")
    st.caption(
        "Cada punto es un tramo de 10 % de PoP; la barra es el intervalo de confianza del 95 % "
        "(ensanchado por el solapamiento). Puntos grises y huecos: menos de 10 casos."
    )
    st.dataframe(calibration_table(rows), hide_index=True, width="stretch")

    render_tails(result)

    st.subheader("ℹ️ Qué mide y qué no", divider=True)
    for message in (MSG_BT_WHAT, MSG_BT_REALIZED_VOL, MSG_BT_AMERICAN, MSG_BT_Q, MSG_NOT_ADVICE):
        st.caption(message)


def render_tails(result) -> None:
    """Diagnóstico de colas: histograma, estadísticos y cuantiles."""
    tail = tail_diagnostics(result.z)
    st.subheader("📉 Diagnóstico de colas", divider=True)
    st.plotly_chart(build_tails_figure(result.z), width="stretch")
    st.caption(
        f"z: media {_fmt(tail.mean, 2)}, desviación {_fmt(tail.std, 2)}, "
        f"asimetría {_fmt(tail.skew, 2)}, curtosis en exceso {_fmt(tail.excess_kurtosis, 2)} "
        f"(normal: 0, 1, 0 y 0). |z| > 2: {_pct(tail.frac_gt2)} (normal {_pct(EXPECTED_GT2)}); "
        f"z < −2: {_pct(tail.frac_lt_m2)} (normal {_pct(EXPECTED_LT_M2)})."
    )
    st.dataframe(quantile_table(tail), hide_index=True)
    st.caption(MSG_BT_TAILS)
