"""Tests de la interfaz de Etapa D: guardar en el Constructor y "Mis estrategias".

AppTest ejecuta app.py sin navegador. Siempre con la carpeta de
estrategias en tmp_path (inyectada en session_state["strategies_dir"]),
proveedor falso, caché en tmp_path y reloj fijo: ningún test toca la red,
ni `.estrategias/` ni `.cache_datos/` reales.
"""

import json

import pytest
from streamlit.testing.v1 import AppTest

from datos import FakeProvider
from estrategias import store
from estrategias.compare import MSG_MAX
from estrategias.serialize import MSG_EMPTY_NAME, MSG_NO_LEGS, prepare_document
from opciones import CommissionSettings, Market
from tests.test_app_smoke import APP_PATH, FIXED_NOW
from ui_estrategias import MSG_SV_CONFIRM, MSG_SV_DOWNLOAD_DISABLED, MSG_SV_EMPTY

TAB_LABELS = [
    "📊 Catálogo",
    "🛠️ Constructor",
    "⚖️ Comparar",
    "💾 Mis estrategias",
    "⚙️ Ajustes",
    "📈 Backtest",
]
BUILDER, COMPARE, SAVED = 1, 2, 3

# Mercado y comisiones por defecto de la app (barra lateral y Ajustes).
DEFAULT_MARKET = Market("Acción", 100.0, 0.2, 30, 0.04, 0.0, "binomial")
DEFAULT_SETTINGS = CommissionSettings()


# ---------------------------------------------------------------------------
# Ayudantes
# ---------------------------------------------------------------------------


def saved_app(tmp_path, timeout: int = 30) -> AppTest:
    """App con carpeta de estrategias, caché, proveedor y reloj inyectados."""
    at = AppTest.from_file(APP_PATH, default_timeout=timeout)
    at.session_state["strategies_dir"] = str(folder_of(tmp_path))
    at.session_state["data_provider"] = FakeProvider(today=FIXED_NOW)
    at.session_state["cache_dir"] = str(tmp_path / "cache")
    at.session_state["clock"] = lambda: FIXED_NOW
    at.run()
    return at


def folder_of(tmp_path):
    return tmp_path / "estrategias"


def json_files(tmp_path) -> list[str]:
    folder = folder_of(tmp_path)
    if not folder.exists():
        return []
    return sorted(path.name for path in folder.iterdir() if path.suffix == ".json")


def leg(kind="call", side=1, quantity=1.0, strike=100.0, price=2.5, manual=False, **extra) -> dict:
    """Pata como diccionario de la app (para guardar estrategias de prueba)."""
    item = {
        "id": 0,
        "kind": kind,
        "side": side,
        "quantity": quantity,
        "strike": None if kind == "stock" else strike,
        "price": price,
        "premium_manual": manual,
        "premium_source": None,
        "bid": None,
        "ask": None,
        "iv_yahoo": None,
        "expiry": None,
    }
    item.update(extra)
    return item


def save_strategy(tmp_path, name, legs=None, market=DEFAULT_MARKET, settings=DEFAULT_SETTINGS, ticker=None):
    """Guarda una estrategia en la carpeta de pruebas; devuelve su slug."""
    legs = legs or [leg()]
    raw, errors = prepare_document(legs, market, settings, name, FIXED_NOW, ticker)
    assert errors == []
    result = store.save_document(raw, folder_of(tmp_path))
    assert result.ok, result.message
    return result.slug


def type_name(at: AppTest, name: str) -> AppTest:
    at.text_input(key="sv_name_input").set_value(name).run()
    return at


def click(at: AppTest, key: str) -> AppTest:
    at.button(key=key).click().run()
    return at


def tab_values(at: AppTest, index: int, kind: str) -> list[str]:
    return [element.value for element in getattr(at.tabs[index], kind)]


def download_button(at: AppTest, key: str):
    for element in at.get("download_button"):
        if element.key == key:
            return element
    return None


def saved_names(at: AppTest) -> list[str]:
    """Nombres de las tarjetas de "Mis estrategias", en orden."""
    return [text[2:-2] for text in tab_values(at, SAVED, "markdown") if text.startswith("**")]


# ---------------------------------------------------------------------------
# Bloque 5: pestañas, estado inicial, nada sin clic
# ---------------------------------------------------------------------------


def test_six_tabs_in_spec_order(tmp_path):
    at = saved_app(tmp_path)
    assert not at.exception
    assert [tab.label for tab in at.tabs] == TAB_LABELS


