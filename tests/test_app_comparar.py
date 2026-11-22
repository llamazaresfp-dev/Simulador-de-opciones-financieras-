"""Tests de la pestaña "⚖️ Comparar" (Etapa D, bloque 7) con AppTest.

Siempre con la carpeta de estrategias en tmp_path, proveedor falso, caché
en tmp_path y reloj fijo (sin red ni carpetas reales). Las curvas «hoy» y
las griegas solo se calculan con la casilla `cmp_heavy_input`.
"""

import base64
import json
import time

import numpy as np
import plotly.graph_objects as go
import pytest
from streamlit.testing.v1 import AppTest

import estrategias.compare
from estrategias import compare
from estrategias.compare import MSG_MAX
from opciones import CommissionSettings, Leg, Market, SimulationSettings
from opciones import binomial
from opciones.payoff import price_grid
from tests.test_app_estrategias import (
    DEFAULT_MARKET,
    DEFAULT_SETTINGS,
    click,
    folder_of,
    leg,
    save_strategy,
    saved_app,
    tab_values,
)
from ui_comparar import (
    BUILDER_LABEL,
    MSG_CMP_FAILED,
    MSG_CMP_GUIDE,
    MSG_CMP_MARKET_INVALID,
    MSG_CMP_SAME_MARKET,
    SERIES_STYLES,
    build_compare_figure,
    series_style,
)

COMPARE = 2

# Iron condor con primas manuales (cifras de referencia calculadas a mano).
CONDOR_LEGS = [
    leg(kind="put", side=1, strike=90.0, price=1.0, manual=True),
    leg(kind="put", side=-1, strike=95.0, price=2.0, manual=True),
    leg(kind="call", side=-1, strike=105.0, price=2.0, manual=True),
    leg(kind="call", side=1, strike=110.0, price=1.0, manual=True),
]
# Call comprada con prima manual 2,50.
CALL_LEGS = [leg(kind="call", side=1, strike=100.0, price=2.5, manual=True)]
# Iron condors con primas automáticas (para el tiempo con binomial en frío).
AUTO_CONDORS = [
    [
        leg(kind="put", side=1, strike=80.0 + shift),
        leg(kind="put", side=-1, strike=90.0 + shift),
        leg(kind="call", side=-1, strike=110.0 + shift),
        leg(kind="call", side=1, strike=120.0 + shift),
    ]
    for shift in (0.0, 2.5, 5.0, 7.5)
]


# ---------------------------------------------------------------------------
# Ayudantes
# ---------------------------------------------------------------------------


def select(at: AppTest, slugs: list[str]) -> AppTest:
    at.multiselect(key="cmp_selected_input").set_value(slugs).run()
    return at


def heavy(at: AppTest, value: bool = True) -> AppTest:
    at.checkbox(key="cmp_heavy_input").set_value(value).run()
    return at


def compare_charts(at: AppTest) -> list[dict]:
    return [json.loads(chart.proto.spec) for chart in at.tabs[COMPARE].get("plotly_chart")]


def decode(values) -> np.ndarray:
    """Valores de una traza del JSON de plotly (lista o array binario base64)."""
    if isinstance(values, dict):
        data = np.frombuffer(base64.b64decode(values["bdata"]), dtype=np.dtype(values["dtype"]))
        return data.astype(float)
    return np.array(values, dtype=float)


def traces(at: AppTest) -> list[dict]:
    charts = compare_charts(at)
    assert len(charts) == 1
    return charts[0]["data"]


def curve_names(at: AppTest) -> list[str]:
    return [trace["name"] for trace in traces(at) if trace.get("mode") == "lines"]


def table(at: AppTest):
    frames = at.tabs[COMPARE].dataframe
    assert len(frames) == 1
    return frames[0].value


def engine_legs(items: list[dict]) -> list[Leg]:
    return [
        Leg(item["kind"], item["side"], item["quantity"], item["strike"], item["price"]) for item in items
    ]


def set_builder_call(at: AppTest) -> None:
    """Deja en el Constructor la call manual de referencia (prima 2,50)."""
    leg_id = at.session_state["legs"][0]["id"]
    at.number_input(key=f"leg_{leg_id}_price").set_value(2.5).run()


