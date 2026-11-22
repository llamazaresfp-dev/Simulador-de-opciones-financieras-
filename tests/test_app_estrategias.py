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
from estrategias.serialize import (
    MAX_BYTES,
    MSG_EMPTY_NAME,
    MSG_NO_LEGS,
    dumps_strategy,
    prepare_document,
    strategy_to_dict,
)
from opciones import CommissionSettings, Market, default_premium
from tests.test_app_smoke import APP_PATH, FIXED_NOW, choose_ticker, load
from ui_estrategias import (
    MSG_SV_CONFIRM,
    MSG_SV_DOWNLOAD_DISABLED,
    MSG_SV_EMPTY,
    MSG_SV_UPLOAD_FAILED,
    import_uploaded,
)

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


# ---------------------------------------------------------------------------
# Bloque 6: abrir (con su mercado / solo las patas), avisos y subida
# ---------------------------------------------------------------------------


# Mercado y comisiones guardados distintos de los de arranque de la app.
SAVED_MARKET = Market("ETF", 250.0, 0.25, 45, 0.0412, 0.013, "black_scholes")
SAVED_SETTINGS = CommissionSettings(per_contract=1.25, index_surcharge=0.5, include_close=False)
MARKET_LEG = leg(
    kind="put",
    side=-1,
    quantity=2.0,
    strike=240.0,
    price=3.1,
    manual=True,
    premium_source="mercado",
    bid=3.0,
    ask=3.2,
    expiry="2026-12-18",
)
MIXED_LEGS = [
    leg(kind="call", side=1, quantity=1.0, strike=260.0, price=3.33, manual=True),
    leg(kind="call", side=-1, quantity=1.0, strike=270.0, price=1.0, manual=False),
    MARKET_LEG,
]
STALE_NOTICE = "Pata 3: cotización guardada el 2026-11-20, puede estar desfasada."


def save_mixed(tmp_path, name="Mixta ETF") -> str:
    return save_strategy(tmp_path, name, MIXED_LEGS, SAVED_MARKET, SAVED_SETTINGS, ticker="SPY")


def open_saved(at: AppTest, slug: str, with_market: bool) -> AppTest:
    prefix = "sv_open_mkt_" if with_market else "sv_open_legs_"
    return click(at, f"{prefix}{slug}")


def current_market(at: AppTest) -> Market:
    state = at.session_state
    return Market(
        state["underlying"],
        state["spot"],
        state["vol_pct"] / 100,
        state["days"],
        state["rate_pct"] / 100,
        state["q_pct"] / 100,
        state["pricing_model"],
    )


def test_open_with_market_restores_state_and_widgets(tmp_path):
    slug = save_mixed(tmp_path)
    at = saved_app(tmp_path)
    open_saved(at, slug, with_market=True)

    assert not at.exception
    state = at.session_state
    assert state["main_tab"] == "🛠️ Constructor"
    assert (state["underlying"], state["spot"], state["days"]) == ("ETF", 250.0, 45)
    assert state["vol_pct"] == 25.0  # round(0.25 * 100, 10), sin ruido
    assert state["rate_pct"] == 4.12
    assert state["q_pct"] == 1.3
    assert state["pricing_model"] == "black_scholes"
    assert (state["per_contract"], state["index_surcharge"], state["include_close"]) == (1.25, 0.5, False)
    # Los widgets muestran lo cargado (DD-20), no solo las claves simples.
    assert at.selectbox(key="underlying").value == "ETF"
    assert at.number_input(key="spot").value == 250.0
    assert at.number_input(key="vol_pct").value == 25.0
    assert at.number_input(key="days").value == 45
    assert at.number_input(key="rate_pct").value == 4.12
    assert at.number_input(key="q_pct").value == 1.3
    assert at.radio(key="pricing_model_input").value == "black_scholes"
    assert at.number_input(key="per_contract_input").value == 1.25
    assert at.number_input(key="index_surcharge_input").value == 0.5
    assert at.checkbox(key="include_close_input").value is False
    assert at.text_input(key="sv_name_input").value == "Mixta ETF"
    assert at.checkbox(key="sv_overwrite_input").value is False
    legs = state["legs"]
    assert [(item["kind"], item["side"], item["quantity"], item["strike"]) for item in legs] == [
        ("call", 1, 1.0, 260.0),
        ("call", -1, 1.0, 270.0),
        ("put", -1, 2.0, 240.0),
    ]


