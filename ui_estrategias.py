"""Guardar estrategias (Constructor) y pestaña "Mis estrategias" (Etapa D).

Qué hace:
- Al final del Constructor, la sección "Guardar esta estrategia": nombre,
  casilla "sobrescribir", botón Guardar y botón "Descargar JSON" (los dos
  usan los MISMOS bytes, preparados una sola vez por ejecución).
- La pestaña "Mis estrategias": lista de lo guardado (nombre, fecha, nº de
  patas) con abrir, descargar, añadir a la comparación y borrar con
  confirmación en dos pasos.

Reglas (las mismas que en el resto de la app):
- Nada pesado sin clic: al abrir la app solo se lista la carpeta (si no
  existe, no se crea).
- Los widgets (`sv_*_input`) copian su valor a una entrada simple (`sv_*`)
  con un callback; las pestañas son "perezosas" y un widget no dibujado
  pierde su valor. Antes de crear cada widget se le pone el valor de la
  entrada simple (como sync_widget en app.py).
- "Guardar" se procesa en el cuerpo (`if st.button(...)`) y muestra su
  mensaje ahí mismo. Los botones que cambian estado de widgets (abrir,
  añadir, borrar) son callbacks y dejan su mensaje en `sv_message`.
- La carpeta llega como argumento (None = la carpeta por defecto, que
  estrategias.store lee en cada llamada).

Este archivo no importa app.py (app.py ejecuta la app al importarse).
"""

from datetime import date

import streamlit as st

from estrategias import store
from estrategias.compare import MAX_STRATEGIES, MSG_MAX
from estrategias.serialize import MAX_BYTES, MAX_NAME_LEN, prepare_document

# Guardadas que caben en la comparación (la del Constructor ocupa un hueco).
MAX_SELECTED = MAX_STRATEGIES - 1

# ---------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------

MSG_SV_INTRO = (
    "Guarda la estrategia en la carpeta local `.estrategias/` de este equipo o "
    "descárgala como archivo JSON. Se guardan las patas, el mercado de la barra "
    "lateral y las comisiones de Ajustes."
)
MSG_SV_DOWNLOAD_DISABLED = (
    "Guardar y descargar se activan cuando la estrategia tiene nombre, al menos "
    "una pata y datos válidos."
)
MSG_SV_EMPTY = (
    "Todavía no hay estrategias guardadas. Guarda una desde el Constructor "
    "(sección «Guardar esta estrategia») o sube un archivo JSON."
)
MSG_SV_LIST_INTRO = (
    "Estrategias guardadas en la carpeta local `.estrategias/`. «Abrir con su "
    "mercado» restaura también la barra lateral y los Ajustes; «Abrir solo las "
    "patas» mantiene tu mercado actual."
)
MSG_SV_ADDED = "«{name}» se añadió a la comparación (pestaña «⚖️ Comparar»)."
MSG_SV_ALREADY = "«{name}» ya está en la comparación."
MSG_SV_CONFIRM = "¿Borrar «{name}»? Esta acción no se puede deshacer."
MSG_SV_DELETED = "Estrategia «{name}» borrada."
MSG_SV_UPLOAD_INTRO = (
    "Sube un archivo JSON descargado de esta app. Se revisa con cuidado antes de "
    "aceptarlo (tamaño máximo 256 KB) y se añade a la lista."
)
MSG_SV_UPLOAD_FAILED = "No se pudo leer el archivo subido."

# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

SV_DEFAULTS = {
    "sv_name": "",
    "sv_overwrite": False,
    "sv_up_overwrite": False,
}


def init_strategies_state() -> None:
    """Crea las entradas de esta parte la primera vez (sin pisar las existentes).

    - sv_name / sv_overwrite / sv_up_overwrite: valores de los widgets.
    - sv_message: None o (nivel, texto) que deja un callback.
    - sv_confirm: None o el slug cuyo borrado espera confirmación.
    - open_notices: avisos al abrir una estrategia (p. ej. cotización vieja).
    """
    for key, value in SV_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("sv_message", None)
    st.session_state.setdefault("sv_confirm", None)
    st.session_state.setdefault("open_notices", [])


