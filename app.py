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

from datetime import date, datetime

import plotly.graph_objects as go
import streamlit as st

from datos.cache import MARKET_TZ, market_today
from datos.errors import MSG_EMPTY
from datos.service import MSG_Q_INDEX, MSG_Q_MISSING, age_text, load_or_cache
from datos.tickers import MANUAL_ENTRY, resolve_ticker, ticker_options

from estrategias import store

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
from ui_backtest import clear_backtest_state, init_backtest_state, render_backtest
from ui_comparar import init_compare_state, render_compare
from ui_estrategias import (
    init_strategies_state,
    render_my_strategies,
    render_open_notices,
    render_save_section,
)

# ============================================================================
# MEJORAS UI - Paleta conservadora con sombras, padding y tipografía
# ============================================================================

# Colores base (sistema de diseño consistente)
COLOR_SYSTEM = {
    "primary": "#3b82f6",       # Azul principal para acciones principales
    "primary_hover": "#2563eb", # Azul más oscuro para hover
    "secondary": "#64748b",     # Gris azulado para elementos secundarios
    "success": "#10b981",       # Verde éxito
    "warning": "#f59e0b",       # Amarillo advertencia
    "danger": "#ef4444",        # Rojo error/negativo
    "info": "#3b82f6",          # Azul información
    # Fondo de las secciones: gris azulado semitransparente, para que el
    # texto se lea tanto con el tema claro como con el oscuro de Streamlit
    # (un fondo blanco fijo dejaría el texto claro del tema oscuro ilegible).
    "background_light": "rgba(148, 163, 184, 0.12)",
    "border_subtle": "rgba(148, 163, 184, 0.35)",  # Borde sutil (sirve en ambos temas)
    "shadow_light": "0 1px 3px rgba(0,0,0,0.06)",  # Sombra muy suave para cards
    "shadow_medium": "0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06)",  # Sombra media
}

# Colores por tipo de estrategia para badges
COLOR_STRATEGY = {
    "alcista": "#10b981",  # Verde para estrategias alcistas 📈
    "bajista": "#f59e0b",  # Amarillo/ámbar para bajistas 📉
    "neutral": "#6366f1",  # Índigo para neutrales ↔️
    "volatil": "#ec4899",  # Rosa para volátiles 🎢
}

# Iconos para widgets y acciones - usando emojis Unicode (compatible con todos los navegadores)
ICON_WIDGETS = {
    "add": "➕",
    "remove": "➖",
    "refresh": "🔄",
    "lock": "🔒",
    "unlock": "🔓",
    "check": "✓",
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "❌",
}

# Iconos de estrategias - usando emojis Unicode (compatible con todos los navegadores)
ICON_STRATEGY = {
    "alcista": "📈",  # Subida alcista
    "bajista": "📉",  # Bajada bajista
    "neutral": "↔️",  # Movimiento lateral
    "volatil": "🎢",  # Volatilidad alta
}


def strategy_type(market_view: str) -> str:
    """Tipo de estrategia ("alcista", "bajista", "neutral" o "volatil") según su visión de mercado."""
    view = market_view.lower()
    if any(word in view for word in ["alcista", "suba", "crezca"]):
        return "alcista"
    if any(word in view for word in ["bajista", "baja", "caída"]):
        return "bajista"
    if any(word in view for word in ["neutral", "lateral", "rango"]):
        return "neutral"
    return "volatil"  # volátil, gran movimiento, etc.


def get_strategy_color(market_view: str) -> str:
    """Devuelve el color del badge según la visión de mercado."""
    return COLOR_STRATEGY[strategy_type(market_view)]


def get_strategy_icon(market_view: str) -> str:
    """Devuelve el icono emoji según la visión de mercado."""
    return ICON_STRATEGY[strategy_type(market_view)]


def create_strategy_badge(market_view: str) -> str:
    """Crea HTML para un badge de estrategia con color, icono emoji y estilo mejorado."""
    color = get_strategy_color(market_view)
    icon = get_strategy_icon(market_view)
    # Badge con emoji Unicode y texto completo. El color + "15"/"26" añade
    # transparencia (hex de 8 dígitos), así el fondo se ve bien en ambos temas.
    return f"""<span style="background-color: {color}15;
         border: 1px solid {color}26;
         padding: 4px 12px;
         border-radius: 9999px;
         font-size: 0.8rem;
         margin-top: 0.2rem;
         display: inline-block;
         width: fit-content;">
        {icon} {market_view}
    </span>"""