def test_later_settings_edit_starts_from_loaded_values(tmp_path):
    slug = save_mixed(tmp_path)
    at = saved_app(tmp_path)
    open_saved(at, slug, with_market=True)
    at.number_input(key="index_surcharge_input").set_value(0.75).run()

    state = at.session_state
    assert state["index_surcharge"] == 0.75
    assert state["per_contract"] == 1.25
    assert state["include_close"] is False
    assert state["pricing_model"] == "black_scholes"


def test_open_legs_only_keeps_current_market_and_settings(tmp_path):
    slug = save_mixed(tmp_path)
    at = saved_app(tmp_path)
    at.number_input(key="spot").set_value(120.0).run()
    at.number_input(key="per_contract_input").set_value(1.0).run()
    open_saved(at, slug, with_market=False)

    assert not at.exception
    state = at.session_state
    assert (state["underlying"], state["spot"], state["vol_pct"], state["days"]) == ("Acción", 120.0, 20.0, 30)
    assert (state["per_contract"], state["pricing_model"]) == (1.0, "binomial")
    assert at.number_input(key="spot").value == 120.0
    assert at.number_input(key="per_contract_input").value == 1.0
    assert at.radio(key="pricing_model_input").value == "binomial"
    assert at.text_input(key="sv_name_input").value == "Mixta ETF"
    assert len(state["legs"]) == 3
    # Prima automática recalculada con el mercado ACTUAL (spot 120, binomial).
    auto = state["legs"][1]
    assert auto["premium_manual"] is False
    assert auto["price"] == pytest.approx(default_premium("call", current_market(at), 270.0))


def test_manual_premium_is_kept(tmp_path):
    slug = save_mixed(tmp_path)
    at = saved_app(tmp_path)
    open_saved(at, slug, with_market=False)
    manual = at.session_state["legs"][0]
    assert manual["premium_manual"] is True
    assert manual["price"] == pytest.approx(3.33)


def test_market_leg_becomes_manual_with_stale_quote_notice(tmp_path):
    slug = save_mixed(tmp_path)
    at = saved_app(tmp_path)
    open_saved(at, slug, with_market=True)

    market_leg = at.session_state["legs"][2]
    assert market_leg["premium_manual"] is True
    assert market_leg["premium_source"] is None
    assert (market_leg["bid"], market_leg["ask"], market_leg["expiry"], market_leg["iv_yahoo"]) == (
        None,
        None,
        None,
        None,
    )
    assert market_leg["price"] == pytest.approx(3.1)
    assert at.session_state["open_notices"] == [STALE_NOTICE]
    assert STALE_NOTICE in tab_values(at, BUILDER, "info")


def test_stale_notice_cleared_when_removing_leg_or_opening_another(tmp_path):
    slug = save_mixed(tmp_path)
    other = save_strategy(tmp_path, "Sin mercado")
    at = saved_app(tmp_path)
    open_saved(at, slug, with_market=True)
    open_saved(at, other, with_market=False)
    assert at.session_state["open_notices"] == []

    open_saved(at, slug, with_market=True)
    leg_id = at.session_state["legs"][0]["id"]
    click(at, f"leg_{leg_id}_remove")
    assert at.session_state["open_notices"] == []
    assert STALE_NOTICE not in tab_values(at, BUILDER, "info")