def copy_sv_field(field: str) -> None:
    """Callback: copia el widget `field_input` a su entrada simple `field`."""
    st.session_state[field] = st.session_state[f"{field}_input"]


def _sync_input(field: str) -> str:
    """Pone en el widget el valor de la entrada simple y devuelve su clave.

    Se hace ANTES de crear el widget (permitido por Streamlit).
    """
    key = f"{field}_input"
    st.session_state[key] = st.session_state[field]
    return key


def _set_selection(slugs: list[str]) -> None:
    """Cambia la selección de la comparación: clave simple Y clave del widget (DD-9)."""
    st.session_state["cmp_selected"] = list(slugs)
    st.session_state["cmp_selected_input"] = list(slugs)


# ---------------------------------------------------------------------------
# Callbacks de "Mis estrategias"
# ---------------------------------------------------------------------------


def add_to_compare(slug: str, name: str | None = None) -> None:
    """Botón "Añadir a comparar": añade el slug a la selección (máx. 3 guardadas)."""
    name = name or slug
    selected = list(st.session_state.get("cmp_selected", []))
    if slug in selected:
        st.session_state["sv_message"] = ("info", MSG_SV_ALREADY.format(name=name))
        return
    if len(selected) >= MAX_SELECTED:
        st.session_state["sv_message"] = ("warning", MSG_MAX)
        return
    _set_selection(selected + [slug])
    st.session_state["sv_message"] = ("success", MSG_SV_ADDED.format(name=name))


def request_delete(slug: str) -> None:
    """Botón "Borrar" (primer paso): pide confirmación."""
    st.session_state["sv_confirm"] = slug


def cancel_delete() -> None:
    """Botón "Cancelar" de la confirmación: no se borra nada."""
    st.session_state["sv_confirm"] = None


def confirm_delete(slug: str, strategies_dir=None, name: str | None = None) -> None:
    """Botón "Sí, borrar" (segundo paso): borra el archivo y lo quita de la comparación."""
    st.session_state["sv_confirm"] = None
    ok, message = store.delete_strategy(slug, strategies_dir)
    selected = [item for item in st.session_state.get("cmp_selected", []) if item != slug]
    _set_selection(selected)
    if ok:
        st.session_state["sv_message"] = ("success", MSG_SV_DELETED.format(name=name or slug))
    else:
        st.session_state["sv_message"] = ("error", message)


# ---------------------------------------------------------------------------
# Sección "Guardar esta estrategia" (al final del Constructor)
# ---------------------------------------------------------------------------


def render_save_section(legs, market, market_errors, settings, ticker, now, strategies_dir) -> None:
    """Nombre, "sobrescribir", Guardar y Descargar JSON.

    - legs: patas de la app (diccionarios de session_state["legs"]).
    - market / market_errors: mercado de la barra lateral y sus errores.
    - settings: comisiones de Ajustes; ticker: símbolo cargado o None.
    - now: hora actual (fecha de guardado); strategies_dir: carpeta o None.
    """
    st.subheader("💾 Guardar esta estrategia", divider=True)
    st.caption(MSG_SV_INTRO)
    cols = st.columns([3.0, 1.2], vertical_alignment="bottom")
    cols[0].text_input(
        "Nombre de la estrategia",
        max_chars=MAX_NAME_LEN,
        placeholder="p. ej. Iron condor SPY",
        key=_sync_input("sv_name"),
        on_change=copy_sv_field,
        args=("sv_name",),
    )
    cols[1].checkbox(
        "Sobrescribir si ya existe",
        key=_sync_input("sv_overwrite"),
        on_change=copy_sv_field,
        args=("sv_overwrite",),
    )

    # Los bytes se preparan UNA vez: son los que se guardan y los que se descargan.
    name = st.session_state["sv_name"]
    raw, errors = prepare_document(legs, market, settings, name, now, ticker)

    cols = st.columns(2)
    clicked = cols[0].button("💾 Guardar", key="sv_save", width="stretch")
    cols[1].download_button(
        "⬇️ Descargar JSON",
        data=raw if raw is not None else b"",
        file_name=f"{store.slugify(name)}.json",
        mime="application/json",
        key="sv_download",
        disabled=raw is None,
        width="stretch",
    )
    if raw is None:
        st.caption(MSG_SV_DOWNLOAD_DISABLED)

    if clicked:
        save_clicked(raw, errors, strategies_dir)


