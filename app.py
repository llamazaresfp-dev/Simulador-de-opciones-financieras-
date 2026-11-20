"""Laboratorio de Opciones: interfaz web con Streamlit.

Cómo funciona Streamlit (resumen para leer este archivo):

- Cada vez que el usuario toca algo (un número, un botón, una pestaña),
  Streamlit vuelve a ejecutar ESTE archivo entero de arriba abajo.
  A eso se le llama "rerun".
- Las variables normales se pierden entre reruns. Lo que debe recordarse
  se guarda en `st.session_state`, un diccionario que sobrevive a los reruns.
- Un "callback" (on_change / on_click) es una función que Streamlit llama
  justo ANTES del rerun, cuando el usuario cambia un widget. La usamos
  para copiar el valor del widget a nuestras propias entradas de
  session_state (así el dato no depende de que el widget se dibuje).

Esta interfaz NO hace cálculos financieros: recoge datos y dibuja.
Todo el cálculo lo hace el motor (`opciones`).

Arranque: .venv/bin/streamlit run app.py
"""

import plotly.graph_objects as go
import streamlit as st

from opciones import (
    TEMPLATES,
    CommissionSettings,
    Leg,
    Market,
    SimulationSettings,
    analyze,
    build_legs,
    default_premium,
    implied_vol,
    market_warnings,
    scenario_warnings,
    simulate_scenario,
    validate_legs,
    validate_market,
    uses_binomial,
    validate_simulation,
)
from opciones.models import PRICING_BINOMIAL, PRICING_BLACK_SCHOLES, PRICING_MODELS
from opciones.validation import MSG_NOT_ADVICE

TAB_NAMES = ["Catálogo", "Constructor", "Ajustes"]

UNDERLYINGS = ["Acción", "ETF", "Índice"]
KIND_LABELS = {"call": "Call", "put": "Put", "stock": "Acción"}
SIDE_LABELS = {1: "Compra (long)", -1: "Venta (short)"}
GREEK_LABELS = {
    "delta": "Delta",
    "gamma": "Gamma",
    "theta": "Theta (por día)",
    "vega": "Vega (por 1 punto de volatilidad)",
    "rho": "Rho (por 1 punto de tipo de interés)",
}

# Colores del gráfico: azul = al vencimiento, naranja = hoy.
COLOR_EXPIRY = "#2a78d6"
COLOR_TODAY = "#eb6834"
COLOR_NEUTRAL = "#8a8985"
COLOR_BREAKEVEN = "#52514e"

# Valores iniciales de la barra lateral y de Ajustes (en %, como los ve el usuario).
MARKET_DEFAULTS = {
    "underlying": "Acción",
    "spot": 100.0,
    "vol_pct": 20.0,
    "days": 30,
    "rate_pct": 4.0,
    "q_pct": 0.0,
}
SETTINGS_DEFAULTS = CommissionSettings()
# Nombres que ve el usuario para cada modelo de valoración (Etapa B1).
PRICING_LABELS = {
    PRICING_BINOMIAL: "Binomial (americano)",
    PRICING_BLACK_SCHOLES: "Black-Scholes (europeo)",
}
# Valores iniciales de la simulación (100 000 trayectorias, semilla 42, μ vacío).
SIMULATION_DEFAULTS = SimulationSettings()


# ---------------------------------------------------------------------------
# Estado (session_state)
# ---------------------------------------------------------------------------