def test_open_clears_loaded_data_and_backtest(tmp_path):
    slug = save_mixed(tmp_path)
    at = saved_app(tmp_path)
    choose_ticker(at, "ETF", "SPY")
    load(at)
    assert at.session_state["snapshot"] is not None
    at.session_state["bt_history"] = "algo cargado"
    open_saved(at, slug, with_market=False)

    state = at.session_state
    assert not at.exception
    assert state["ticker_choice"] == "Entrada manual"
    assert state["snapshot"] is None
    assert state["expiry_choice"] is None
    assert state["bt_history"] is None


def test_new_leg_ids_are_unique_and_open_is_idempotent(tmp_path):
    slug = save_mixed(tmp_path)
    at = saved_app(tmp_path)
    first_id = at.session_state["next_leg_id"]
    open_saved(at, slug, with_market=True)
    ids = [item["id"] for item in at.session_state["legs"]]
    assert len(set(ids)) == 3 and min(ids) >= first_id
    snapshot = [(item["kind"], item["strike"], item["price"]) for item in at.session_state["legs"]]

    open_saved(at, slug, with_market=True)
    assert not at.exception
    again = [(item["kind"], item["strike"], item["price"]) for item in at.session_state["legs"]]
    assert again == snapshot
    assert at.session_state["next_leg_id"] == first_id + 6


def test_open_resets_overwrite_checkbox(tmp_path):
    slug = save_mixed(tmp_path)
    at = saved_app(tmp_path)
    at.checkbox(key="sv_overwrite_input").check().run()
    open_saved(at, slug, with_market=False)
    assert at.session_state["sv_overwrite"] is False
    assert at.checkbox(key="sv_overwrite_input").value is False


@pytest.mark.parametrize("failure", ["missing", "raises"])
def test_open_failure_shows_error_and_keeps_state(tmp_path, monkeypatch, failure):
    slug = save_mixed(tmp_path)
    at = saved_app(tmp_path)
    before = [dict(item) for item in at.session_state["legs"]]

    def fake_read(*args, **kwargs):
        if failure == "raises":
            raise OverflowError("motor")
        return None, "No existe la estrategia."

    monkeypatch.setattr(store, "read_strategy", fake_read)
    open_saved(at, slug, with_market=True)

    assert not at.exception
    errors = tab_values(at, SAVED, "error")
    assert any(text.startswith("No se pudo abrir «") for text in errors)
    assert at.session_state["legs"] == before
    assert at.session_state["spot"] == 100.0
    assert at.session_state["main_tab"] == "📊 Catálogo"


def hostile_document(path: list, value) -> bytes:
    """Documento válido con un campo cambiado por un valor hostil (JSON a mano)."""
    doc = strategy_to_dict([leg()], DEFAULT_MARKET, DEFAULT_SETTINGS, "Hostil", FIXED_NOW)
    target = doc
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    text = json.dumps(doc).replace('"__INF__"', "1e999")
    return text.encode("utf-8")


HOSTILE_CASES = [
    (["legs", 0, "strike"], 1e300),
    (["market", "spot"], 1e300),
    (["market", "spot"], 1e-300),
    (["legs", 0, "quantity"], 1e308),
    (["market", "rate"], -1e6),
    (["legs", 0, "price"], "__INF__"),
]


@pytest.mark.parametrize(("path", "value"), HOSTILE_CASES)
def test_hostile_file_in_folder_is_skipped_never_opened(tmp_path, path, value):
    save_strategy(tmp_path, "Buena")
    (folder_of(tmp_path) / "hostil.json").write_bytes(hostile_document(path, value))
    at = saved_app(tmp_path)

    assert not at.exception
    assert saved_names(at) == ["Buena"]
    assert any("hostil.json" in text for text in tab_values(at, SAVED, "caption"))
    assert not any(str(button.key).endswith("_hostil") for button in at.button)
    assert not at.error and not at.warning


# --- Subida de JSON: función pura (la misma que usa el botón) ---