class CallCounter:
    """Espía: cuenta las llamadas y delega en la función real."""

    def __init__(self, function):
        self.function = function
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.function(*args, **kwargs)


@pytest.fixture
def spies(monkeypatch):
    today = CallCounter(estrategias.compare.pnl_today)
    greeks = CallCounter(estrategias.compare.position_greeks)
    monkeypatch.setattr(estrategias.compare, "pnl_today", today)
    monkeypatch.setattr(estrategias.compare, "position_greeks", greeks)
    return today, greeks


def clear_binomial_caches() -> None:
    """Medición en frío: vacía las cachés del árbol binomial."""
    binomial._cached_price.cache_clear()
    binomial._cached_grid.cache_clear()
    binomial._cached_greeks.cache_clear()


# ---------------------------------------------------------------------------
# Sin selección / selector
# ---------------------------------------------------------------------------


def test_without_selection_shows_guide_and_no_chart(tmp_path):
    save_strategy(tmp_path, "Guardada")
    at = saved_app(tmp_path)
    assert not at.exception
    assert MSG_CMP_GUIDE in tab_values(at, COMPARE, "info")
    assert compare_charts(at) == []
    assert at.tabs[COMPARE].dataframe == []
    assert not at.tabs[COMPARE].error and not at.tabs[COMPARE].warning


def test_selector_allows_three_and_hides_corrupt_files(tmp_path):
    slugs = [save_strategy(tmp_path, f"E{n}") for n in range(3)]
    (folder_of(tmp_path) / "rota.json").write_bytes(b"{roto")
    at = saved_app(tmp_path)
    selector = at.multiselect(key="cmp_selected_input")
    assert selector.proto.max_selections == 3
    assert list(selector.options) == ["E0", "E1", "E2"]  # format_func: nombres
    assert "rota" not in selector.options
    select(at, slugs)
    assert at.session_state["cmp_selected"] == slugs


def test_add_to_compare_shows_in_selector_and_fourth_is_rejected(tmp_path):
    slugs = [save_strategy(tmp_path, f"E{n}") for n in range(4)]
    at = saved_app(tmp_path)
    for slug in slugs:
        click(at, f"sv_compare_{slug}")
    assert at.multiselect(key="cmp_selected_input").value == slugs[:3]
    assert MSG_MAX in [element.value for element in at.warning]
    assert len(curve_names(at)) == 4


# ---------------------------------------------------------------------------
# Gráfico y tabla
# ---------------------------------------------------------------------------


def test_one_selected_draws_two_curves_and_table(tmp_path):
    slug = save_strategy(tmp_path, "Condor", CONDOR_LEGS)
    at = saved_app(tmp_path)
    select(at, [slug])

    assert not at.exception
    assert curve_names(at) == [BUILDER_LABEL, "Condor"]
    breakeven_traces = [trace for trace in traces(at) if trace.get("mode") == "markers"]
    assert [trace["name"] for trace in breakeven_traces] == [
        f"{BUILDER_LABEL}: breakeven",
        "Condor: breakeven",
    ]
    frame = table(at)
    assert list(frame.columns) == [
        "Estrategia",
        "Ganancia máx.",
        "Pérdida máx.",
        "Breakevens",
        "Comisiones",
        "Prima neta",
        "PoP",
    ]
    assert list(frame["Estrategia"]) == [BUILDER_LABEL, "Condor"]
    assert MSG_CMP_SAME_MARKET in tab_values(at, COMPARE, "caption")
    assert not at.tabs[COMPARE].warning and not at.tabs[COMPARE].error


def test_three_selected_draw_four_curves(tmp_path):
    slugs = [save_strategy(tmp_path, name, CONDOR_LEGS) for name in ("A", "B", "C")]
    at = saved_app(tmp_path)
    select(at, slugs)
    assert curve_names(at) == [BUILDER_LABEL, "A", "B", "C"]
    assert len(table(at)) == 4