def init_state() -> None:
    """Crea las entradas de session_state la primera vez que se abre la app.

    `setdefault` solo escribe si la clave aún no existe, así que en los
    reruns siguientes no se pisa lo que el usuario ya cambió.
    """
    for key, value in MARKET_DEFAULTS.items():
        st.session_state.setdefault(key, value)

    # Comisiones: entradas simples (no ligadas a widgets). Los widgets de
    # Ajustes las actualizan con callbacks.
    st.session_state.setdefault("per_contract", SETTINGS_DEFAULTS.per_contract)
    st.session_state.setdefault("index_surcharge", SETTINGS_DEFAULTS.index_surcharge)
    st.session_state.setdefault("include_close", SETTINGS_DEFAULTS.include_close)

    # Simulación (Etapa A): también entradas simples, por la misma razón.
    # Las pestañas de Streamlit son "perezosas": si un widget no se dibuja
    # en un rerun, Streamlit borra su valor. Guardando el dato en una clave
    # propia (sin widget) no se pierde al cambiar de pestaña.
    # mu_pct = None significa "vacío" = escenario neutral al riesgo.
    st.session_state.setdefault("n_sims", SIMULATION_DEFAULTS.n_paths)
    st.session_state.setdefault("seed", SIMULATION_DEFAULTS.seed)
    st.session_state.setdefault("mu_pct", None)

    # Modelo de valoración para Acción/ETF (Etapa B1): entrada simple, como
    # las comisiones. Se crea aquí, ANTES de dibujar la barra lateral, porque
    # market_from_state() la lee para construir el Market.
    st.session_state.setdefault("pricing_model", PRICING_BINOMIAL)

    st.session_state.setdefault("main_tab", "Catálogo")

    # Patas: lista de diccionarios. Cada pata tiene un `id` que nunca se
    # repite (sirve para nombrar sus widgets) y `premium_manual`, que dice
    # si el usuario escribió la prima a mano (entonces no la recalculamos).
    st.session_state.setdefault("next_leg_id", 0)
    if "legs" not in st.session_state:
        st.session_state["legs"] = []
        add_leg()  # empezamos con una call comprada en el dinero


def new_leg_dict(kind: str, side: int, quantity: float, strike, price: float) -> dict:
    """Crea el diccionario de una pata con un id nuevo."""
    leg_id = st.session_state["next_leg_id"]
    st.session_state["next_leg_id"] = leg_id + 1
    return {
        "id": leg_id,
        "kind": kind,
        "side": side,
        "quantity": float(quantity),
        "strike": None if strike is None else float(strike),
        "price": float(price),
        "premium_manual": False,
    }


def find_leg(leg_id: int) -> dict | None:
    """Busca una pata por su id en session_state."""
    for leg in st.session_state["legs"]:
        if leg["id"] == leg_id:
            return leg
    return None


def market_from_state() -> Market:
    """Construye el Market con los valores de la barra lateral.

    La volatilidad, el tipo y el dividendo se escriben en % y el motor
    los quiere como fracción (20 % -> 0.20).
    """
    return Market(
        underlying=st.session_state["underlying"],
        spot=st.session_state["spot"],
        vol=percent_to_fraction(st.session_state["vol_pct"]),
        days=st.session_state["days"],
        rate=percent_to_fraction(st.session_state["rate_pct"]),
        q=percent_to_fraction(st.session_state["q_pct"]),
        pricing_model=st.session_state["pricing_model"],
    )


def percent_to_fraction(value):
    """Convierte un porcentaje en fracción; deja None si el campo está vacío."""
    if value is None:
        return None
    return value / 100


def settings_from_state() -> CommissionSettings:
    """Ajustes de comisiones leídos de las entradas simples de session_state."""
    return CommissionSettings(
        per_contract=st.session_state["per_contract"],
        index_surcharge=st.session_state["index_surcharge"],
        include_close=st.session_state["include_close"],
    )


def sim_settings_from_state() -> SimulationSettings:
    """Ajustes de la simulación leídos de session_state.

    μ se escribe en % y el motor lo quiere como fracción (5 % -> 0.05);
    si el campo está vacío queda None (= neutral al riesgo).
    """
    return SimulationSettings(
        n_paths=st.session_state["n_sims"],
        seed=st.session_state["seed"],
        mu=percent_to_fraction(st.session_state["mu_pct"]),
    )


def leg_from_dict(item: dict) -> Leg:
    """Convierte el diccionario de una pata en un objeto Leg del motor."""
    strike = None if item["kind"] == "stock" else item["strike"]
    return Leg(item["kind"], item["side"], item["quantity"], strike, item["price"])


def legs_from_state() -> list[Leg]:
    """Convierte los diccionarios de patas en objetos Leg del motor."""
    return [leg_from_dict(item) for item in st.session_state["legs"]]


def refresh_auto_prices(market: Market) -> None:
    """Recalcula en cada rerun las primas que NO son manuales.

    - Opción: prima del modelo activo (default_premium del motor: árbol
      binomial en Acción/ETF por defecto, Black-Scholes en Índice o si el
      usuario lo elige en Ajustes).
    - Acción: precio de entrada = spot actual.
    Las primas manuales se respetan aunque cambien los datos globales.
    """
    for leg in st.session_state["legs"]:
        if leg["premium_manual"]:
            continue
        if leg["kind"] == "stock":
            leg["price"] = float(market.spot)
        else:
            leg["price"] = float(default_premium(leg["kind"], market, leg["strike"]))