def valid_bytes(name="Subida") -> bytes:
    raw, errors = prepare_document([leg()], DEFAULT_MARKET, DEFAULT_SETTINGS, name, FIXED_NOW)
    assert errors == []
    return raw


def test_import_uploaded_valid_saves_exact_bytes(tmp_path):
    raw = valid_bytes()
    ok, message = import_uploaded(raw, folder_of(tmp_path))
    assert ok and "guardada" in message
    assert (folder_of(tmp_path) / "subida.json").read_bytes() == raw


@pytest.mark.parametrize(
    "raw",
    [
        b"{corrupto",
        b" " * (MAX_BYTES + 1),
        valid_bytes().replace(b'"schema_version": 1', b'"schema_version": 2'),
        hostile_document(["legs", 0, "strike"], 1e300),
        hostile_document(["market", "spot"], "__INF__"),
        hostile_document(["name"], "a\u0000b"),
        None,
    ],
    ids=["corrupto", "grande", "version-2", "strike-1e300", "spot-1e999", "nombre-nul", "none"],
)
def test_import_uploaded_rejects_bad_bytes(tmp_path, raw):
    ok, message = import_uploaded(raw, folder_of(tmp_path))
    assert ok is False and message
    assert json_files(tmp_path) == []


def test_import_uploaded_path_traversal_name_stays_inside(tmp_path):
    raw = valid_bytes("../../fuera")
    ok, _message = import_uploaded(raw, folder_of(tmp_path))
    assert ok
    assert json_files(tmp_path) == ["fuera.json"]
    assert not (tmp_path.parent / "fuera.json").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["estrategias"]


def test_import_uploaded_existing_name_needs_overwrite(tmp_path):
    raw = valid_bytes()
    assert import_uploaded(raw, folder_of(tmp_path))[0]
    ok, message = import_uploaded(raw, folder_of(tmp_path))
    assert ok is False and "Ya existe" in message
    assert import_uploaded(raw, folder_of(tmp_path), overwrite=True)[0]
    assert json_files(tmp_path) == ["subida.json"]


def test_import_uploaded_respects_limit_of_100(tmp_path):
    for number in range(100):
        assert import_uploaded(valid_bytes(f"E{number}"), folder_of(tmp_path))[0]
    ok, message = import_uploaded(valid_bytes("La 101"), folder_of(tmp_path))
    assert ok is False and "100" in message
    assert len(json_files(tmp_path)) == 100


def test_import_uploaded_never_raises(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("disco")

    monkeypatch.setattr(store, "save_document", boom)
    assert import_uploaded(valid_bytes(), folder_of(tmp_path)) == (False, MSG_SV_UPLOAD_FAILED)


# --- Subida de JSON: widget real (AppTest 1.67 sí soporta st.file_uploader) ---


def test_upload_button_without_file_does_nothing(tmp_path):
    at = saved_app(tmp_path)
    click(at, "sv_upload_save")
    assert not at.exception
    assert not at.error and not at.success
    assert json_files(tmp_path) == []


def test_upload_widget_saves_and_lists(tmp_path):
    at = saved_app(tmp_path)
    at.file_uploader(key="sv_upload").set_value(("mia.json", valid_bytes("Subida"), "application/json")).run()
    click(at, "sv_upload_save")

    assert not at.exception
    assert json_files(tmp_path) == ["subida.json"]
    assert saved_names(at) == ["Subida"]
    assert any("guardada" in text for text in tab_values(at, SAVED, "success"))


def test_upload_widget_rejects_corrupt_file(tmp_path):
    at = saved_app(tmp_path)
    at.file_uploader(key="sv_upload").set_value(("rota.json", b"{roto", "application/json")).run()
    click(at, "sv_upload_save")

    assert not at.exception
    assert any("No se pudo guardar" in text for text in tab_values(at, SAVED, "error"))
    assert json_files(tmp_path) == []