def test_initial_state_keys(tmp_path):
    state = saved_app(tmp_path).session_state
    assert state["sv_name"] == ""
    assert state["sv_overwrite"] is False
    assert state["sv_up_overwrite"] is False
    assert state["sv_message"] is None
    assert state["sv_confirm"] is None
    assert state["open_notices"] == []
    assert state["cmp_selected"] == []
    assert state["cmp_heavy"] is False


def test_default_app_shows_guide_and_no_error_or_warning(tmp_path):
    at = saved_app(tmp_path)
    assert MSG_SV_EMPTY in tab_values(at, SAVED, "info")
    assert not at.error and not at.warning
    # Nada pesado ni nuevo: el mismo número de gráficos que antes de la Etapa D.
    assert len(at.get("plotly_chart")) == 2
    assert at.get("dataframe") == []


def test_nothing_written_without_click(tmp_path):
    at = saved_app(tmp_path)
    type_name(at, "Sin guardar")
    at.run()
    assert not folder_of(tmp_path).exists()


def test_default_folder_is_redirected_by_conftest(tmp_path):
    """Sin carpeta inyectada, la app usa la carpeta por defecto (redirigida a tmp)."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    type_name(at, "Por defecto")
    click(at, "sv_save")
    assert not at.exception
    default = store.DEFAULT_STRATEGIES_DIR
    assert (default / "por-defecto.json").is_file()
    assert "laboratorio-opciones/.estrategias" not in str(default)


# ---------------------------------------------------------------------------
# Bloque 5: "Guardar esta estrategia"
# ---------------------------------------------------------------------------


def test_save_writes_prepare_document_bytes(tmp_path):
    at = saved_app(tmp_path)
    type_name(at, "Call de prueba")
    expected, errors = prepare_document(
        at.session_state["legs"], DEFAULT_MARKET, DEFAULT_SETTINGS, "Call de prueba", FIXED_NOW, None
    )
    assert errors == []
    click(at, "sv_save")

    assert not at.exception
    assert json_files(tmp_path) == ["call-de-prueba.json"]
    assert (folder_of(tmp_path) / "call-de-prueba.json").read_bytes() == expected
    assert any("guardada" in text for text in tab_values(at, BUILDER, "success"))


def test_save_without_legs_shows_error_and_writes_nothing(tmp_path):
    at = saved_app(tmp_path)
    leg_id = at.session_state["legs"][0]["id"]
    click(at, f"leg_{leg_id}_remove")
    type_name(at, "Vacía")
    click(at, "sv_save")
    assert MSG_NO_LEGS in [error.value for error in at.error]
    assert json_files(tmp_path) == []


def test_save_with_empty_name_shows_error(tmp_path):
    at = saved_app(tmp_path)
    click(at, "sv_save")
    assert MSG_EMPTY_NAME in [error.value for error in at.error]
    assert json_files(tmp_path) == []


def test_save_with_invalid_market_writes_nothing(tmp_path):
    at = saved_app(tmp_path)
    at.number_input(key="spot").set_value(0.0).run()
    type_name(at, "Mercado malo")
    click(at, "sv_save")
    assert not at.exception
    assert any("spot" in error.value.lower() or "precio" in error.value.lower() for error in at.tabs[BUILDER].error)
    assert json_files(tmp_path) == []


def test_duplicate_name_without_overwrite_warns_and_keeps_file(tmp_path):
    at = saved_app(tmp_path)
    type_name(at, "Repetida")
    click(at, "sv_save")
    before = (folder_of(tmp_path) / "repetida.json").read_bytes()

    at.number_input(key="spot").set_value(105.0).run()
    click(at, "sv_save")

    assert any("Ya existe" in text for text in tab_values(at, BUILDER, "warning"))
    assert (folder_of(tmp_path) / "repetida.json").read_bytes() == before
    assert json_files(tmp_path) == ["repetida.json"]


def test_duplicate_name_with_overwrite_replaces_file(tmp_path):
    at = saved_app(tmp_path)
    type_name(at, "Repetida")
    click(at, "sv_save")
    at.number_input(key="spot").set_value(105.0).run()
    at.checkbox(key="sv_overwrite_input").check().run()
    assert at.session_state["sv_overwrite"] is True
    click(at, "sv_save")

    assert json_files(tmp_path) == ["repetida.json"]
    doc = json.loads((folder_of(tmp_path) / "repetida.json").read_bytes())
    assert doc["market"]["spot"] == pytest.approx(105.0)


def test_download_button_disabled_until_valid(tmp_path):
    at = saved_app(tmp_path)
    button = download_button(at, "sv_download")
    assert button is not None
    assert button.proto.disabled is True
    assert MSG_SV_DOWNLOAD_DISABLED in tab_values(at, BUILDER, "caption")

    type_name(at, "Descargable")
    assert download_button(at, "sv_download").proto.disabled is False
    assert MSG_SV_DOWNLOAD_DISABLED not in tab_values(at, BUILDER, "caption")


# ---------------------------------------------------------------------------
# Bloque 5: "Mis estrategias" (lista, añadir a comparar, borrar)
# ---------------------------------------------------------------------------


def test_list_shows_saved_sorted_with_date_and_legs(tmp_path):
    save_strategy(tmp_path, "zeta", [leg(), leg(strike=110.0)])
    save_strategy(tmp_path, "Alfa")
    save_strategy(tmp_path, "beta", [leg(kind="stock", price=100.0)])
    at = saved_app(tmp_path)

    assert saved_names(at) == ["Alfa", "beta", "zeta"]
    captions = tab_values(at, SAVED, "caption")
    assert "Guardada el 2026-11-20, hoy · 1 pata" in captions
    assert "Guardada el 2026-11-20, hoy · 2 patas" in captions
    assert MSG_SV_EMPTY not in tab_values(at, SAVED, "info")
    assert not at.error and not at.warning


def test_corrupt_file_is_skipped_with_note(tmp_path):
    save_strategy(tmp_path, "Buena")
    (folder_of(tmp_path) / "rota.json").write_bytes(b"{no es json")
    at = saved_app(tmp_path)

    assert not at.exception
    assert saved_names(at) == ["Buena"]
    assert any("rota.json" in text for text in tab_values(at, SAVED, "caption"))
    assert not at.error and not at.warning


def test_widget_keys_derive_from_slug_and_are_stable(tmp_path):
    slug = save_strategy(tmp_path, "Iron Condor SPY")
    at = saved_app(tmp_path)
    keys = {f"sv_compare_{slug}", f"sv_delete_{slug}"}
    assert keys <= {button.key for button in at.button}
    assert download_button(at, f"sv_download_{slug}") is not None
    at.run()
    assert keys <= {button.key for button in at.button}


def test_saved_download_button_has_file_bytes(tmp_path):
    slug = save_strategy(tmp_path, "Descarga")
    at = saved_app(tmp_path)
    button = download_button(at, f"sv_download_{slug}")
    assert button.proto.disabled is False


def test_add_to_compare_updates_both_keys(tmp_path):
    slug = save_strategy(tmp_path, "Para comparar")
    at = saved_app(tmp_path)
    click(at, f"sv_compare_{slug}")

    assert not at.exception
    assert at.session_state["cmp_selected"] == [slug]
    assert at.multiselect(key="cmp_selected_input").value == [slug]
    assert any("comparación" in text for text in tab_values(at, SAVED, "success"))

    click(at, f"sv_compare_{slug}")  # no duplica
    assert at.session_state["cmp_selected"] == [slug]


def test_fourth_saved_strategy_is_rejected(tmp_path):
    slugs = [save_strategy(tmp_path, f"Estrategia {n}") for n in range(4)]
    at = saved_app(tmp_path)
    for slug in slugs[:3]:
        click(at, f"sv_compare_{slug}")
    click(at, f"sv_compare_{slugs[3]}")

    assert at.session_state["cmp_selected"] == slugs[:3]
    assert at.multiselect(key="cmp_selected_input").value == slugs[:3]
    assert MSG_MAX in tab_values(at, SAVED, "warning")


def test_delete_asks_for_confirmation_and_cancel_keeps_file(tmp_path):
    slug = save_strategy(tmp_path, "Borrable")
    at = saved_app(tmp_path)
    click(at, f"sv_delete_{slug}")

    assert at.session_state["sv_confirm"] == slug
    assert MSG_SV_CONFIRM.format(name="Borrable") in tab_values(at, SAVED, "warning")
    assert json_files(tmp_path) == [f"{slug}.json"]

    click(at, "sv_confirm_no")
    assert at.session_state["sv_confirm"] is None
    assert json_files(tmp_path) == [f"{slug}.json"]
    assert not at.warning


def test_confirm_delete_removes_file_and_selection(tmp_path):
    slug = save_strategy(tmp_path, "Borrable")
    other = save_strategy(tmp_path, "Otra")
    at = saved_app(tmp_path)
    click(at, f"sv_compare_{slug}")
    click(at, f"sv_compare_{other}")
    click(at, f"sv_delete_{slug}")
    click(at, "sv_confirm_yes")

    assert not at.exception
    assert json_files(tmp_path) == [f"{other}.json"]
    assert at.session_state["cmp_selected"] == [other]
    assert at.multiselect(key="cmp_selected_input").value == [other]
    assert saved_names(at) == ["Otra"]
    assert any("borrada" in text for text in tab_values(at, SAVED, "success"))