# ---------------------------------------------------------------------------
# Callbacks (se ejecutan antes del rerun, cuando el usuario toca un widget)
# ---------------------------------------------------------------------------


def add_leg() -> None:
    """Botón "+ añadir pata": una call comprada con strike = spot."""
    spot = st.session_state.get("spot") or MARKET_DEFAULTS["spot"]
    leg = new_leg_dict("call", 1, 1, spot, 0.0)
    st.session_state["legs"].append(leg)


def remove_leg(leg_id: int) -> None:
    """Botón "Quitar" de una fila."""
    st.session_state["legs"] = [leg for leg in st.session_state["legs"] if leg["id"] != leg_id]


def on_leg_field_change(leg_id: int, field: str) -> None:
    """Copia el valor de un widget de la fila a la pata (tipo, dirección...)."""
    leg = find_leg(leg_id)
    if leg is None:
        return
    leg[field] = st.session_state[f"leg_{leg_id}_{field}"]


def on_kind_change(leg_id: int) -> None:
    """Al cambiar el tipo de pata, la prima anterior ya no sirve: vuelve a automática."""
    leg = find_leg(leg_id)
    if leg is None:
        return
    leg["kind"] = st.session_state[f"leg_{leg_id}_kind"]
    leg["premium_manual"] = False
    if leg["kind"] == "stock":
        leg["strike"] = None
    elif leg["strike"] is None:
        leg["strike"] = st.session_state.get("spot") or MARKET_DEFAULTS["spot"]


def on_premium_change(leg_id: int) -> None:
    """El usuario escribió la prima: la marcamos como manual."""
    leg = find_leg(leg_id)
    if leg is None:
        return
    leg["price"] = st.session_state[f"leg_{leg_id}_price"]
    leg["premium_manual"] = True


def reset_premium(leg_id: int) -> None:
    """Botón "↺ binomial" / "↺ BS" / "↺ spot": la prima vuelve a ser automática."""
    leg = find_leg(leg_id)
    if leg is not None:
        leg["premium_manual"] = False


def open_template(template_key: str) -> None:
    """Botón "Abrir en el constructor": carga las patas y cambia de pestaña."""
    template = next(t for t in TEMPLATES if t.key == template_key)
    market = market_from_state()
    legs = []
    for leg in build_legs(template, market):
        legs.append(new_leg_dict(leg.kind, leg.side, leg.quantity, leg.strike, leg.price))
    st.session_state["legs"] = legs
    # Cambiar el valor de la clave de las pestañas selecciona otra pestaña.
    st.session_state["main_tab"] = "Constructor"


def use_iv_as_global(vol_pct: float) -> None:
    """Botón "Usar como volatilidad global": pone la IV en la barra lateral.

    Tiene que ser un callback (on_click). Streamlit lo ejecuta ANTES del
    rerun, cuando el widget "Volatilidad anual (%)" (clave `vol_pct`) aún
    no se ha dibujado. Si cambiáramos `st.session_state["vol_pct"]` después
    de dibujar ese widget, Streamlit lanzaría un error
    (StreamlitWidgetAlreadyInstantiatedError).
    En el rerun, refresh_auto_prices recalcula con la nueva σ las primas
    automáticas y la curva «hoy» (no hace falta lógica nueva).
    """
    st.session_state["vol_pct"] = vol_pct


def copy_setting(field: str) -> None:
    """Copia un widget (Ajustes o μ) a su entrada simple de session_state."""
    st.session_state[field] = st.session_state[f"{field}_input"]


# ---------------------------------------------------------------------------
# Barra lateral (siempre se dibuja, en todas las pestañas)
# ---------------------------------------------------------------------------


def render_sidebar() -> Market:
    """Datos globales del mercado. Devuelve el Market con esos datos."""
    with st.sidebar:
        st.header("Datos del mercado")
        st.caption("Valen para todas las patas (un único vencimiento común).")
        # Cada widget usa `key`: su valor vive en st.session_state[key].
        st.selectbox("Tipo de subyacente", UNDERLYINGS, key="underlying")
        st.number_input("Precio actual (spot)", step=1.0, format="%.2f", key="spot")
        st.number_input("Volatilidad anual (%)", step=1.0, format="%.2f", key="vol_pct")
        st.number_input("Días al vencimiento", step=1, key="days")
        st.number_input("Tipo de interés libre de riesgo (%)", step=0.25, format="%.2f", key="rate_pct")
        st.number_input("Dividend yield q (%)", step=0.25, format="%.2f", key="q_pct")

        market = market_from_state()
        for message in validate_market(market):
            st.error(message)
    return market


