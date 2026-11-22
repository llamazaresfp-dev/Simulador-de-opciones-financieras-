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
    """La pestaña Backtest (la última)."""
    return at.tabs[5]


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


def test_backtest_is_the_last_tab(tmp_path):
    at = data_app(tmp_path)
    assert not at.exception
    assert [tab.label for tab in at.tabs][5] == BACKTEST_TAB
    assert len(at.tabs) == 6


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


# ---------------------------------------------------------------------------
# Bloque 10: "Calcular", gráficos, tabla, avisos y caché de sesión
# ---------------------------------------------------------------------------

import json  # noqa: E402
import re  # noqa: E402

from datos import covers  # noqa: E402
from opciones.calibration import calibration_bins  # noqa: E402
from opciones.validation import MSG_NOT_ADVICE  # noqa: E402

NAN_RE = re.compile(r"\bnan\b|\binf\b", re.IGNORECASE)


@pytest.fixture
def run_spy(monkeypatch):
    """Cuenta las llamadas a run_backtest hechas desde la pestaña."""
    calls = []
    real = ui_backtest.run_backtest

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(ui_backtest, "run_backtest", spy)
    return calls


def run_click(at: AppTest) -> AppTest:
    """Pulsa "Calcular"."""
    at.button(key="bt_run").click().run()
    return at


def ready_app(tmp_path, provider=None, years=3, step=20) -> tuple[AppTest, FakeProvider]:
    """SPY con histórico cargado y paso grande (cálculo rápido)."""
    at, provider = spy_app(tmp_path, provider, years=years)
    set_param(at, "bt_step", step)
    load_history_click(at)
    return at, provider


def tab_charts(at: AppTest) -> list[dict]:
    """Figuras plotly de la pestaña Backtest (como diccionarios)."""
    return [json.loads(chart.proto.spec) for chart in backtest_tab(at).get("plotly_chart")]


def all_tab_texts(at: AppTest) -> list[str]:
    texts = []
    for kind in ("caption", "info", "warning", "markdown"):
        texts += tab_texts(at, kind)
    texts += [metric.value for metric in backtest_tab(at).metric]
    for frame in backtest_tab(at).dataframe:
        texts += [str(value) for value in frame.value.to_numpy().ravel()]
    return texts


def test_run_without_history_warns(tmp_path, run_spy):
    at, _ = spy_app(tmp_path)
    run_click(at)
    assert ui_backtest.MSG_BT_NEED_HISTORY in tab_texts(at, "warning")
    assert at.session_state["bt_result"] is None
    assert run_spy == []


def test_run_with_more_years_than_loaded_asks_to_reload(tmp_path, run_spy):
    at, provider = ready_app(tmp_path, years=3)
    set_param(at, "bt_years", 8)
    run_click(at)
    expected = "El histórico cargado no cubre 8 años: pulsa «Cargar histórico»"
    assert ui_backtest.MSG_BT_NOT_COVERED.format(years=8) == expected
    assert expected in tab_texts(at, "warning")
    assert at.session_state["bt_result"] is None
    assert run_spy == []

    # Con menos años sí calcula, sin avisar de cobertura.
    set_param(at, "bt_years", 2)
    run_click(at)
    assert len(run_spy) == 1
    assert at.session_state["bt_result"] is not None
    assert expected not in tab_texts(at, "warning")

    # Cargar con 8 y calcular: calcula.
    set_param(at, "bt_years", 8)
    load_history_click(at)
    run_click(at)
    assert len(run_spy) == 2
    assert not any("no cubre" in text for text in tab_texts(at, "warning"))


def test_run_one_day_after_load_is_still_covered(tmp_path, run_spy):
    """Mismo reloj inyectado en ambos lados; un día después sigue cubierto (E-7)."""
    at, _ = ready_app(tmp_path, years=3)
    later = FIXED_NOW + timedelta(days=1)
    at.session_state["clock"] = lambda: later
    run_click(at)
    assert len(run_spy) == 1
    assert not any("no cubre" in text for text in tab_texts(at, "warning"))


def test_same_day_requested_start_equality_covers():
    need = start_for_years(TODAY, 3)
    # Primer dato muy posterior, pero se pidió justo ese inicio: cubre.
    assert covers((TODAY - timedelta(days=30)).isoformat(), need, need)


def test_short_source_computes_with_short_warning_only(tmp_path, run_spy):
    provider = FakeProvider(today=FIXED_NOW, history_years=3)
    at, _ = ready_app(tmp_path, provider, years=5)
    run_click(at)
    warnings = tab_texts(at, "warning")
    assert not any("no cubre" in text for text in warnings)
    assert any("solo permite analizar" in text for text in warnings)
    assert len(run_spy) == 1
    assert at.session_state["bt_result"] is not None


