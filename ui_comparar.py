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

import streamlit as st

from estrategias import store
from estrategias.compare import MAX_STRATEGIES

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


def init_compare_state() -> None:
    """Crea las entradas de la pestaña la primera vez (sin pisar las existentes)."""
    st.session_state.setdefault("cmp_selected", [])
    st.session_state.setdefault("cmp_heavy", False)


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
    """Dibuja la pestaña Comparar."""
    st.subheader("⚖️ Comparar estrategias", divider=True)
    st.caption(MSG_CMP_INTRO)
    chosen = render_selector(strategies_dir)
    if not chosen:
        st.info(MSG_CMP_GUIDE)
        return