# ---------------------------------------------------------------------------
# Pestaña Catálogo
# ---------------------------------------------------------------------------


def render_catalog(market_errors: list[str]) -> None:
    """Las 8 estrategias del catálogo, en dos columnas."""
    st.subheader("Catálogo de estrategias")
    st.caption("Elige una estrategia y ábrela en el constructor con los datos actuales del mercado.")
    if market_errors:
        st.warning("Corrige los datos del mercado en la barra lateral para poder abrir una estrategia.")

    columns = st.columns(2)
    for index, template in enumerate(TEMPLATES):
        with columns[index % 2]:
            render_template_card(template, disabled=bool(market_errors))


def render_template_card(template, disabled: bool) -> None:
    """Tarjeta de una plantilla: nombre, idea principal, detalles y botón."""
    with st.container(border=True):
        st.markdown(f"**{template.name}**")
        st.markdown(f"*Visión de mercado:* {template.market_view}")
        st.markdown(template.bet)
        with st.expander("Más detalles"):
            st.markdown(f"**Beneficio máximo:** {template.max_profit}")
            st.markdown(f"**Pérdida máxima:** {template.max_loss}")
            st.markdown(f"**Cuándo usarla:** {template.when_to_use}")
            st.markdown(f"**Riesgos:** {template.risks}")
        st.button(
            "Abrir en el constructor",
            key=f"open_{template.key}",
            on_click=open_template,
            args=(template.key,),
            disabled=disabled,
        )


# ---------------------------------------------------------------------------
# Pestaña Constructor
# ---------------------------------------------------------------------------


def render_builder(market: Market, market_errors: list[str]) -> None:
    """Filas de patas, gráfico, métricas, griegas y avisos."""
    st.subheader("Constructor de estrategias")
    st.caption(active_model_caption(market))
    render_leg_rows(market)
    st.button("+ añadir pata", on_click=add_leg)
    st.divider()

    legs = legs_from_state()
    leg_errors = validate_legs(legs)
    if market_errors:
        st.warning("No se puede calcular: corrige los datos del mercado en la barra lateral.")
    elif leg_errors:
        for message in leg_errors:
            st.error(message)
    else:
        analysis = analyze(market, legs, settings_from_state())
        st.plotly_chart(build_chart(analysis, market), width="stretch")
        render_metrics(analysis)
        render_greeks(analysis.greeks)
        # Escenarios (Etapa A): debajo de lo del MVP, sin moverlo ni cambiarlo.
        render_scenarios(market, legs)

    render_notices(market)


def active_model_caption(market: Market) -> str:
    """Frase que dice con qué modelo se valoran ahora las opciones.

    Va en st.caption (no en st.metric, que recorta los textos largos).
    """
    if uses_binomial(market):
        return (
            "Modelo activo: Binomial (americano), árbol de Cox-Ross-Rubinstein "
            "para primas, curva «hoy», griegas e IV. Se cambia en Ajustes."
        )
    if market.underlying in ("Acción", "ETF"):
        return (
            "Modelo activo: Black-Scholes (europeo), elegido en Ajustes. "
            "Para opciones americanas es una aproximación."
        )
    return (
        "Modelo activo: Black-Scholes (europeo). Las opciones sobre índices son "
        "europeas; el selector de modelo de Ajustes no tiene efecto con Índice."
    )


def render_leg_rows(market: Market) -> None:
    """Una fila de widgets por cada pata guardada en session_state."""
    for number, leg in enumerate(st.session_state["legs"], start=1):
        render_leg_row(number, leg, market)


def sync_widget(leg: dict, field: str) -> str:
    """Pone en el widget el valor guardado en la pata y devuelve su clave.

    Así el widget siempre muestra el valor actual (por ejemplo, la prima
    BS recalculada al cambiar el spot). Se hace ANTES de crear el widget.
    """
    key = f"leg_{leg['id']}_{field}"
    st.session_state[key] = leg[field]
    return key