def test_run_shows_figures_table_metrics_and_notices(tmp_path, run_spy):
    at, _ = ready_app(tmp_path, years=3)
    assert any(text.startswith("≈ ") and " fechas, ~" in text for text in tab_texts(at, "caption"))
    run_click(at)
    assert not at.exception

    stored = at.session_state["bt_result"]
    assert set(stored) >= {"key", "result"}
    assert stored["result"].n > 0

    charts = tab_charts(at)
    assert len(charts) == 2
    reliability = charts[0]["data"]
    assert any(trace.get("x") == [0, 1] and trace.get("y") == [0, 1] for trace in reliability)
    assert any("error_y" in trace for trace in reliability)

    frames = backtest_tab(at).dataframe
    assert len(frames[0].value) == 10
    labels = [metric.label for metric in backtest_tab(at).metric]
    assert {"Brier", "Casos (N)", "N efectivo"} <= set(labels)

    texts = all_tab_texts(at)
    for message in (
        ui_backtest.MSG_BT_REALIZED_VOL,
        ui_backtest.MSG_BT_AMERICAN,
        ui_backtest.MSG_BT_Q,
        ui_backtest.MSG_BT_WHAT,
        ui_backtest.MSG_BT_OVERLAP,
        ui_backtest.MSG_BT_TAILS,
        MSG_NOT_ADVICE,
    ):
        assert message in texts, message
    assert "no rentabilidad real" in ui_backtest.MSG_BT_WHAT
    assert "colas gordas del modelo + ruido de volatilidad" in ui_backtest.MSG_BT_TAILS
    assert not any(NAN_RE.search(text) for text in texts)
    assert not backtest_tab(at).error


def test_mu_line_adds_second_series(tmp_path, run_spy):
    at, _ = ready_app(tmp_path, years=3)
    run_click(at)
    plain = [t for t in tab_charts(at)[0]["data"] if "error_y" in t]
    assert len(plain) == 1
    set_param(at, "bt_use_mu", True)
    run_click(at)
    assert run_spy[-1]["with_mu"] is True
    with_mu = [t for t in tab_charts(at)[0]["data"] if "error_y" in t]
    assert len(with_mu) == 2


def test_result_reused_while_params_unchanged(tmp_path, run_spy):
    at, provider = ready_app(tmp_path, years=3)
    run_click(at)
    calls_before = len(provider.history_calls)
    at.run()
    at.run()
    assert len(run_spy) == 1
    assert len(provider.history_calls) == calls_before
    assert len(tab_charts(at)) == 2


def test_param_change_hides_old_result(tmp_path, run_spy):
    at, _ = ready_app(tmp_path, years=3)
    run_click(at)
    set_param(at, "bt_horizon", 45)
    assert ui_backtest.MSG_BT_PARAMS_CHANGED in tab_texts(at, "info")
    assert tab_charts(at) == []
    assert not backtest_tab(at).metric


def test_commission_change_invalidates_result(tmp_path, run_spy):
    at, _ = ready_app(tmp_path, years=3)
    run_click(at)
    at.number_input(key="per_contract_input").set_value(1.0).run()
    assert ui_backtest.MSG_BT_PARAMS_CHANGED in tab_texts(at, "info")
    # Sin comisiones, cambiar las de Ajustes no importa.
    set_param(at, "bt_fees", False)
    run_click(at)
    at.number_input(key="per_contract_input").set_value(2.0).run()
    assert ui_backtest.MSG_BT_PARAMS_CHANGED not in tab_texts(at, "info")


def test_reloading_different_history_invalidates_result(tmp_path, run_spy):
    at, _ = ready_app(tmp_path, years=3)
    run_click(at)
    set_param(at, "bt_years", 5)
    load_history_click(at)  # más años: otra descarga, otra huella
    set_param(at, "bt_years", 3)
    assert ui_backtest.MSG_BT_PARAMS_CHANGED in tab_texts(at, "info")


def test_few_cases_marked_in_table(tmp_path, run_spy):
    at, _ = ready_app(tmp_path, years=3)
    run_click(at)
    table = backtest_tab(at).dataframe[0].value
    notes = list(table["Nota"])
    rows = calibration_bins(
        at.session_state["bt_result"]["result"].pop, at.session_state["bt_result"]["result"].win
    )
    assert notes.count("pocos casos") == sum(row.few for row in rows)
    assert notes.count("sin casos") == sum(row.empty for row in rows)


def test_reliability_figure_pure():
    rows = calibration_bins([0.05, 0.55] + [0.75] * 12, [0, 1] + [1] * 9 + [0] * 3)
    figure = ui_backtest.build_reliability_figure(rows)
    data = figure.to_dict()["data"]
    diagonal = [t for t in data if list(t["x"]) == [0, 1] and list(t["y"]) == [0, 1]]
    assert len(diagonal) == 1
    points = [t for t in data if t.get("error_y")]
    assert len(points) == 1
    # Tramos con pocos casos: marcador hueco.
    symbols = list(points[0]["marker"]["symbol"])
    assert symbols.count("circle-open") == 2
    assert len(symbols) == 3


def test_tails_figure_pure():
    import numpy as np

    z = np.random.default_rng(1).standard_normal(500)
    figure = ui_backtest.build_tails_figure(z)
    kinds = [trace["type"] for trace in figure.to_dict()["data"]]
    assert kinds == ["histogram", "scatter"]