def test_table_matches_engine_and_hand_oracle(tmp_path):
    slug = save_strategy(tmp_path, "Condor", CONDOR_LEGS)
    at = saved_app(tmp_path)
    set_builder_call(at)
    select(at, [slug])
    frame = table(at)

    expected = compare.compare_strategies(
        [(BUILDER_LABEL, engine_legs(CALL_LEGS)), ("Condor", engine_legs(CONDOR_LEGS))],
        DEFAULT_MARKET,
        DEFAULT_SETTINGS,
        SimulationSettings(),
    )
    call_row, condor_row = expected.rows
    # Call comprada 2,50: débito 250; pérdida máx. = -250 - 0,65 (apertura)
    # - 0,65 (cierre: justo por encima del strike la call vence con valor y
    # paga cierre; medido -251,30, tolerancia de pytest.approx); comisiones
    # abrir + cerrar = 1,30; ganancia ilimitada.
    assert call_row.net_premium == pytest.approx(-250.0)
    assert call_row.worst_pnl == pytest.approx(-251.30)
    assert list(frame.iloc[0]) == [
        BUILDER_LABEL,
        "ilimitada",
        "-251.30 USD",
        f"{call_row.breakevens[0]:.2f}",
        "1.30 USD",
        "Débito 250.00 USD",
        f"{call_row.pop * 100:.1f} %",
    ]
    # Iron condor: crédito (2+2-1-1)×100 = 200; ganancia máx. = 200 - 4×0,65 =
    # 197,40; pérdida máx. = -(5×100 - 200) - 2,60 - 2×0,65 (cierre de 2 patas
    # con valor) = -303,90; comisiones abrir + cerrar = 8×0,65 = 5,20.
    assert condor_row.best_pnl == pytest.approx(197.40)
    assert condor_row.worst_pnl == pytest.approx(-303.90)
    assert list(frame.iloc[1]) == [
        "Condor",
        "197.40 USD",
        "-303.90 USD",
        " y ".join(f"{value:.2f}" for value in condor_row.breakevens),
        "5.20 USD",
        "Crédito 200.00 USD",
        f"{condor_row.pop * 100:.1f} %",
    ]


def test_saved_with_other_market_is_revalued_with_notice(tmp_path):
    old_market = Market("Acción", 80.0, 0.3, 60, 0.04, 0.0, "binomial")
    slug = save_strategy(tmp_path, "Vieja", [leg(strike=80.0, price=5.0)], market=old_market)
    at = saved_app(tmp_path)
    select(at, [slug])

    infos = tab_values(at, COMPARE, "info")
    assert any(text.startswith("«Vieja» se guardó con spot 80") for text in infos)
    assert not at.tabs[COMPARE].warning
    # Prima automática recalculada con el mercado actual (spot 100).
    revalued = compare.revalue_legs(
        __import__("estrategias").store.read_strategy(slug, folder_of(tmp_path))[0].strategy.legs,
        DEFAULT_MARKET,
    )
    expected = compare.compare_strategies([("Vieja", revalued)], DEFAULT_MARKET, DEFAULT_SETTINGS, SimulationSettings())
    assert table(at).iloc[1]["Prima neta"] == f"Débito {-expected.rows[0].net_premium:.2f} USD"


def test_same_market_shows_no_notice(tmp_path):
    slug = save_strategy(tmp_path, "Igual")
    at = saved_app(tmp_path)
    select(at, [slug])
    assert not any("se guardó con" in text for text in tab_values(at, COMPARE, "info"))


def test_without_checkbox_no_heavy_calls(tmp_path, spies):
    slug = save_strategy(tmp_path, "Condor", CONDOR_LEGS)
    at = saved_app(tmp_path)
    select(at, [slug])
    today, greeks = spies
    assert (today.calls, greeks.calls) == (0, 0)
    assert not any("(hoy)" in name for name in curve_names(at))
    assert "Griegas (hoy)" not in table(at).columns