def reset_label_and_help(is_stock: bool, binomial: bool) -> tuple[str, str]:
    """Texto y ayuda del botón que devuelve la prima a automática."""
    if is_stock:
        return "↺ spot", "Volver al precio automático: el spot actual."
    if binomial:
        return "↺ binomial", "Volver a la prima automática del modelo binomial (americano)."
    return "↺ BS", "Volver a la prima automática de Black-Scholes (europeo)."


def price_origin(leg: dict, binomial: bool) -> str:
    """De dónde sale el precio de la pata: manual, spot, binomial o Black-Scholes."""
    if leg["premium_manual"]:
        return "manual"
    if leg["kind"] == "stock":
        return "spot"
    return "binomial" if binomial else "Black-Scholes"


def render_leg_row(number: int, leg: dict, market: Market) -> None:
    """Fila de una pata: tipo, dirección, strike, cantidad, prima y botones."""
    leg_id = leg["id"]
    is_stock = leg["kind"] == "stock"
    binomial = uses_binomial(market)
    reset_label, reset_help = reset_label_and_help(is_stock, binomial)
    cols = st.columns([1.1, 1.4, 1.1, 1.0, 1.2, 0.9, 0.8], vertical_alignment="bottom")

    cols[0].selectbox(
        f"Pata {number}: tipo",
        list(KIND_LABELS),
        format_func=KIND_LABELS.get,
        key=sync_widget(leg, "kind"),
        on_change=on_kind_change,
        args=(leg_id,),
    )
    cols[1].selectbox(
        "Dirección",
        list(SIDE_LABELS),
        format_func=SIDE_LABELS.get,
        key=sync_widget(leg, "side"),
        on_change=on_leg_field_change,
        args=(leg_id, "side"),
    )
    if is_stock:
        cols[2].text_input("Strike", value="—", disabled=True, key=f"leg_{leg_id}_nostrike")
    else:
        cols[2].number_input(
            "Strike",
            step=0.5,
            format="%.2f",
            key=sync_widget(leg, "strike"),
            on_change=on_leg_field_change,
            args=(leg_id, "strike"),
        )
    cols[3].number_input(
        "Acciones" if is_stock else "Contratos",
        step=1.0,
        format="%g",
        key=sync_widget(leg, "quantity"),
        on_change=on_leg_field_change,
        args=(leg_id, "quantity"),
    )
    cols[4].number_input(
        "Precio de entrada" if is_stock else "Prima (por acción)",
        step=0.05,
        format="%.2f",
        key=sync_widget(leg, "price"),
        on_change=on_premium_change,
        args=(leg_id,),
    )
    cols[5].button(
        reset_label,
        key=f"leg_{leg_id}_reset",
        on_click=reset_premium,
        args=(leg_id,),
        disabled=not leg["premium_manual"],
        help=reset_help,
    )
    cols[6].button("Quitar", key=f"leg_{leg_id}_remove", on_click=remove_leg, args=(leg_id,))
    st.caption(f"Pata {number}: precio {price_origin(leg, binomial)}.")


