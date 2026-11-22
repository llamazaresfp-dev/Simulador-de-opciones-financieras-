"""Pestaña "Comparar" de la app (Etapa D).

Qué hace: dibuja juntas, con el MISMO mercado (el de la barra lateral) y
las mismas comisiones (las de Ajustes), la estrategia del Constructor y
hasta 3 estrategias guardadas: curvas de P&L al vencimiento superpuestas
y una tabla lado a lado.

Reglas (las mismas que en el resto de la app):
- Nada pesado sin casilla: las curvas «hoy» y las griegas solo se
  calculan si se marca "Incluir curvas «hoy» y griegas".
- La selección sigue el patrón de Ajustes: el widget `cmp_selected_input`
  copia su valor a la entrada simple `cmp_selected` con un callback, y
  antes de crear el widget se le pone la selección saneada (sin slugs de
  estrategias borradas o ilegibles).
- La carpeta llega como argumento (None = la carpeta por defecto).

Este archivo no importa app.py (app.py ejecuta la app al importarse).
"""

import plotly.graph_objects as go
import streamlit as st

from estrategias import compare, store
from estrategias.compare import MAX_STRATEGIES
from opciones.validation import MSG_NOT_ADVICE

# Guardadas que caben en la comparación (la del Constructor ocupa un hueco).
MAX_SELECTED = MAX_STRATEGIES - 1

MSG_CMP_INTRO = (
    "Compara la estrategia del Constructor con hasta 3 estrategias guardadas "
    "(máximo 4 en total)."
)
MSG_CMP_GUIDE = (
    "Elige al menos una estrategia guardada para compararla con la del Constructor. "
    "Puedes añadirlas aquí o con «⚖️ Añadir a comparar» en «💾 Mis estrategias»."
)
MSG_CMP_NO_SAVED = "Todavía no hay estrategias guardadas: guarda una desde el Constructor."
MSG_CMP_SAME_MARKET = (
    "Todas se calculan con el mercado de la barra lateral y las comisiones de Ajustes. "
    "Las primas automáticas de las guardadas se recalculan con ese mercado; las "
    "manuales y las de mercado se mantienen. Las comisiones guardadas solo vuelven "
    "con «Abrir con su mercado»."
)
MSG_CMP_MARKET_INVALID = (
    "No se puede comparar: corrige los datos del mercado en la barra lateral."
)
MSG_CMP_FAILED = "No se pudo calcular la comparación."
MSG_CMP_HEAVY_HELP = (
    "Las curvas «hoy» y las griegas usan el modelo activo (con el binomial pueden "
    "tardar unos segundos la primera vez)."
)
BUILDER_LABEL = "🛠️ Constructor"

# Paleta apta para daltónicos (DD-15): azul sólida (Constructor), naranja
# discontinua, verde azulado punteada y magenta raya-punto.
SERIES_STYLES = [
    ("#2a78d6", "solid"),
    ("#eb6834", "dash"),
    ("#009e73", "dot"),
    ("#cc79a7", "dashdot"),
]
# Colores neutros del gráfico del Constructor (línea de cero y de spot).
COLOR_NEUTRAL = "#8a8985"
GREEK_SYMBOLS = {"delta": "Δ", "gamma": "Γ", "theta": "Θ", "vega": "ν", "rho": "ρ"}


def init_compare_state() -> None:
    """Crea las entradas de la pestaña la primera vez (sin pisar las existentes)."""
    st.session_state.setdefault("cmp_selected", [])
    st.session_state.setdefault("cmp_heavy", False)


def series_style(index: int) -> tuple[str, str]:
    """(color, estilo de línea) de la serie `index` (0 = Constructor).

    Solo hay 4 estilos: nunca se compara más de 4 estrategias.
    """
    if not 0 <= index < len(SERIES_STYLES):
        raise ValueError(f"No hay estilo para la serie {index}: máximo {len(SERIES_STYLES)}.")
    return SERIES_STYLES[index]