def test_with_checkbox_today_curves_on_own_grid_and_greeks(tmp_path, spies):
    slug = save_strategy(tmp_path, "Condor", CONDOR_LEGS)
    at = saved_app(tmp_path, timeout=60)
    set_builder_call(at)
    select(at, [slug])
    heavy(at)

    assert at.session_state["cmp_heavy"] is True
    today, greeks = spies
    assert today.calls >= 2 and greeks.calls >= 2
    data = traces(at)
    lines = {trace["name"]: trace for trace in data if trace.get("mode") == "lines"}
    assert list(lines) == [BUILDER_LABEL, f"{BUILDER_LABEL} (hoy)", "Condor", "Condor (hoy)"]
    for label, items in ((BUILDER_LABEL, CALL_LEGS), ("Condor", CONDOR_LEGS)):
        own = price_grid(DEFAULT_MARKET, engine_legs(items))
        assert decode(lines[f"{label} (hoy)"]["x"]) == pytest.approx(own)
        assert lines[f"{label} (hoy)"]["line"]["color"] == lines[label]["line"]["color"]
    frame = table(at)
    assert "Griegas (hoy)" in frame.columns
    assert all(text.startswith("Δ ") for text in frame["Griegas (hoy)"])

    heavy(at, False)
    assert not any("(hoy)" in name for name in curve_names(at))


def test_zero_days_shows_dash_for_pop_and_greeks(tmp_path):
    slug = save_strategy(tmp_path, "Condor", CONDOR_LEGS)
    at = saved_app(tmp_path, timeout=60)
    at.number_input(key="days").set_value(0).run()
    select(at, [slug])
    assert set(table(at)["PoP"]) == {"—"}
    heavy(at)
    frame = table(at)
    assert set(frame["PoP"]) == {"—"}
    assert set(frame["Griegas (hoy)"]) == {"—"}
    assert not at.exception


def test_chart_styles_follow_series_style(tmp_path):
    slugs = [save_strategy(tmp_path, name, CONDOR_LEGS) for name in ("A", "B", "C")]
    at = saved_app(tmp_path)
    select(at, slugs)
    chart = compare_charts(at)[0]
    assert chart["layout"]["hovermode"] == "x unified"
    lines = [trace for trace in chart["data"] if trace.get("mode") == "lines"]
    markers = [trace for trace in chart["data"] if trace.get("mode") == "markers"]
    for index, trace in enumerate(lines):
        color, dash = series_style(index)
        assert trace["line"]["color"] == color
        assert trace["line"].get("dash", "solid") == dash
    assert lines[0]["line"]["color"] == "#2a78d6"  # azul para el Constructor
    for index, trace in enumerate(markers):
        assert trace["marker"]["color"] == series_style(index)[0]


def test_figure_values_are_finite_and_serializable(tmp_path):
    slugs = [save_strategy(tmp_path, name, items) for name, items in (("Condor", CONDOR_LEGS), ("Call", CALL_LEGS))]
    at = saved_app(tmp_path, timeout=60)
    select(at, slugs)
    heavy(at)
    for trace in traces(at):
        assert np.all(np.isfinite(decode(trace["x"])))
        assert np.all(np.isfinite(decode(trace["y"])))

    entries = [("A", engine_legs(CONDOR_LEGS)), ("B", engine_legs(CALL_LEGS))]
    result = compare.compare_strategies(
        entries, DEFAULT_MARKET, DEFAULT_SETTINGS, SimulationSettings(), with_heavy=True
    )
    figure = build_compare_figure(result, DEFAULT_MARKET, ["A", "B"], True)
    assert isinstance(figure, go.Figure)
    assert json.loads(figure.to_json())["data"]


# ---------------------------------------------------------------------------
# Borrar, errores y mercado inválido
# ---------------------------------------------------------------------------


def test_deleting_selected_strategy_cleans_selection(tmp_path):
    slug = save_strategy(tmp_path, "Borrable", CONDOR_LEGS)
    other = save_strategy(tmp_path, "Queda", CONDOR_LEGS)
    at = saved_app(tmp_path)
    select(at, [slug, other])
    click(at, f"sv_delete_{slug}")
    click(at, "sv_confirm_yes")

    assert not at.exception
    assert at.session_state["cmp_selected"] == [other]
    assert at.multiselect(key="cmp_selected_input").value == [other]
    assert curve_names(at) == [BUILDER_LABEL, "Queda"]