def build_chart(analysis, market: Market) -> go.Figure:
    """Gráfico de P&L: vencimiento (sólida), hoy (discontinua), cero, spot y breakevens."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=analysis.grid,
            y=analysis.expiry_curve,
            name="Al vencimiento",
            mode="lines",
            line={"color": COLOR_EXPIRY, "width": 2},
            hovertemplate="%{y:.2f} USD",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=analysis.grid,
            y=analysis.today_curve,
            name="Hoy",
            mode="lines",
            line={"color": COLOR_TODAY, "width": 2, "dash": "dash"},
            hovertemplate="%{y:.2f} USD",
        )
    )
    breakevens = analysis.metrics.breakevens
    if breakevens:
        fig.add_trace(
            go.Scatter(
                x=breakevens,
                y=[0] * len(breakevens),
                name="Breakeven",
                mode="markers",
                marker={"color": COLOR_BREAKEVEN, "size": 10, "symbol": "diamond"},
                hovertemplate="Breakeven %{x:.2f}<extra></extra>",
            )
        )
    fig.add_hline(y=0, line={"color": COLOR_NEUTRAL, "width": 1})
    fig.add_vline(
        x=market.spot,
        line={"color": COLOR_NEUTRAL, "width": 1, "dash": "dot"},
        annotation_text=f"Spot {market.spot:.2f}",
        annotation_position="top",
    )
    fig.update_layout(
        xaxis_title="Precio del subyacente",
        yaxis_title="P&L (USD)",
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.12},
        margin={"t": 40, "b": 40},
    )
    return fig


def format_usd(value: float) -> str:
    """Formatea un importe en USD con 2 decimales."""
    return f"{value:.2f} USD"


def render_metrics(analysis) -> None:
    """Beneficio máx., pérdida máx., breakevens y comisiones (al vencimiento)."""
    metrics = analysis.metrics
    best = "ilimitado" if metrics.profit_unlimited else format_usd(metrics.best_pnl)
    worst = "ilimitado" if metrics.loss_unlimited else format_usd(metrics.worst_pnl)
    # Los breakevens van en su propia línea (no en st.metric) porque
    # st.metric recorta el texto largo y no se leería el segundo valor.
    if metrics.breakevens:
        breakevens = " y ".join(f"{value:.2f}" for value in metrics.breakevens)
    else:
        breakevens = "ninguno"

    st.markdown("**Resultados al vencimiento**")
    cols = st.columns(3)
    cols[0].metric("Beneficio máximo", best)
    cols[1].metric("Pérdida máxima", worst)
    cols[2].metric("Comisiones totales", format_usd(analysis.commission_total))
    st.markdown(f"**Breakevens:** {breakevens}")


def render_greeks(greeks: dict) -> None:
    """Tabla de griegas de la posición ("—" si no se pueden calcular)."""
    st.markdown("**Griegas de la posición (hoy, al precio spot)**")
    rows = []
    for name, label in GREEK_LABELS.items():
        value = greeks.get(name)
        rows.append({"Griega": label, "Valor": "—" if value is None else f"{value:.4f}"})
    st.table(rows)


# ---------------------------------------------------------------------------
# Escenarios (Monte Carlo) dentro del Constructor
# ---------------------------------------------------------------------------


def format_pct(fraction: float) -> str:
    """Formatea una fracción como porcentaje con 1 decimal (0.339 -> 33.9 %)."""
    return f"{fraction * 100:.1f} %"


def render_scenarios(market: Market, legs: list[Leg]) -> None:
    """Desplegable con la PoP y la simulación del P&L AL VENCIMIENTO.

    Solo se llama si la estrategia es válida. No hay nada de la curva
    «hoy» aquí: la simulación es solo al vencimiento.
    """
    with st.expander("Escenarios (Monte Carlo)"):
        render_mu_input()
        sim = sim_settings_from_state()
        errors = validate_simulation(market, legs, sim)
        if errors:
            for message in errors:
                st.error(message)
        else:
            result = simulate_scenario(market, legs, settings_from_state(), sim)
            render_scenario_results(result, sim)
        render_implied_vols(market)
        for message in scenario_warnings(market):
            # El aviso "no es asesoría" ya sale en el pie de la página y en los
            # avisos generales justo debajo: aquí lo saltamos para no repetirlo.
            if message != MSG_NOT_ADVICE:
                st.info(message)


def render_mu_input() -> None:
    """Campo de μ (crecimiento esperado del precio, % anual).

    Mismo patrón que Ajustes: el widget (`mu_pct_input`) copia su valor a
    la entrada simple `mu_pct` con un callback. Sin min/max a propósito:
    así un valor fuera de rango llega a validate_simulation, que muestra
    el mensaje en español. Vacío (None) = escenario neutral al riesgo.
    """
    st.number_input(
        "Crecimiento esperado del precio (% anual), comparable a r − q",
        value=st.session_state["mu_pct"],
        step=1.0,
        format="%.2f",
        placeholder="vacío = neutral al riesgo (r − q)",
        help="Déjalo vacío para el escenario neutral al riesgo (crecimiento = r − q).",
        key="mu_pct_input",
        on_change=copy_setting,
        args=("mu_pct",),
    )


def scenario_label(result, sim: SimulationSettings) -> str:
    """Texto que dice qué escenario se simuló (neutral al riesgo o μ del usuario)."""
    growth = format_pct(result.mu_used)
    if sim.mu is None:
        return f"Escenario: neutral al riesgo (crecimiento del precio = r − q = {growth} anual)."
    return f"Escenario: μ del usuario (crecimiento esperado del precio = {growth} anual)."


def render_scenario_results(result, sim: SimulationSettings) -> None:
    """PoP exacta y simulada, valor esperado, percentiles e histograma."""
    st.caption(scenario_label(result, sim))

    st.markdown("**Probabilidad de beneficio al vencimiento (PoP)**")
    cols = st.columns(2)
    cols[0].metric("PoP exacta", format_pct(result.pop_exact))
    cols[1].metric("PoP simulada", format_pct(result.pop_mc))
    # f"{n:,}" pone comas de miles (100,000); las cambiamos por espacios (100 000).
    n_paths = f"{result.n_paths:,}".replace(",", " ")
    st.caption(f"PoP simulada con {n_paths} simulaciones (semilla {sim.seed}).")

    st.markdown("**P&L simulado al vencimiento**")
    # El valor esperado va en su propia fila: en una fila de 4 columnas
    # st.metric recortaba la etiqueta y no se leía «no descontado».
    st.metric("Valor esperado (no descontado)", format_usd(result.mean_pnl))
    st.caption(
        "Valor esperado no descontado: es la media del P&L al vencimiento, "
        "sin descontar. No es un precio justo."
    )
    cols = st.columns(3)
    cols[0].metric("Percentil 5", format_usd(result.p5))
    cols[1].metric("Mediana (p50)", format_usd(result.p50))
    cols[2].metric("Percentil 95", format_usd(result.p95))

    st.plotly_chart(build_histogram(result), width="stretch")
    st.caption(
        "Las barras de los extremos acumulan las colas: incluyen todas las "
        "simulaciones por debajo del percentil 0,5 % (primera barra) y por "
        "encima del 99,5 % (última barra)."
    )


def manual_option_legs() -> list[tuple[int, dict]]:
    """Patas de opción con prima escrita a mano, con su número de fila.

    Solo estas tienen IV: las primas automáticas salen de la σ global,
    así que su IV sería esa misma σ. Las acciones no tienen IV.
    """
    found = []
    for number, item in enumerate(st.session_state["legs"], start=1):
        if item["premium_manual"] and item["kind"] != "stock":
            found.append((number, item))
    return found


def render_implied_vols(market: Market) -> None:
    """Volatilidad implícita de cada pata con prima manual (y su botón).

    Si no hay patas de opción con prima manual, no se dibuja nada.
    """
    manual_legs = manual_option_legs()
    if not manual_legs:
        return

    st.markdown("**Volatilidad implícita (IV) de las primas manuales**")
    st.warning(
        "Atención: «Usar como volatilidad global» cambia la volatilidad de la "
        "barra lateral, y con ella TODAS las primas automáticas y la curva «hoy». "
        "Una sola σ global no encaja con todos los strikes: cada prima de "
        "mercado puede tener su propia IV."
    )
    for number, item in manual_legs:
        render_leg_iv(number, item, market)


def render_leg_iv(number: int, item: dict, market: Market) -> None:
    """IV de una pata: el valor en % con su botón, o el mensaje si no existe."""
    name = f"Pata {number} ({KIND_LABELS[item['kind']]}, strike {item['strike']:.2f})"
    result = implied_vol(leg_from_dict(item), market)
    if result.vol is None:
        st.caption(f"{name}: {result.message}")
        return
    vol_pct = round(result.vol * 100, 2)
    st.caption(f"{name}: volatilidad implícita {vol_pct:.2f} %")
    st.button(
        "Usar como volatilidad global",
        key=f"use_iv_{item['id']}",
        on_click=use_iv_as_global,
        args=(vol_pct,),
    )


def build_histogram(result) -> go.Figure:
    """Histograma del P&L simulado (barras ya contadas por el motor) y línea en cero."""
    edges = result.hist_edges
    # Solo para dibujar: cada barra va centrada entre sus dos bordes.
    centers = (edges[:-1] + edges[1:]) / 2
    widths = edges[1:] - edges[:-1]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=centers,
            y=result.hist_counts,
            width=widths,
            name="Simulaciones",
            marker={"color": COLOR_EXPIRY},
            hovertemplate="P&L %{x:.2f} USD: %{y} simulaciones<extra></extra>",
        )
    )
    fig.add_vline(x=0, line={"color": COLOR_BREAKEVEN, "width": 1})
    fig.update_layout(
        xaxis_title="P&L al vencimiento (USD)",
        yaxis_title="Número de simulaciones",
        bargap=0,
        showlegend=False,
        margin={"t": 20, "b": 40},
    )
    return fig


def render_notices(market: Market) -> None:
    """Avisos informativos del motor (asesoría, americanas/europeas, días = 0, cierre)."""
    for message in market_warnings(market):
        st.info(message)


# ---------------------------------------------------------------------------
# Pestaña Ajustes
# ---------------------------------------------------------------------------


def render_settings() -> None:
    """Modelo, comisiones y simulación. Los widgets copian su valor a session_state con callbacks."""
    render_pricing_settings()
    st.subheader("Ajustes de comisiones")
    st.number_input(
        "Comisión por contrato de opción (USD)",
        min_value=0.0,
        step=0.05,
        format="%.2f",
        value=st.session_state["per_contract"],
        key="per_contract_input",
        on_change=copy_setting,
        args=("per_contract",),
    )
    st.number_input(
        "Recargo por contrato si el subyacente es Índice (USD)",
        min_value=0.0,
        step=0.05,
        format="%.2f",
        value=st.session_state["index_surcharge"],
        key="index_surcharge_input",
        on_change=copy_setting,
        args=("index_surcharge",),
    )
    st.checkbox(
        "Incluir comisión de cierre",
        value=st.session_state["include_close"],
        key="include_close_input",
        on_change=copy_setting,
        args=("include_close",),
    )
    st.caption(
        "Las acciones no pagan comisión. Al vencimiento, la comisión de cierre solo se cobra "
        "si la opción vence con valor; en la curva «hoy» se cobra en todas las opciones."
    )
    render_simulation_settings()


def render_pricing_settings() -> None:
    """Selector del modelo de valoración (mismo patrón de callbacks que las comisiones).

    El widget (`pricing_model_input`) copia su valor a la entrada simple
    `pricing_model`; el valor inicial del widget sale de esa entrada, así
    no se pierde al cambiar de pestaña.
    """
    st.subheader("Modelo de valoración")
    st.radio(
        "Modelo de valoración para Acción/ETF",
        list(PRICING_MODELS),
        index=list(PRICING_MODELS).index(st.session_state["pricing_model"]),
        format_func=PRICING_LABELS.get,
        key="pricing_model_input",
        on_change=copy_setting,
        args=("pricing_model",),
        help=(
            "Binomial: modelo americano (permite ejercer antes del vencimiento). "
            "Black-Scholes: modelo europeo, útil para comparar."
        ),
    )
    st.caption(
        "Las opciones sobre acciones y ETF son americanas: el modelo binomial "
        "(por defecto) tiene en cuenta el ejercicio anticipado en las primas "
        "automáticas, la curva «hoy», las griegas y la IV. Elige Black-Scholes "
        "para comparar. Las primas escritas a mano no cambian."
    )
    st.caption(
        "Con Índice este ajuste no tiene efecto: sus opciones son europeas y "
        "siempre se valoran con Black-Scholes."
    )


def render_simulation_settings() -> None:
    """Número de simulaciones y semilla (mismo patrón de callbacks que las comisiones).

    Sin min/max a propósito: así un valor no válido llega a
    validate_simulation y el Constructor muestra el mensaje en español.
    `step=1` con valores enteros hace que Streamlit devuelva enteros.
    """
    st.subheader("Simulación")
    st.number_input(
        "Número de simulaciones (Monte Carlo)",
        step=1,
        value=st.session_state["n_sims"],
        key="n_sims_input",
        on_change=copy_setting,
        args=("n_sims",),
    )
    st.number_input(
        "Semilla del generador aleatorio",
        step=1,
        value=st.session_state["seed"],
        key="seed_input",
        on_change=copy_setting,
        args=("seed",),
    )
    st.caption(
        "Entre 1 000 y 1 000 000 simulaciones. Con la misma semilla y los mismos "
        "datos, el resultado simulado es siempre el mismo; cambiar la semilla "
        "cambia solo la parte simulada (no la PoP exacta)."
    )


# ---------------------------------------------------------------------------
# Programa principal: se ejecuta entero en cada rerun
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Laboratorio de Opciones", layout="wide")
    init_state()

    st.title("Laboratorio de Opciones")
    st.caption("Herramienta de estudio, no asesoría de inversión.")

    market = render_sidebar()
    market_errors = validate_market(market)
    if not market_errors:
        refresh_auto_prices(market)

    # Con key + on_change="rerun", la pestaña activa vive en
    # st.session_state["main_tab"] y un callback puede cambiarla.
    catalog_tab, builder_tab, settings_tab = st.tabs(TAB_NAMES, key="main_tab", on_change="rerun")
    with catalog_tab:
        render_catalog(market_errors)
    with builder_tab:
        render_builder(market, market_errors)
    with settings_tab:
        render_settings()


main()