# Etiquetas de las pestañas (con icono). El valor de st.session_state["main_tab"]
# es la etiqueta completa de la pestaña activa.
TAB_NAMES = [
    "📊 Catálogo",
    "🛠️ Constructor",
    "⚖️ Comparar",
    "💾 Mis estrategias",
    "⚙️ Ajustes",
    "📈 Backtest",
]

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

    st.session_state.setdefault("main_tab", TAB_NAMES[0])

    # Pestaña Backtest (Etapa C2): sus controles, histórico y resultado.
    init_backtest_state()

    # Estrategias guardadas y comparación (Etapa D). Solo para pruebas:
    # "strategies_dir" se puede poner en session_state antes de arrancar;
    # si no está, se usa la carpeta .estrategias/ (ver estrategias.store).
    init_strategies_state()
    init_compare_state()

    # Datos de mercado en directo (Etapa C1). Con "Entrada manual" nada de
    # esto se usa y la app funciona exactamente como antes.
    # - ticker_choice / expiry_choice: claves de los selectbox de la barra
    #   lateral (Ticker y Vencimiento).
    # - snapshot: los datos cargados (MarketSnapshot) o None.
    # - load_notice: avisos de la última carga (textos en español).
    # Solo para pruebas: "data_provider", "cache_dir" y "clock" se pueden
    # poner en session_state antes de arrancar; si no están, se usan Yahoo,
    # la carpeta .cache_datos/ y la hora real de Nueva York.
    st.session_state.setdefault("ticker_choice", MANUAL_ENTRY)
    st.session_state.setdefault("expiry_choice", None)
    st.session_state.setdefault("snapshot", None)
    st.session_state.setdefault("load_notice", [])

    # Patas: lista de diccionarios. Cada pata tiene un `id` que nunca se
    # repite (sirve para nombrar sus widgets) y `premium_manual`, que dice
    # si el usuario escribió la prima a mano (entonces no la recalculamos).
    st.session_state.setdefault("next_leg_id", 0)
    if "legs" not in st.session_state:
        st.session_state["legs"] = []
        add_leg()  # empezamos con una call comprada en el dinero


def new_leg_dict(
    kind: str,
    side: int,
    quantity: float,
    strike,
    price: float,
    premium_manual: bool = False,
    premium_source=None,
    bid=None,
    ask=None,
    iv_yahoo=None,
    expiry=None,
) -> dict:
    """Crea el diccionario de una pata con un id nuevo.

    Los campos opcionales solo los usan las patas "de mercado" (Etapa C1),
    añadidas desde la cadena real:
    - premium_source: "mercado" (prima = mid), "manual" (el usuario la
      editó después) o None (pata normal).
    - bid, ask: cotización de la que sale el mid.
    - iv_yahoo: IV publicada por Yahoo (fracción), SOLO como referencia.
    - expiry: vencimiento ISO de la cotización.
    """
    leg_id = st.session_state["next_leg_id"]
    st.session_state["next_leg_id"] = leg_id + 1
    return {
        "id": leg_id,
        "kind": kind,
        "side": side,
        "quantity": float(quantity),
        "strike": None if strike is None else float(strike),
        "price": float(price),
        "premium_manual": premium_manual,
        "premium_source": premium_source,
        "bid": bid,
        "ask": ask,
        "iv_yahoo": iv_yahoo,
        "expiry": expiry,
    }


def is_market_leg(leg: dict) -> bool:
    """True si la prima de la pata es el mid de una cotización real."""
    return leg.get("premium_source") == "mercado"