def copy_cmp_heavy() -> None:
    """Callback de la casilla "hoy y griegas"."""
    st.session_state["cmp_heavy"] = st.session_state["cmp_heavy_input"]


def copy_cmp_selected() -> None:
    """Callback del selector: copia el widget a la entrada simple."""
    st.session_state["cmp_selected"] = list(st.session_state["cmp_selected_input"])


def drop_from_selection(slug: str) -> None:
    """Quita un slug de la selección (clave simple y clave del widget, DD-9)."""
    selected = [item for item in st.session_state.get("cmp_selected", []) if item != slug]
    st.session_state["cmp_selected"] = selected
    st.session_state["cmp_selected_input"] = list(selected)


def render_selector(strategies_dir) -> list:
    """Selector de hasta 3 estrategias guardadas. Devuelve las elegidas (StoredStrategy).

    La selección se sanea ANTES de crear el widget: un slug borrado o
    ilegible desaparece de la clave simple y de la del widget (DD-9).
    """
    items, _warnings = store.list_saved(strategies_dir)  # los ilegibles se omiten
    by_slug = {item.slug: item for item in items}
    selected = [slug for slug in st.session_state["cmp_selected"] if slug in by_slug][:MAX_SELECTED]
    st.session_state["cmp_selected"] = selected
    st.session_state["cmp_selected_input"] = list(selected)
    if not items:
        st.caption(MSG_CMP_NO_SAVED)
        return []
    # Etiquetas calculadas AQUÍ: format_func no puede leer session_state.
    labels = {item.slug: item.strategy.name for item in items}
    st.multiselect(
        "Estrategias guardadas (hasta 3)",
        list(labels),
        format_func=lambda slug: labels.get(slug, slug),
        max_selections=MAX_SELECTED,
        placeholder="Elige estrategias guardadas",
        key="cmp_selected_input",
        on_change=copy_cmp_selected,
    )
    return [by_slug[slug] for slug in selected]


def render_compare(market, market_errors, builder_legs, settings, sim, strategies_dir) -> None:
    """Dibuja la pestaña Comparar.

    - market / market_errors: mercado de la barra lateral y sus errores.
    - builder_legs: patas del Constructor (objetos Leg del motor).
    - settings: comisiones de Ajustes; sim: ajustes de la simulación (PoP).
    - strategies_dir: carpeta de estrategias (None = la por defecto).
    """
    st.subheader("⚖️ Comparar estrategias", divider=True)
    st.caption(MSG_CMP_INTRO)
    chosen = render_selector(strategies_dir)
    st.session_state["cmp_heavy_input"] = st.session_state["cmp_heavy"]
    st.checkbox(
        "Incluir curvas «hoy» y griegas",
        key="cmp_heavy_input",
        on_change=copy_cmp_heavy,
        help=MSG_CMP_HEAVY_HELP,
    )
    if not chosen:
        st.info(MSG_CMP_GUIDE)
        return
    st.caption(MSG_CMP_SAME_MARKET)
    if market_errors:
        st.warning(MSG_CMP_MARKET_INVALID)
        return
    try:
        render_comparison(market, builder_legs, settings, sim, chosen, st.session_state["cmp_heavy"])
    except Exception:
        # Red de seguridad (DD-22): nunca un traceback en la pestaña.
        st.error(MSG_CMP_FAILED)


def render_comparison(market, builder_legs, settings, sim, chosen, with_heavy: bool) -> None:
    """Calcula y dibuja: avisos, gráfico superpuesto y tabla."""
    entries = [(BUILDER_LABEL, builder_legs)]
    notices = []
    for item in chosen:
        strategy = item.strategy
        entries.append((strategy.name, compare.revalue_legs(strategy.legs, market)))
        notice = compare.market_difference_notice(strategy.name, strategy.market, market)
        if notice is not None:
            notices.append(notice)

    result = compare.compare_strategies(entries, market, settings, sim, with_heavy=with_heavy)
    for message in result.errors:
        st.warning(message)
    for notice in notices:
        st.info(notice)
    if not result.rows:
        return

    labels = [label for label, _legs in entries]
    st.plotly_chart(build_compare_figure(result, market, labels, with_heavy), width="stretch", key="cmp_chart")
    st.subheader("📋 Tabla comparativa", divider=True)
    st.dataframe(comparison_table(result.rows, with_heavy), hide_index=True, width="stretch")
    st.caption(MSG_NOT_ADVICE)


