"""Tests de la pestaña "Backtest" (Etapa C2, bloques 9 y 10) con AppTest.

Siempre sin red: proveedor falso inyectado en session_state, caché en
tmp_path y reloj fijo (helpers de tests/test_app_smoke.py). Nunca se usa
el `.cache_datos/` real ni se construye YahooProvider sin pulsar un botón.
"""

from datetime import timedelta

import pytest
from streamlit.testing.v1 import AppTest

import datos.yahoo
import ui_backtest
from datos import FakeProvider, NetworkError, start_for_years
from datos.errors import MSG_NETWORK
from datos.history_service import MSG_RATE_HISTORY_MISSING
from tests.test_app_smoke import APP_PATH, FIXED_NOW, choose_ticker, data_app

BACKTEST_TAB = "📈 Backtest"
TODAY = FIXED_NOW.date()


# ---------------------------------------------------------------------------
# Ayudantes
# ---------------------------------------------------------------------------


def backtest_tab(at: AppTest):
    """La pestaña Backtest (la 4.ª)."""
    return at.tabs[3]


def set_param(at: AppTest, field: str, value) -> AppTest:
    """Cambia un control de la pestaña (su widget `bt_*_input`)."""
    if isinstance(value, bool):
        at.checkbox(key=f"{field}_input").set_value(value).run()
    else:
        at.number_input(key=f"{field}_input").set_value(value).run()
    return at


def load_history_click(at: AppTest) -> AppTest:
    """Pulsa "Cargar histórico"."""
    at.button(key="bt_load").click().run()
    return at


def calls_for(provider: FakeProvider, symbol: str) -> list:
    return [call for call in provider.history_calls if call[0] == symbol]


def tab_texts(at: AppTest, kind: str) -> list[str]:
    return [element.value for element in getattr(backtest_tab(at), kind)]


def spy_app(tmp_path, provider=None, years=None) -> tuple[AppTest, FakeProvider]:
    """App con SPY elegido y un proveedor falso (opcionalmente con años)."""
    provider = provider or FakeProvider(today=FIXED_NOW)
    at = data_app(tmp_path, provider)
    choose_ticker(at, "ETF", "SPY")
    if years is not None:
        set_param(at, "bt_years", years)
    return at, provider


class SpyYahoo:
    """Sustituto de YahooProvider que anota cada construcción y falla."""

    created = []

    def __init__(self, *args, **kwargs):
        SpyYahoo.created.append((args, kwargs))
        raise RuntimeError("YahooProvider no debe construirse en los tests")


@pytest.fixture
def yahoo_spy(monkeypatch):
    SpyYahoo.created = []
    monkeypatch.setattr(datos.yahoo, "YahooProvider", SpyYahoo)
    return SpyYahoo.created


# ---------------------------------------------------------------------------
# Bloque 9: pestaña, controles, "Cargar histórico"
# ---------------------------------------------------------------------------


def test_backtest_is_the_fourth_tab(tmp_path):
    at = data_app(tmp_path)
    assert not at.exception
    assert [tab.label for tab in at.tabs][3] == BACKTEST_TAB
    assert len(at.tabs) == 4


def test_default_values_of_controls(tmp_path):
    at = data_app(tmp_path)
    state = at.session_state
    assert state["bt_template"] == "iron_condor"
    assert (state["bt_horizon"], state["bt_window"], state["bt_step"], state["bt_years"]) == (
        30,
        30,
        5,
        10,
    )
    assert state["bt_fees"] is True
    assert state["bt_use_mu"] is False
    assert at.selectbox(key="bt_template_input").value == "iron_condor"
    assert at.checkbox(key="bt_fees_input").value is True
    assert at.checkbox(key="bt_use_mu_input").value is False


@pytest.mark.parametrize(
    "field, low, high, default",
    [
        ("bt_horizon", 7, 120, 30),
        ("bt_window", 10, 250, 30),
        ("bt_step", 1, 20, 5),
        ("bt_years", 1, 15, 10),
    ],
)
def test_number_inputs_have_ranges(tmp_path, field, low, high, default):
    at = data_app(tmp_path)
    widget = at.number_input(key=f"{field}_input")
    assert widget.proto.has_min and widget.proto.has_max
    assert widget.proto.min == low
    assert widget.proto.max == high
    assert widget.value == default
    # Enteros (sin decimales).
    assert isinstance(widget.value, int)