def clear_market_fields(leg: dict) -> None:
    """Olvida la cotización de la que salía la pata (ya no es de mercado)."""
    leg["premium_source"] = None
    leg["bid"] = None
    leg["ask"] = None
    leg["iv_yahoo"] = None
    leg["expiry"] = None


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
    Las patas de mercado (prima = mid real) tampoco se tocan nunca.
    """
    for leg in st.session_state["legs"]:
        if leg["premium_manual"] or is_market_leg(leg):
            continue
        if leg["kind"] == "stock":
            leg["price"] = float(market.spot)
        else:
            leg["price"] = float(default_premium(leg["kind"], market, leg["strike"]))


# ---------------------------------------------------------------------------
# Callbacks (se ejecutan antes del rerun, cuando el usuario toca un widget)
# ---------------------------------------------------------------------------


def add_leg() -> None:
    """Botón "➕ Añadir pata": una call comprada con strike = spot."""
    spot = st.session_state.get("spot") or MARKET_DEFAULTS["spot"]
    leg = new_leg_dict("call", 1, 1, spot, 0.0)
    st.session_state["legs"].append(leg)


def remove_leg(leg_id: int) -> None:
    """Botón "➖ Quitar" de una fila."""
    st.session_state["legs"] = [leg for leg in st.session_state["legs"] if leg["id"] != leg_id]
    # Los avisos de "Abrir" van por número de pata: ya no corresponden.
    st.session_state["open_notices"] = []


def on_leg_field_change(leg_id: int, field: str) -> None:
    """Copia el valor de un widget de la fila a la pata (tipo, dirección...)."""
    leg = find_leg(leg_id)
    if leg is None:
        return
    leg[field] = st.session_state[f"leg_{leg_id}_{field}"]
    if field == "strike" and is_market_leg(leg):
        # Otro strike = otro contrato: la prima ya no es el mid de su
        # cotización. Se conserva como prima manual.
        clear_market_fields(leg)
        leg["premium_source"] = "manual"


def on_kind_change(leg_id: int) -> None:
    """Al cambiar el tipo de pata, la prima anterior ya no sirve: vuelve a automática."""
    leg = find_leg(leg_id)
    if leg is None:
        return
    leg["kind"] = st.session_state[f"leg_{leg_id}_kind"]
    leg["premium_manual"] = False
    clear_market_fields(leg)
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
    if leg.get("premium_source") is not None:
        # Era una pata de mercado: ahora la prima la ha puesto el usuario.
        leg["premium_source"] = "manual"


def reset_premium(leg_id: int) -> None:
    """Botón "🔄 binomial" / "🔄 BS" / "🔄 spot": la prima vuelve a ser automática."""
    leg = find_leg(leg_id)
    if leg is not None:
        leg["premium_manual"] = False
        clear_market_fields(leg)


def open_template(template_key: str) -> None:
    """Botón "Abrir en el constructor": carga las patas y cambia de pestaña."""
    template = next(t for t in TEMPLATES if t.key == template_key)
    market = market_from_state()
    legs = []
    for leg in build_legs(template, market):
        legs.append(new_leg_dict(leg.kind, leg.side, leg.quantity, leg.strike, leg.price))
    st.session_state["legs"] = legs
    # Cambiar el valor de la clave de las pestañas selecciona otra pestaña.
    st.session_state["main_tab"] = TAB_NAMES[1]


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
# Datos de mercado en directo (Etapa C1): callbacks y ayudantes
# ---------------------------------------------------------------------------

# Mensaje cuando un ticker curado no devuelve datos: como todos los de la
# lista tienen opciones, lo más probable es un fallo de la fuente o de la red.
MSG_CURATED_EMPTY = (
    "Yahoo no devolvió datos para {label}: puede ser un problema temporal "
    "de la fuente o de la conexión; prueba más tarde."
)
# Avisos de q que se muestran como nota (caption), no como advertencia.
Q_NOTES = (MSG_Q_MISSING, MSG_Q_INDEX)


def clear_loaded_data() -> None:
    """Olvida los datos cargados (snapshot, vencimiento elegido y avisos)."""
    st.session_state["snapshot"] = None
    st.session_state["expiry_choice"] = None
    st.session_state["load_notice"] = []


def on_underlying_change() -> None:
    """Cambia el tipo de subyacente: el ticker vuelve a "Entrada manual"."""
    st.session_state["ticker_choice"] = MANUAL_ENTRY
    clear_loaded_data()
    clear_backtest_state()


def on_ticker_change() -> None:
    """Cambia el ticker (p. ej. SPY -> QQQ): los datos del anterior ya no valen.

    Así nunca se muestra la cadena de SPY con la etiqueta QQQ: hay que
    volver a pulsar "Cargar datos". Lo mismo con el histórico del Backtest.
    """
    clear_loaded_data()
    clear_backtest_state()
    st.session_state["open_notices"] = []


def strategies_dir_from_state() -> str | None:
    """Carpeta de estrategias de las pruebas, o None (= la carpeta por defecto).

    None hace que estrategias.store lea su carpeta por defecto en cada
    llamada (así los tests pueden redirigirla).
    """
    return st.session_state.get("strategies_dir")


# ---------------------------------------------------------------------------
# Abrir una estrategia guardada (Etapa D)
# ---------------------------------------------------------------------------

MSG_OPEN_FAILED = "No se pudo abrir «{name}»."
MSG_OPEN_STALE_QUOTE = "Pata {number}: cotización guardada el {date}, puede estar desfasada."


def fraction_to_percent(value: float) -> float:
    """Fracción -> % para la barra lateral, sin ruido de coma flotante (0.2 -> 20.0)."""
    return round(value * 100, 10)


def loaded_leg_spec(saved) -> dict:
    """Pata guardada -> argumentos de new_leg_dict.

    - Prima manual o de mercado: queda como manual con la prima guardada
      (la pata de mercado pierde bid/ask/vencimiento: ya no es de mercado).
    - Prima automática: premium_manual=False; refresh_auto_prices la
      recalcula con el mercado resultante en el mismo rerun.
    """
    manual = saved.premium_manual or saved.premium_source in ("mercado", "manual")
    return {
        "kind": saved.kind,
        "side": saved.side,
        "quantity": saved.quantity,
        "strike": saved.strike,
        "price": saved.price,
        "premium_manual": bool(manual),
    }


def market_state_updates(strategy) -> dict:
    """Claves de la barra lateral y de Ajustes (simples Y de widget, DD-20)."""
    market = strategy.market
    commissions = strategy.commissions
    return {
        # Las claves de la barra lateral son directamente las de sus widgets.
        "underlying": market.underlying,
        "spot": float(market.spot),
        "vol_pct": fraction_to_percent(market.vol),
        "days": int(market.days),
        "rate_pct": fraction_to_percent(market.rate),
        "q_pct": fraction_to_percent(market.q),
        # Ajustes: entrada simple y widget, para que el widget muestre lo cargado.
        "pricing_model": market.pricing_model,
        "pricing_model_input": market.pricing_model,
        "per_contract": float(commissions.per_contract),
        "per_contract_input": float(commissions.per_contract),
        "index_surcharge": float(commissions.index_surcharge),
        "index_surcharge_input": float(commissions.index_surcharge),
        "include_close": bool(commissions.include_close),
        "include_close_input": bool(commissions.include_close),
    }


def open_saved_strategy(slug: str, with_market: bool) -> None:
    """Botones "Abrir con su mercado" / "Abrir solo las patas" (callback).

    Es un callback (como open_template): se ejecuta ANTES de dibujar los
    widgets, así que puede escribir sus claves. Todo se prepara primero y
    solo se aplica si nada falló: un error deja el estado sin cambios y un
    mensaje en español en la pestaña "Mis estrategias" (DD-22).
    """
    try:
        stored, message = store.read_strategy(slug, strategies_dir_from_state())
        if stored is None:
            st.session_state["sv_message"] = ("error", f"{MSG_OPEN_FAILED.format(name=slug)} {message}")
            return
        strategy = stored.strategy
        specs = [loaded_leg_spec(saved) for saved in strategy.legs]
        saved_day = strategy.saved_at[:10]
        notices = [
            MSG_OPEN_STALE_QUOTE.format(number=number, date=saved_day)
            for number, saved in enumerate(strategy.legs, start=1)
            if saved.premium_source == "mercado"
        ]
        updates = market_state_updates(strategy) if with_market else {}
    except Exception:
        st.session_state["sv_message"] = ("error", MSG_OPEN_FAILED.format(name=slug))
        return

    for key, value in updates.items():
        st.session_state[key] = value
    # Cambiar `underlying` desde un callback no dispara on_underlying_change:
    # se limpian a mano el ticker, los datos cargados y el Backtest.
    st.session_state["ticker_choice"] = MANUAL_ENTRY
    clear_loaded_data()
    clear_backtest_state()
    st.session_state["legs"] = [new_leg_dict(**spec) for spec in specs]
    st.session_state["open_notices"] = notices
    st.session_state["sv_name"] = strategy.name
    st.session_state["sv_name_input"] = strategy.name
    st.session_state["sv_overwrite"] = False
    st.session_state["sv_overwrite_input"] = False
    st.session_state["sv_message"] = None
    st.session_state["main_tab"] = TAB_NAMES[1]


def current_time() -> datetime:
    """Hora actual con zona horaria (Nueva York).

    Las pruebas ponen un reloj fijo en st.session_state["clock"].
    """
    clock = st.session_state.get("clock")
    if clock is not None:
        return clock()
    return datetime.now(MARKET_TZ)


def data_provider():
    """Proveedor de datos: el de las pruebas o, por defecto, Yahoo Finance.

    Yahoo se importa aquí dentro para que la app arranque aunque yfinance
    falle. Devuelve None si no se puede crear el proveedor.
    """
    provider = st.session_state.get("data_provider")
    if provider is not None:
        return provider
    try:
        from datos.yahoo import YahooProvider

        return YahooProvider()
    except Exception:
        return None


def days_until(expiry: str) -> int:
    """Días naturales desde hoy (fecha de mercado) hasta un vencimiento ISO."""
    today = market_today(current_time())
    return (date.fromisoformat(expiry) - today).days


def explain_notice(message: str, label: str) -> str:
    """Cambia el aviso de "respuesta vacía" por uno que sugiere la causa."""
    if message == MSG_EMPTY:
        return MSG_CURATED_EMPTY.format(label=label)
    return message


def fill_market_inputs(snapshot, notices: list[str]) -> None:
    """Escribe spot, r y q del snapshot en los campos de la barra lateral.

    - r: fracción -> % con 2 decimales (0.04122 -> 4.12).
    - q de Yahoo: fracción -> % con 2 decimales.
    - q no disponible (acción/ETF): q = 0 y nota.
    - Índice: q NO se toca (el usuario lo edita) y nota C10.
    Los campos siguen siendo editables.
    """
    st.session_state["spot"] = float(snapshot.spot)
    st.session_state["rate_pct"] = round(snapshot.rate * 100, 2)
    if snapshot.q_source == "indice":
        note = MSG_Q_INDEX
    elif snapshot.q is None:
        st.session_state["q_pct"] = 0.0
        note = MSG_Q_MISSING
    else:
        st.session_state["q_pct"] = round(snapshot.q * 100, 2)
        note = None
    if note is not None and note not in notices:
        notices.append(note)


def select_first_expiry(snapshot) -> None:
    """Elige el primer vencimiento ofrecido y pone sus días (A2)."""
    expiries = sorted(snapshot.chains)
    if not expiries:
        st.session_state["expiry_choice"] = None
        return
    st.session_state["expiry_choice"] = expiries[0]
    st.session_state["days"] = days_until(expiries[0])


def on_load_data() -> None:
    """Botón "Cargar datos": trae spot, r, q y las cadenas líquidas.

    Es un callback: se ejecuta ANTES de dibujar los widgets, así que puede
    escribir `spot`, `rate_pct`, `q_pct` y `days` sin error de Streamlit.
    Si el proveedor falla, se usan los datos guardados (si los hay) y los
    avisos quedan en `load_notice`. Nunca deja escapar una excepción.
    """
    kind = st.session_state["underlying"]
    label = st.session_state["ticker_choice"]
    symbol = resolve_ticker(kind, label)
    clear_loaded_data()
    if symbol is None:
        return
    provider = data_provider()
    if provider is None:
        st.session_state["load_notice"] = [
            "No se pudo preparar la conexión con Yahoo Finance. "
            "Introduce los valores a mano."
        ]
        return

    now = current_time()
    snapshot, notices = load_or_cache(
        symbol,
        provider,
        today=market_today(now),
        now=now,
        cache_dir=st.session_state.get("cache_dir"),
        label=label,
        is_index=(kind == "Índice"),
    )
    notices = [explain_notice(message, label) for message in notices]
    if snapshot is not None:
        fill_market_inputs(snapshot, notices)
        select_first_expiry(snapshot)
    st.session_state["snapshot"] = snapshot
    st.session_state["load_notice"] = notices


def on_expiry_change() -> None:
    """Cambia el vencimiento: los días al vencimiento se ponen solos."""
    expiry = st.session_state.get("expiry_choice")
    if expiry:
        st.session_state["days"] = days_until(expiry)


def selected_chain() -> list:
    """Cotizaciones líquidas del vencimiento elegido ([] si no hay datos).

    Todo lo que ofrece el selector de patas reales sale de aquí, es decir,
    de `snapshot.chains`, que ya viene filtrado (solo opciones líquidas).
    """
    snapshot = st.session_state.get("snapshot")
    expiry = st.session_state.get("expiry_choice")
    if snapshot is None or expiry not in snapshot.chains:
        return []
    return snapshot.chains[expiry]


def quotes_of_kind(chain: list, kind: str) -> list:
    """Cotizaciones de un tipo ("call" o "put"), ordenadas por strike."""
    return sorted((quote for quote in chain if quote.kind == kind), key=lambda q: q.strike)


def find_quote(chain: list, kind: str, strike: float):
    """La cotización de ese tipo y strike, o None si no está."""
    for quote in chain:
        if quote.kind == kind and quote.strike == strike:
            return quote
    return None


def on_add_market_leg() -> None:
    """Botón "Añadir pata" del selector de cadena real.

    La prima es el mid (bid+ask)/2, NUNCA el último precio negociado.
    La pata queda como prima fija (premium_manual=True, premium_source
    "mercado"): el modelo no la recalcula. La IV de Yahoo se guarda solo
    para mostrarla como referencia.
    """
    quote = find_quote(
        selected_chain(),
        st.session_state.get("pick_kind"),
        st.session_state.get("pick_strike"),
    )
    if quote is None:
        return
    leg = new_leg_dict(
        quote.kind,
        st.session_state.get("pick_side", 1),
        st.session_state.get("pick_quantity", 1.0),
        quote.strike,
        quote.mid,
        premium_manual=True,
        premium_source="mercado",
        bid=quote.bid,
        ask=quote.ask,
        iv_yahoo=quote.iv_yahoo,
        expiry=st.session_state["expiry_choice"],
    )
    st.session_state["legs"].append(leg)


# ---------------------------------------------------------------------------
# Barra lateral (siempre se dibuja, en todas las pestañas)
# ---------------------------------------------------------------------------


def render_sidebar() -> Market:
    """Datos globales del mercado. Devuelve el Market con esos datos."""
    with st.sidebar:
        st.header("Datos del mercado")
        st.caption("Valen para todas las patas (un único vencimiento común).")
        # Cada widget usa `key`: su valor vive en st.session_state[key].
        st.selectbox(
            "Tipo de subyacente", UNDERLYINGS, key="underlying", on_change=on_underlying_change
        )
        render_data_loader()
        st.number_input("Precio actual (spot)", step=1.0, format="%.2f", key="spot")
        st.number_input("Volatilidad anual (%)", step=1.0, format="%.2f", key="vol_pct")
        st.number_input("Días al vencimiento", step=1, key="days")
        st.number_input("Tipo de interés libre de riesgo (%)", step=0.25, format="%.2f", key="rate_pct")
        st.number_input("Dividend yield q (%)", step=0.25, format="%.2f", key="q_pct")

        market = market_from_state()
        for message in validate_market(market):
            st.error(message)
    return market


def render_data_loader() -> None:
    """Ticker, botón "Cargar datos", antigüedad, avisos y vencimiento (Etapa C1).

    Con "Entrada manual" solo se ven el selector y el botón desactivado.
    """
    manual = st.session_state["ticker_choice"] == MANUAL_ENTRY
    st.selectbox(
        "Ticker",
        ticker_options(st.session_state["underlying"]),
        key="ticker_choice",
        on_change=on_ticker_change,
        help="Elige un ticker de la lista para cargar sus datos, o escribe tú los valores.",
    )
    st.button("Cargar datos", on_click=on_load_data, disabled=manual, key="load_data")

    snapshot = st.session_state["snapshot"]
    if snapshot is not None:
        # Texto largo: va en caption (st.metric lo recortaría).
        st.caption(age_text(snapshot))
    for message in st.session_state["load_notice"]:
        if message in Q_NOTES:
            st.caption(message)
        elif snapshot is None:
            st.error(message)
        else:
            st.warning(message)
    if snapshot is not None:
        render_expiry_select(snapshot)


def render_expiry_select(snapshot) -> None:
    """Selector de vencimiento: solo los que tienen opciones líquidas."""
    expiries = sorted(snapshot.chains)
    if not expiries:
        return
    # Se ajusta ANTES de crear el widget (permitido por Streamlit).
    if st.session_state.get("expiry_choice") not in expiries:
        st.session_state["expiry_choice"] = expiries[0]
    # Las etiquetas se calculan AQUÍ, dentro de la ejecución del script:
    # Streamlit (y AppTest) pueden volver a llamar a format_func fuera de
    # ella, donde st.session_state (el reloj de las pruebas) no está.
    labels = {expiry: f"{expiry} ({days_until(expiry)} días)" for expiry in expiries}
    st.selectbox(
        "Vencimiento",
        expiries,
        format_func=lambda expiry: labels.get(expiry, str(expiry)),
        key="expiry_choice",
        on_change=on_expiry_change,
    )


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
    """Tarjeta de una plantilla: icono + nombre, badge, idea principal, botón y detalles.

    Layout:
    ┌────────────────────────────────────┐
    │  Icono + Nombre                    │
    │  Badge estrategia (completo)       │
    │ ────────────────────────────────   │
    │  Visión de mercado (color)         │
    │  Texto apuesta                     │
    │  [Botón]                           │
    │  [Expander - Más detalles]         │
    └────────────────────────────────────┘

    Cada st.markdown con HTML es un bloque cerrado: Streamlit no permite
    meter widgets (botones, expanders) dentro de un <div> propio.
    """
    strategy_color = get_strategy_color(template.market_view)
    section_bg = COLOR_SYSTEM["background_light"]

    # Contenedor con borde nativo de Streamlit
    with st.container(border=True):
        # HEADER: icono emoji de la estrategia + nombre, en una sola línea
        st.markdown(
            f"""<div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.25rem;">
            <span style="font-size:1.15rem; font-weight:600; color:{COLOR_SYSTEM['secondary']}; line-height:1.3;">
                {get_strategy_icon(template.market_view)} <strong>{template.name}</strong>
            </span>
        </div>""",
            unsafe_allow_html=True,
        )

        # Badge con la visión de mercado (texto completo, sin recortar)
        st.markdown(
            f"""<div style="display:inline-block; margin-top:0.2rem;">{create_strategy_badge(template.market_view)}</div>""",
            unsafe_allow_html=True,
        )

        # Línea divisoria HTML simple (evita el padding extra de st.divider)
        st.markdown(
            f"""<div style="margin:0.75rem 0; border-top:1px solid {COLOR_SYSTEM['border_subtle']};"></div>""",
            unsafe_allow_html=True,
        )

        # Visión de mercado, en el color de su tipo de estrategia
        st.markdown(
            f"""<span style="color:{strategy_color}; font-weight:600; font-size:1rem;">{template.market_view}</span>""",
            unsafe_allow_html=True,
        )

        # Texto de la apuesta
        st.markdown(
            f'<div style="color:{COLOR_SYSTEM["secondary"]}; font-size:0.875rem; line-height:1.5;">{template.bet}</div>',
            unsafe_allow_html=True,
        )

        # Botón nativo. Si los datos de mercado tienen errores queda
        # desactivado (con candado y una ayuda que explica por qué).
        st.button(
            "Abrir en el constructor",
            key=f"open_{template.key}",
            on_click=open_template,
            args=(template.key,),
            disabled=disabled,
            icon=ICON_WIDGETS["lock"] if disabled else None,
            help="Corrige los datos del mercado en la barra lateral." if disabled else None,
            width="stretch",
        )

        # Expander con el detalle, en secciones con fondo suave
        with st.expander("Más detalles", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(
                    f"""<div style="background-color:{section_bg}; padding:1rem; border-radius:6px;">
                        <h4 style="margin:0 0 0.5rem 0; font-size:0.9rem;">💰 Rentabilidad</h4>
                        <p style="margin:0;"><strong>Beneficio máximo:</strong> {template.max_profit}</p>
                        <p style="margin:0.25rem 0 0 0;"><strong>Pérdida máxima:</strong> {template.max_loss}</p>
                    </div>""",
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown(
                    f"""<div style="background-color:{section_bg}; padding:1rem; border-radius:6px;">
                        <h4 style="margin:0 0 0.5rem 0; font-size:0.9rem;">📅 Cuándo usarla</h4>
                        <p style="margin:0; color:{strategy_color}; line-height:1.6;">{template.when_to_use}</p>
                    </div>""",
                    unsafe_allow_html=True,
                )
            # Sección de riesgos con estilo visual distinto
            st.markdown(
                f"""<div style="margin-top:1rem; padding:0.75rem 1rem; background-color:{section_bg}; border-radius:6px; border-left:3px solid {COLOR_SYSTEM['danger']};">
                    <h4 style="margin:0 0 0.5rem 0; font-size:0.9rem;">⚠️ Riesgos</h4>
                    <p style="margin:0; font-size:0.85rem; color:{COLOR_SYSTEM['danger']};">{template.risks}</p>
                </div>""",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Pestaña Constructor
# ---------------------------------------------------------------------------


def render_builder(market: Market, market_errors: list[str]) -> None:
    """Filas de patas, gráfico, métricas, griegas y avisos."""
    st.subheader("Constructor de estrategias")
    st.caption(active_model_caption(market))
    render_leg_rows(market)
    render_expiry_mismatch_warnings()
    st.button(f"{ICON_WIDGETS['add']} Añadir pata", on_click=add_leg)
    render_chain_picker()
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
    # Guardar (Etapa D): al final, para no mover nada de lo anterior.
    render_save_section(
        st.session_state["legs"],
        market,
        market_errors,
        settings_from_state(),
        resolve_ticker(st.session_state["underlying"], st.session_state["ticker_choice"]),
        current_time(),
        strategies_dir_from_state(),
    )
    render_open_notices()


def chain_picker_visible() -> bool:
    """El selector de patas reales solo existe con datos cargados (no en manual)."""
    return (
        st.session_state["ticker_choice"] != MANUAL_ENTRY
        and st.session_state.get("snapshot") is not None
        and bool(selected_chain())
    )


def quote_label(quote) -> str:
    """Texto de una opción en la lista: strike, bid/ask/mid e IV de Yahoo."""
    if quote.iv_yahoo is None:
        iv_text = "IV Yahoo —"
    else:
        iv_text = f"IV Yahoo {quote.iv_yahoo * 100:.1f} %"
    return (
        f"{quote.strike:.2f} · bid {quote.bid:.2f} / ask {quote.ask:.2f} / "
        f"mid {quote.mid:.2f} · {iv_text}"
    )


def render_chain_picker() -> None:
    """Desplegable para añadir una pata desde la cadena real (Etapa C1).

    Solo ofrece opciones líquidas del vencimiento elegido en la barra
    lateral. Los widgets solo guardan la elección; la pata se crea en el
    callback del botón (on_add_market_leg).
    """
    if not chain_picker_visible():
        return
    chain = selected_chain()
    expiry = st.session_state["expiry_choice"]
    with st.expander("Añadir pata desde la cadena real"):
        st.caption(
            f"Solo opciones líquidas del vencimiento {expiry}. La prima será el mid "
            "(punto medio entre bid y ask); la IV de Yahoo es solo una referencia."
        )
        # Valores iniciales de los widgets (solo la primera vez).
        st.session_state.setdefault("pick_kind", "call")
        st.session_state.setdefault("pick_side", 1)
        st.session_state.setdefault("pick_quantity", 1.0)
        cols = st.columns([1.0, 1.4, 1.0])
        cols[0].selectbox("Tipo", ["call", "put"], format_func=KIND_LABELS.get, key="pick_kind")
        cols[1].selectbox("Dirección", list(SIDE_LABELS), format_func=SIDE_LABELS.get, key="pick_side")
        cols[2].number_input("Contratos", min_value=1.0, step=1.0, format="%g", key="pick_quantity")
        render_strike_select(chain)


def render_strike_select(chain: list) -> None:
    """Lista de strikes líquidos del tipo elegido y botón "Añadir pata"."""
    quotes = quotes_of_kind(chain, st.session_state["pick_kind"])
    if not quotes:
        st.caption("No hay opciones líquidas de este tipo en este vencimiento.")
        return
    labels = {quote.strike: quote_label(quote) for quote in quotes}
    # Se ajusta ANTES de crear el widget (al cambiar call/put o vencimiento).
    if st.session_state.get("pick_strike") not in labels:
        st.session_state["pick_strike"] = quotes[0].strike
    st.selectbox("Strike", list(labels), format_func=labels.get, key="pick_strike")
    st.button("Añadir pata", key="add_market_leg", on_click=on_add_market_leg)


def render_expiry_mismatch_warnings() -> None:
    """Aviso si una pata de mercado es de otro vencimiento que el elegido.

    La app usa un único vencimiento común (los días de la barra lateral);
    la pata no se borra, solo se avisa.
    """
    selected = st.session_state.get("expiry_choice")
    if not selected:
        return
    for number, leg in enumerate(st.session_state["legs"], start=1):
        expiry = leg.get("expiry")
        if expiry and expiry != selected:
            st.warning(
                f"Pata {number}: su cotización es del vencimiento {expiry}, pero el "
                f"vencimiento elegido es {selected}. La app calcula todas las patas "
                "con un único vencimiento (los días de la barra lateral)."
            )


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
        return "🔄 spot", "Volver al precio automático: el spot actual."
    if binomial:
        return "🔄 binomial", "Volver a la prima automática del modelo binomial (americano)."
    return "🔄 BS", "Volver a la prima automática de Black-Scholes (europeo)."


def price_origin(leg: dict, binomial: bool) -> str:
    """De dónde sale el precio de la pata: mercado, manual, spot, binomial o Black-Scholes."""
    if is_market_leg(leg):
        return f"mercado (mid de bid {leg['bid']:.2f} / ask {leg['ask']:.2f})"
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

    # Título de la pata (bloque HTML cerrado: los widgets van debajo, en columnas)
    st.markdown(
        f"""<div style="margin: 0 0 0.25rem 0; display: flex; align-items: center; gap: 0.5rem;">
        <span style="font-size: 1.1rem; font-weight: 600; color: {COLOR_SYSTEM['secondary']};">
            {ICON_WIDGETS["add"]} Pata {number}
        </span>
    </div>""",
        unsafe_allow_html=True,
    )
    cols = st.columns([1.1, 1.4, 1.1, 1.0, 1.2, 0.9, 0.9], vertical_alignment="bottom")

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
    cols[6].button(
        f"{ICON_WIDGETS['remove']} Quitar",
        key=f"leg_{leg_id}_remove",
        on_click=remove_leg,
        args=(leg_id,),
    )
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

    # Título de sección con emoji y divisor nativo de Streamlit
    st.subheader("💰 Resultados al vencimiento", divider=True)
    cols = st.columns(3)
    cols[0].metric("Beneficio máximo", best)
    cols[1].metric("Pérdida máxima", worst)
    cols[2].metric("Comisiones totales", format_usd(analysis.commission_total))
    st.markdown(f"**Breakevens:** {breakevens}")


def render_greeks(greeks: dict) -> None:
    """Tabla de griegas de la posición ("—" si no se pueden calcular).

    Se usa st.table (nativa): respeta el tema claro/oscuro de Streamlit.
    """
    st.subheader("📐 Griegas de la posición (hoy, al precio spot)", divider=True)
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
        render_yahoo_iv(item)
        return
    vol_pct = round(result.vol * 100, 2)
    st.caption(f"{name}: volatilidad implícita {vol_pct:.2f} %")
    render_yahoo_iv(item)
    st.button(
        "Usar como volatilidad global",
        key=f"use_iv_{item['id']}",
        on_click=use_iv_as_global,
        args=(vol_pct,),
    )


def render_yahoo_iv(item: dict) -> None:
    """IV publicada por Yahoo, solo como referencia (no entra en ningún cálculo)."""
    iv_yahoo = item.get("iv_yahoo")
    if iv_yahoo is not None:
        st.caption(f"IV Yahoo (referencia): {iv_yahoo * 100:.2f} %")


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

    # Título principal con icono destacado (sin color fijo: sirve en ambos temas)
    st.markdown(
        """<div style="display: flex; align-items: center; gap: 0.75rem; justify-content: center">
        <span style="font-size: 2.5em;">🎓</span>
        <span style="font-size: 1.75em; font-weight: 700;">Laboratorio de Opciones</span>
    </div>""",
        unsafe_allow_html=True,
    )
    st.caption("Herramienta de estudio, no asesoría de inversión.")

    market = render_sidebar()
    market_errors = validate_market(market)
    if not market_errors:
        refresh_auto_prices(market)

    # Con key + on_change="rerun", la pestaña activa vive en
    # st.session_state["main_tab"] (su etiqueta, con icono: ver TAB_NAMES)
    # y un callback puede cambiarla.
    catalog_tab, builder_tab, compare_tab, saved_tab, settings_tab, backtest_tab = st.tabs(
        TAB_NAMES, key="main_tab", on_change="rerun"
    )
    with catalog_tab:
        render_catalog(market_errors)
    with builder_tab:
        render_builder(market, market_errors)
    with compare_tab:
        render_compare(
            market,
            market_errors,
            legs_from_state(),
            settings_from_state(),
            sim_settings_from_state(),
            strategies_dir_from_state(),
        )
    with saved_tab:
        render_my_strategies(strategies_dir_from_state(), current_time(), open_saved_strategy)
    with settings_tab:
        render_settings()
    with backtest_tab:
        # Se pasa la FUNCIÓN data_provider (sin llamarla): el proveedor solo
        # se crea al pulsar "Cargar histórico".
        render_backtest(
            data_provider,
            current_time(),
            settings_from_state(),
            st.session_state["underlying"],
            st.session_state["ticker_choice"],
            percent_to_fraction(st.session_state["rate_pct"]) or 0.0,
            st.session_state.get("cache_dir"),
        )


main()