def build_compare_figure(result, market, labels, with_today: bool) -> go.Figure:
    """Curvas al vencimiento superpuestas (+ «hoy» si se piden) y breakevens.

    - labels: etiquetas de TODAS las entradas en orden (fija el color de
      cada estrategia aunque alguna se haya omitido por error).
    - Las curvas «hoy» van sobre la malla propia de cada estrategia (DD-23).
    """
    fig = go.Figure()
    for position, row in enumerate(result.rows):
        color, dash = series_style(labels.index(row.label))
        fig.add_trace(
            go.Scatter(
                x=result.grid,
                y=result.expiry_curves[position],
                name=row.label,
                mode="lines",
                line={"color": color, "dash": dash, "width": 2},
                hovertemplate="%{y:.2f} USD",
            )
        )
        if with_today and result.today_curves is not None:
            today_grid, today_curve = result.today_curves[position]
            fig.add_trace(
                go.Scatter(
                    x=today_grid,
                    y=today_curve,
                    name=f"{row.label} (hoy)",
                    mode="lines",
                    line={"color": color, "dash": dash, "width": 1},
                    opacity=0.5,
                    hovertemplate="%{y:.2f} USD",
                )
            )
        if row.breakevens:
            fig.add_trace(
                go.Scatter(
                    x=row.breakevens,
                    y=[0] * len(row.breakevens),
                    name=f"{row.label}: breakeven",
                    mode="markers",
                    marker={"color": color, "size": 10, "symbol": "diamond"},
                    hovertemplate="Breakeven %{x:.2f}<extra></extra>",
                    showlegend=False,
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
        yaxis_title="P&L al vencimiento (USD)",
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.12},
        margin={"t": 40, "b": 40},
    )
    return fig


# ---------------------------------------------------------------------------
# Tabla comparativa (todo texto: así cada celda dice "ilimitado" o "—")
# ---------------------------------------------------------------------------


def _usd(value: float) -> str:
    return f"{value:.2f} USD"


def _premium_text(value: float) -> str:
    """Prima neta (DD-12): crédito si se cobra al abrir, débito si se paga."""
    if value > 0:
        return f"Crédito {value:.2f} USD"
    if value < 0:
        return f"Débito {-value:.2f} USD"
    return "0.00 USD"


def _greeks_text(greeks) -> str:
    """Griegas en una celda: "Δ 0.5000 · Γ 0.0300 · …" ("—" si no existen, p. ej. días = 0)."""
    if greeks is None or all(value is None for value in greeks.values()):
        return "—"
    parts = []
    for name, symbol in GREEK_SYMBOLS.items():
        value = greeks.get(name)
        parts.append(f"{symbol} {'—' if value is None else f'{value:.4f}'}")
    return " · ".join(parts)


def comparison_table(rows, with_greeks: bool) -> list[dict]:
    """Filas de la tabla lado a lado (una por estrategia)."""
    table = []
    for row in rows:
        item = {
            "Estrategia": row.label,
            "Ganancia máx.": "ilimitada" if row.profit_unlimited else _usd(row.best_pnl),
            "Pérdida máx.": "ilimitada" if row.loss_unlimited else _usd(row.worst_pnl),
            "Breakevens": " y ".join(f"{value:.2f}" for value in row.breakevens) or "ninguno",
            "Comisiones": _usd(row.commission_total),
            "Prima neta": _premium_text(row.net_premium),
            "PoP": "—" if row.pop is None else f"{row.pop * 100:.1f} %",
        }
        if with_greeks:
            item["Griegas (hoy)"] = _greeks_text(row.greeks)
        table.append(item)
    return table