def test_file_removed_outside_the_app_is_dropped_from_selection(tmp_path):
    slug = save_strategy(tmp_path, "Desaparece")
    at = saved_app(tmp_path)
    select(at, [slug])
    (folder_of(tmp_path) / f"{slug}.json").unlink()
    at.run()
    assert not at.exception
    assert at.session_state["cmp_selected"] == []
    assert MSG_CMP_GUIDE in tab_values(at, COMPARE, "info")


def test_compare_failure_shows_spanish_error(tmp_path, monkeypatch):
    slug = save_strategy(tmp_path, "Condor", CONDOR_LEGS)
    at = saved_app(tmp_path)

    def boom(*args, **kwargs):
        raise ZeroDivisionError("motor")

    monkeypatch.setattr(estrategias.compare, "compare_strategies", boom)
    select(at, [slug])
    assert not at.exception
    assert MSG_CMP_FAILED in tab_values(at, COMPARE, "error")
    assert compare_charts(at) == []


def test_invalid_market_shows_message_and_no_calculation(tmp_path, spies):
    slug = save_strategy(tmp_path, "Condor", CONDOR_LEGS)
    at = saved_app(tmp_path)
    at.number_input(key="spot").set_value(0.0).run()
    select(at, [slug])
    assert MSG_CMP_MARKET_INVALID in tab_values(at, COMPARE, "warning")
    assert compare_charts(at) == []
    assert at.tabs[COMPARE].dataframe == []


def test_invalid_builder_legs_are_reported_and_saved_still_compared(tmp_path):
    slug = save_strategy(tmp_path, "Condor", CONDOR_LEGS)
    at = saved_app(tmp_path)
    leg_id = at.session_state["legs"][0]["id"]
    click(at, f"leg_{leg_id}_remove")
    select(at, [slug])
    assert not at.exception
    assert any(BUILDER_LABEL in text for text in tab_values(at, COMPARE, "warning"))
    assert curve_names(at) == ["Condor"]
    # El color sigue el índice de la entrada: la guardada es la serie 1.
    assert traces(at)[0]["line"]["color"] == series_style(1)[0]


# ---------------------------------------------------------------------------
# series_style (puro) y tiempos
# ---------------------------------------------------------------------------


def test_series_style_is_pure_and_distinct():
    styles = [series_style(index) for index in range(4)]
    assert styles == SERIES_STYLES
    assert len(set(styles)) == 4
    assert len({color for color, _dash in styles}) == 4
    assert len({dash for _color, dash in styles}) == 4
    assert series_style(0) == ("#2a78d6", "solid")
    with pytest.raises(ValueError):
        series_style(4)
    with pytest.raises(ValueError):
        series_style(-1)


def test_timing_without_checkbox_three_saved(tmp_path):
    slugs = [save_strategy(tmp_path, f"Auto {n}", AUTO_CONDORS[n]) for n in range(3)]
    at = saved_app(tmp_path, timeout=60)
    clear_binomial_caches()
    start = time.perf_counter()
    select(at, slugs)
    elapsed = time.perf_counter() - start
    print(f"\n[medido] Comparar sin casilla, 3 guardadas, frío: {elapsed:.2f} s")
    assert not at.exception
    assert len(curve_names(at)) == 4
    assert elapsed < 10


def test_timing_with_checkbox_four_strategies_cold(tmp_path):
    market = Market("Acción", 100.0, 0.2, 45, 0.04, 0.0, "binomial")
    slugs = [save_strategy(tmp_path, f"Auto {n}", AUTO_CONDORS[n], market=market) for n in range(3)]
    at = saved_app(tmp_path, timeout=60)
    at.number_input(key="days").set_value(45).run()
    at.button(key="open_iron_condor").click().run()
    select(at, slugs)
    clear_binomial_caches()
    start = time.perf_counter()
    heavy(at)
    elapsed = time.perf_counter() - start
    print(f"\n[medido] Comparar con «hoy» y griegas, 4 iron condors, binomial, 45 días, frío: {elapsed:.2f} s")
    assert not at.exception
    assert len([name for name in curve_names(at) if name.endswith("(hoy)")]) == 4
    assert elapsed < 8