def test_template_labels_are_names(tmp_path):
    at = data_app(tmp_path)
    box = at.selectbox(key="bt_template_input")
    assert "Iron condor (dos spreads vendidos)" in box.options


def test_param_widget_copies_to_simple_entry(tmp_path):
    at = data_app(tmp_path)
    set_param(at, "bt_horizon", 45)
    set_param(at, "bt_use_mu", True)
    assert at.session_state["bt_horizon"] == 45
    assert at.session_state["bt_use_mu"] is True


def test_years_caption_present(tmp_path):
    at = data_app(tmp_path)
    assert ui_backtest.MSG_BT_YEARS_CAPTION in tab_texts(at, "caption")
    assert "cambiar a más años obliga a volver a descargar" in ui_backtest.MSG_BT_YEARS_CAPTION


def test_default_tab_is_inert_no_warning_error_or_chart(tmp_path):
    provider = FakeProvider(today=FIXED_NOW)
    at = data_app(tmp_path, provider)
    tab = backtest_tab(at)
    assert not tab.warning and not tab.error
    assert not tab.get("plotly_chart")
    assert provider.history_calls == []
    assert at.session_state["bt_history"] is None
    assert at.session_state["bt_result"] is None


def test_no_download_without_button_even_with_ticker(tmp_path):
    at, provider = spy_app(tmp_path)
    set_param(at, "bt_years", 4)
    assert provider.history_calls == []
    assert at.session_state["bt_history"] is None
    assert at.session_state["bt_result"] is None
    assert not backtest_tab(at).warning and not backtest_tab(at).error
    assert not list(tmp_path.glob("history/*"))


def test_yahoo_never_built_without_click_bare_app(yahoo_spy):
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.selectbox(key="underlying").set_value("ETF").run()
    at.selectbox(key="ticker_choice").set_value("SPY").run()
    set_param(at, "bt_years", 3)
    assert not at.exception
    assert yahoo_spy == []


def test_yahoo_never_built_without_click_data_app(tmp_path, yahoo_spy):
    at, provider = spy_app(tmp_path)
    assert yahoo_spy == []
    load_history_click(at)
    # Con proveedor inyectado tampoco: se usa el falso.
    assert yahoo_spy == []
    assert calls_for(provider, "SPY")