def save_clicked(raw, errors: list[str], strategies_dir) -> None:
    """Procesa el clic en "Guardar" (en el cuerpo: no cambia widgets)."""
    if raw is None:
        for message in errors:
            st.error(message)
        return
    result = store.save_document(raw, strategies_dir, st.session_state["sv_overwrite"])
    if result.ok:
        st.success(result.message)
    elif result.exists:
        st.warning(result.message)
    else:
        st.error(result.message)


def render_open_notices() -> None:
    """Avisos de la última estrategia abierta (p. ej. cotización guardada vieja).

    Va al final del Constructor; solo dibuja algo si hay avisos.
    """
    for message in st.session_state.get("open_notices", []):
        st.info(message)


# ---------------------------------------------------------------------------
# Subir un archivo JSON
# ---------------------------------------------------------------------------


def import_uploaded(raw, strategies_dir=None, overwrite: bool = False) -> tuple[bool, str]:
    """Valida y guarda los bytes de un archivo subido. Devuelve (ok, mensaje).

    Es la misma función que usa el botón "Guardar archivo subido". El
    archivo se revisa con parse_strategy_json (dentro de save_document):
    si no vale, no se escribe nada. Nunca lanza.
    """
    try:
        if not isinstance(raw, (bytes, bytearray)):
            return False, MSG_SV_UPLOAD_FAILED
        result = store.save_document(bytes(raw), strategies_dir, overwrite)
    except Exception:
        return False, MSG_SV_UPLOAD_FAILED
    return result.ok, result.message


def render_upload(strategies_dir) -> None:
    """Subida de un JSON: archivo, "sobrescribir" y botón (procesado en el cuerpo).

    Va ANTES de la lista: así lo recién subido ya aparece en esta ejecución.
    """
    with st.expander("📤 Subir una estrategia (JSON)"):
        st.caption(MSG_SV_UPLOAD_INTRO)
        uploaded = st.file_uploader("Archivo JSON", type=["json"], key="sv_upload")
        st.checkbox(
            "Sobrescribir si ya existe una con el mismo nombre",
            key=_sync_input("sv_up_overwrite"),
            on_change=copy_sv_field,
            args=("sv_up_overwrite",),
        )
        if st.button("📤 Guardar archivo subido", key="sv_upload_save") and uploaded is not None:
            # Se lee como mucho un byte más del tope: así un archivo enorme se
            # rechaza sin leerlo entero (DD-17).
            raw = uploaded.read(MAX_BYTES + 1)
            ok, message = import_uploaded(raw, strategies_dir, st.session_state["sv_up_overwrite"])
            if ok:
                st.success(message)
            else:
                st.error(message)


# ---------------------------------------------------------------------------
# Pestaña "Mis estrategias"
# ---------------------------------------------------------------------------


def render_message() -> None:
    """Muestra (una sola vez) el mensaje que dejó el último callback."""
    message = st.session_state.get("sv_message")
    st.session_state["sv_message"] = None
    if not message:
        return
    level, text = message
    show = {"success": st.success, "warning": st.warning, "error": st.error}.get(level, st.info)
    show(text)