def test_click_builds_provider_lazily_and_fails_softly(yahoo_spy):
    """Sin proveedor inyectado, el clic es lo que construye Yahoo (el espía falla)."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.selectbox(key="underlying").set_value("ETF").run()
    at.selectbox(key="ticker_choice").set_value("SPY").run()
    assert yahoo_spy == []
    at.button(key="bt_load").click().run()
    assert len(yahoo_spy) == 1
    assert not at.exception
    assert ui_backtest.MSG_BT_NO_PROVIDER in tab_texts(at, "error")
    assert at.session_state["bt_history"] is None


def test_manual_entry_shows_info_and_disabled_buttons(tmp_path):
    at = data_app(tmp_path)
    assert ui_backtest.MSG_BT_MANUAL in tab_texts(at, "info")
    assert at.button(key="bt_load").disabled
    assert at.button(key="bt_run").disabled


def test_load_requests_years_plus_one_and_reuses_cache(tmp_path):
    at, provider = spy_app(tmp_path, years=5)
    load_history_click(at)

    assert not at.exception
    end = TODAY + timedelta(days=1)
    assert calls_for(provider, "SPY") == [("SPY", start_for_years(TODAY, 5), end)]
    assert start_for_years(TODAY, 5) == TODAY.replace(year=TODAY.year - 6)
    assert calls_for(provider, "^IRX") == [("^IRX", start_for_years(TODAY, 5), end)]
    loaded = at.session_state["bt_history"]
    assert loaded["ticker"] == "SPY"
    assert loaded["load"].source == "live"

    # Segunda pulsación con los mismos (o menos) años: caché, sin llamadas.
    load_history_click(at)
    set_param(at, "bt_years", 3)
    load_history_click(at)
    assert len(provider.history_calls) == 2

    # Más años: descarga nueva.
    set_param(at, "bt_years", 8)
    load_history_click(at)
    assert calls_for(provider, "SPY")[-1] == ("SPY", start_for_years(TODAY, 8), end)
    assert len(calls_for(provider, "SPY")) == 2


def test_load_shows_age_text(tmp_path):
    at, _provider = spy_app(tmp_path, years=2)
    load_history_click(at)
    texts = tab_texts(at, "caption")
    assert any(text.startswith("histórico cargado a las ") for text in texts)

    load_history_click(at)  # segunda vez: de la caché
    texts = tab_texts(at, "caption")
    assert any(text.startswith("histórico guardado hoy a las ") for text in texts)


def test_short_source_shows_real_years_warning(tmp_path):
    provider = FakeProvider(today=FIXED_NOW, history_years=3)
    at, _ = spy_app(tmp_path, provider, years=10)
    load_history_click(at)
    warnings = tab_texts(at, "warning")
    # 3 años de fuente − 1 de calentamiento ≈ 2,0 años analizables.
    assert any("solo permite analizar 2,0 años" in text for text in warnings), warnings


def test_ticker_change_clears_backtest_state(tmp_path):
    at, _ = spy_app(tmp_path, years=2)
    load_history_click(at)
    assert at.session_state["bt_history"] is not None
    at.session_state["bt_result"] = {"key": "x", "result": None}
    at.selectbox(key="ticker_choice").set_value("QQQ").run()
    assert at.session_state["bt_history"] is None
    assert at.session_state["bt_result"] is None


def test_underlying_change_clears_backtest_state(tmp_path):
    at, _ = spy_app(tmp_path, years=2)
    load_history_click(at)
    at.selectbox(key="underlying").set_value("Acción").run()
    assert at.session_state["bt_history"] is None


def test_loading_chain_data_keeps_backtest_history(tmp_path):
    """Pulsar "Cargar datos" (cadena de opciones) no borra el histórico."""
    at, _ = spy_app(tmp_path, years=2)
    load_history_click(at)
    at.button(key="load_data").click().run()
    assert at.session_state["bt_history"] is not None


def test_provider_error_without_cache_shows_spanish_error(tmp_path):
    provider = FakeProvider(today=FIXED_NOW, history_fail_symbols={"SPY": NetworkError()})
    at, _ = spy_app(tmp_path, provider, years=2)
    load_history_click(at)
    assert not at.exception
    errors = tab_texts(at, "error")
    assert any(MSG_NETWORK in text for text in errors)
    assert at.session_state["bt_history"] is None


def test_provider_error_with_cache_uses_cache(tmp_path):
    at, _ = spy_app(tmp_path, years=2)
    load_history_click(at)
    failing = FakeProvider(today=FIXED_NOW, history_fail_symbols={"SPY": NetworkError()})
    at.session_state["data_provider"] = failing
    set_param(at, "bt_years", 6)  # pide más años: no cubre, intenta descargar
    load_history_click(at)
    assert not at.exception
    assert calls_for(failing, "SPY")
    assert at.session_state["bt_history"]["load"].source == "cache"
    warnings = tab_texts(at, "warning")
    assert MSG_NETWORK in warnings
    assert not tab_texts(at, "error")


def test_gspc_network_error_does_not_fall_back_to_spx(tmp_path):
    provider = FakeProvider(today=FIXED_NOW, history_fail_symbols={"^GSPC": NetworkError()})
    at = data_app(tmp_path, provider)
    choose_ticker(at, "Índice", "SPX")
    set_param(at, "bt_years", 2)
    load_history_click(at)
    assert calls_for(provider, "^GSPC")
    assert not calls_for(provider, "^SPX")
    assert any(MSG_NETWORK in text for text in tab_texts(at, "error"))


def test_only_rate_failing_is_not_fatal(tmp_path):
    provider = FakeProvider(today=FIXED_NOW, history_fail_symbols={"^IRX": NetworkError()})
    at, _ = spy_app(tmp_path, provider, years=2)
    load_history_click(at)
    assert at.session_state["bt_history"] is not None
    assert at.session_state["bt_history"]["load"].rates is None
    assert MSG_RATE_HISTORY_MISSING in tab_texts(at, "warning")
    assert not tab_texts(at, "error")


class NoHistoryProvider:
    """Proveedor de C1 sin `get_history`."""

    def get_spot(self, ticker):
        return 100.0


def test_provider_without_history_message_only_after_click(tmp_path):
    at = data_app(tmp_path, NoHistoryProvider())
    choose_ticker(at, "ETF", "SPY")
    assert not at.exception
    assert not tab_texts(at, "error")
    load_history_click(at)
    assert not at.exception
    assert ui_backtest.MSG_BT_NO_PROVIDER in tab_texts(at, "error")


def test_default_app_has_four_tabs_and_no_backtest_noise():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    assert not at.warning and not at.error
    assert not backtest_tab(at).get("plotly_chart")