def saved_date(saved_at: str) -> str:
    """Parte de fecha de `saved_at` (ISO): "2026-11-20T10:30:00-05:00" -> "2026-11-20"."""
    return saved_at[:10]


def age_label(saved_at: str, now) -> str:
    """Fecha de guardado y antigüedad en días ("2026-11-20, hace 2 días")."""
    day = saved_date(saved_at)
    try:
        days = (now.date() - date.fromisoformat(day)).days
    except (ValueError, AttributeError):
        return day
    if days <= 0:
        return f"{day}, hoy"
    if days == 1:
        return f"{day}, hace 1 día"
    return f"{day}, hace {days} días"


def render_my_strategies(strategies_dir, now, on_open) -> None:
    """Dibuja la pestaña "Mis estrategias".

    - strategies_dir: carpeta (None = la por defecto).
    - now: hora actual (para la antigüedad de cada estrategia).
    - on_open: callback de app.py `on_open(slug, with_market)` (None = sin
      botones "Abrir").
    """
    st.subheader("💾 Mis estrategias", divider=True)
    st.caption(MSG_SV_LIST_INTRO)
    render_message()
    render_upload(strategies_dir)

    items, warnings = store.list_saved(strategies_dir)
    for warning in warnings:
        # Nota (no advertencia): el archivo se omite y el resto se lista.
        st.caption(f"{warning} Se omite.")
    if not items:
        st.info(MSG_SV_EMPTY)
    for item in items:
        render_saved_item(item, strategies_dir, now, on_open)


def render_saved_item(item, strategies_dir, now, on_open) -> None:
    """Tarjeta de una estrategia guardada con sus botones (claves derivadas del slug)."""
    strategy = item.strategy
    slug = item.slug
    with st.container(border=True):
        st.markdown(f"**{strategy.name}**")
        n_legs = len(strategy.legs)
        legs_text = "1 pata" if n_legs == 1 else f"{n_legs} patas"
        ticker = f" · {strategy.ticker}" if strategy.ticker else ""
        st.caption(f"Guardada el {age_label(strategy.saved_at, now)} · {legs_text}{ticker}")
        cols = st.columns(5)
        if on_open is not None:
            cols[0].button(
                "📂 Abrir con su mercado",
                key=f"sv_open_mkt_{slug}",
                on_click=on_open,
                args=(slug, True),
                width="stretch",
            )
            cols[1].button(
                "📂 Abrir solo las patas",
                key=f"sv_open_legs_{slug}",
                on_click=on_open,
                args=(slug, False),
                width="stretch",
            )
        cols[2].button(
            "⚖️ Añadir a comparar",
            key=f"sv_compare_{slug}",
            on_click=add_to_compare,
            args=(slug, strategy.name),
            width="stretch",
        )
        cols[3].download_button(
            "⬇️ Descargar JSON",
            data=item.raw,
            file_name=f"{slug}.json",
            mime="application/json",
            key=f"sv_download_{slug}",
            width="stretch",
        )
        cols[4].button(
            "🗑️ Borrar",
            key=f"sv_delete_{slug}",
            on_click=request_delete,
            args=(slug,),
            width="stretch",
        )
        if st.session_state.get("sv_confirm") == slug:
            render_delete_confirm(slug, strategy.name, strategies_dir)


def render_delete_confirm(slug: str, name: str, strategies_dir) -> None:
    """Segundo paso del borrado: "Sí, borrar" o "Cancelar"."""
    st.warning(MSG_SV_CONFIRM.format(name=name))
    cols = st.columns(2)
    cols[0].button(
        "🗑️ Sí, borrar",
        key="sv_confirm_yes",
        on_click=confirm_delete,
        args=(slug, strategies_dir, name),
        width="stretch",
    )
    cols[1].button("Cancelar", key="sv_confirm_no", on_click=cancel_delete, width="stretch")
