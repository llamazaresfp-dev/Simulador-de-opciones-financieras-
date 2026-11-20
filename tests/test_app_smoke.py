"""Smoke tests de la interfaz Streamlit (app.py) con AppTest.

AppTest ejecuta app.py sin navegador y permite tocar widgets desde Python.
Estos tests comprueban que la app no falla y que los datos llegan al motor.

Importante: AppTest ejecuta el cuerpo de TODAS las pestañas en cada
ejecución, así que estos tests NO prueban que los valores persistan al
cambiar de pestaña en un navegador real. Eso solo lo prueba la revisión
manual (ítem 9 de la checklist del plan).
"""

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from opciones import Leg, Market, implied_vol
from opciones.implied_vol import MSG_ABOVE_UPPER_BOUND
from opciones.validation import (
    MSG_BAD_MU,
    MSG_BAD_PATHS,
    MSG_BAD_SEED,
    MSG_FAT_TAILS,
    MSG_MODEL,
    MSG_NOT_ADVICE,
    MSG_SCENARIO_ZERO_DAYS,
)

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app() -> AppTest:
    """La app recién abierta (primera ejecución completa)."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    return at


def metric_value(at: AppTest, label: str) -> str:
    """Texto mostrado en la métrica con esa etiqueta."""
    for metric in at.metric:
        if metric.label == label:
            return metric.value
    raise AssertionError(f"No se encontró la métrica {label!r}")


SCENARIOS_LABEL = "Escenarios (Monte Carlo)"


def scenarios_expander(at: AppTest):
    """El desplegable de escenarios, o None si no se dibujó."""
    for expander in at.expander:
        if expander.label == SCENARIOS_LABEL:
            return expander
    return None


def test_app_loads_without_exception(app):
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Catálogo", "Constructor", "Ajustes"]
    # Con los datos por defecto hay una pata y se dibuja el gráfico de P&L
    # (más el histograma de escenarios, dentro de su desplegable: Etapa A).
    assert len(app.get("plotly_chart")) == 2
    assert not app.error


def test_open_template_fills_legs_and_switches_to_builder(app):
    app.button(key="open_iron_condor").click().run()

    assert not app.exception
    assert app.session_state["main_tab"] == "Constructor"
    legs = app.session_state["legs"]
    assert len(legs) == 4
    assert [leg["kind"] for leg in legs] == ["put", "put", "call", "call"]
    assert all(not leg["premium_manual"] for leg in legs)
    # Gráfico de P&L + histograma de escenarios (Etapa A).
    assert len(app.get("plotly_chart")) == 2


def test_iron_condor_shows_both_breakevens_in_full(app):
    """Los dos breakevens del iron condor se leen enteros (sin recortar)."""
    app.button(key="open_iron_condor").click().run()

    texts = [md.value for md in app.markdown if "Breakevens" in md.value]
    assert len(texts) == 1
    numbers = re.findall(r"\d+\.\d{2}", texts[0])
    assert len(numbers) == 2
    low, high = (float(n) for n in numbers)
    assert low < 100 < high  # uno por debajo y otro por encima del spot
    assert "…" not in texts[0]


def test_commission_setting_from_session_state_reaches_result(app):
    """Cambiar la comisión por contrato (callback) cambia el total de comisiones.

    No prueba persistencia entre pestañas (ver docstring del módulo).
    """
    app.button(key="open_iron_condor").click().run()
    # 4 contratos × 0,65 × 2 (abrir + cerrar) = 5,20 USD
    assert metric_value(app, "Comisiones totales") == "5.20 USD"

    app.number_input(key="per_contract_input").set_value(1.0).run()

    assert app.session_state["per_contract"] == pytest.approx(1.0)
    # 4 contratos × 1,00 × 2 = 8,00 USD
    assert metric_value(app, "Comisiones totales") == "8.00 USD"


def test_zero_days_shows_notice_not_error(app):
    app.number_input(key="days").set_value(0).run()

    assert not app.exception
    # El MVP no da error con días = 0; el único error es el de los
    # escenarios (Etapa A), que no pueden simular sin tiempo.
    assert [error.value for error in app.error] == [MSG_SCENARIO_ZERO_DAYS]
    notices = [info.value for info in app.info]
    assert any(text.startswith("Días al vencimiento = 0") for text in notices)
    # Solo el gráfico de P&L: los escenarios no muestran histograma.
    assert len(app.get("plotly_chart")) == 1
    # Sin griegas: la tabla muestra "—".
    assert set(app.table[0].value["Valor"]) == {"—"}


def test_zero_volatility_shows_error_and_no_chart(app):
    app.number_input(key="vol_pct").set_value(0.0).run()

    assert not app.exception
    errors = [error.value for error in app.error]
    assert any("volatilidad" in text for text in errors)
    assert len(app.get("plotly_chart")) == 0


# ---------------------------------------------------------------------------
# Etapa A, bloque 4a: desplegable "Escenarios (Monte Carlo)"
# ---------------------------------------------------------------------------


def expander_texts(expander) -> list[str]:
    """Todos los textos visibles dentro del desplegable (para buscar palabras)."""
    texts = []
    for kind in ("markdown", "caption", "info", "error", "warning"):
        texts += [element.value for element in expander.get(kind)]
    texts += [f"{metric.label} {metric.value}" for metric in expander.get("metric")]
    texts += [widget.label for widget in expander.get("number_input")]
    texts += [widget.label for widget in expander.get("button")]
    return texts


def expander_metric(expander, label: str) -> str:
    """Valor de una métrica dentro del desplegable."""
    for metric in expander.get("metric"):
        if metric.label == label:
            return metric.value
    raise AssertionError(f"No se encontró la métrica {label!r}")


def test_scenarios_expander_shows_results(app):
    """Estrategia válida: PoP exacta y simulada, valor esperado, percentiles, histograma y avisos."""
    expander = scenarios_expander(app)
    assert expander is not None
    labels = [metric.label for metric in expander.get("metric")]
    assert labels == [
        "PoP exacta",
        "PoP simulada",
        "Valor esperado (no descontado)",
        "Percentil 5",
        "Mediana (p50)",
        "Percentil 95",
    ]
    # Long call ATM con los datos por defecto: PoP exacta y simulada parecidas.
    exact = float(expander_metric(expander, "PoP exacta").rstrip(" %"))
    simulated = float(expander_metric(expander, "PoP simulada").rstrip(" %"))
    assert 0 < exact < 100
    assert abs(exact - simulated) < 1.0
    assert len(expander.get("plotly_chart")) == 1
    texts = expander_texts(expander)
    assert any("neutral al riesgo" in text for text in texts)
    assert any("acumulan las colas" in text for text in texts)
    assert MSG_MODEL in texts and MSG_FAT_TAILS in texts
    assert not expander.get("error")


def test_scenarios_expander_is_below_greeks(app):
    """El desplegable va después de la tabla de griegas (bajo las métricas)."""
    # El orden de los hijos de la pestaña Constructor es el orden en pantalla.
    children = list(app.tabs[1].children.values())
    types = [node.type for node in children]
    chart_index = types.index("plotly_chart")
    table_index = types.index("table")
    expander_index = next(
        i for i, node in enumerate(children)
        if node.type == "expander" and node.label == SCENARIOS_LABEL
    )
    assert chart_index < table_index < expander_index


def assert_no_today_results(expander) -> None:
    """AC-A7: ningún resultado, métrica, control ni traza del gráfico es de «hoy».

    Los st.warning no se miran: el aviso de la IV (AC-A13) menciona la curva
    «hoy» a propósito, para explicar qué cambia al pulsar el botón.
    """
    texts = []
    for kind in ("markdown", "caption", "info", "error"):
        texts += [element.value for element in expander.get(kind)]
    texts += [metric.label for metric in expander.get("metric")]
    texts += [widget.label for widget in expander.get("number_input")]
    texts += [widget.label for widget in expander.get("button")]
    for text in texts:
        assert "hoy" not in text.lower()
    for chart in expander.get("plotly_chart"):
        assert "hoy" not in chart.proto.spec.lower()


def test_no_today_inside_scenarios_expander(app):
    """AC-A7: dentro del desplegable no hay nada de la curva «hoy»."""
    expander = scenarios_expander(app)
    assert len(expander.get("plotly_chart")) == 1
    assert_no_today_results(expander)


def test_no_today_inside_scenarios_expander_with_manual_leg(app):
    """AC-A7 con prima manual: el aviso de la IV nombra «hoy», pero nada más."""
    set_manual_premium(app, 3.00)

    assert not app.exception
    expander = scenarios_expander(app)
    warnings = [warning.value for warning in expander.get("warning")]
    assert len(warnings) == 1 and "hoy" in warnings[0]
    assert len(expander.get("plotly_chart")) == 1
    assert_no_today_results(expander)


def test_expected_value_label_not_truncated(app):
    """AC-A6: «no descontado» se lee entero en un texto que no se recorta."""
    expander = scenarios_expander(app)
    captions = [element.value for element in expander.get("caption")]
    markdowns = [element.value for element in expander.get("markdown")]
    assert any("no descontado" in text for text in captions + markdowns)
    # La métrica del valor esperado va sola en su fila (fuera de st.columns).
    direct = [node for node in expander.children.values() if node.type == "metric"]
    assert [node.label for node in direct] == ["Valor esperado (no descontado)"]


def test_scenarios_expander_absent_with_market_error(app):
    app.number_input(key="vol_pct").set_value(0.0).run()

    assert not app.exception
    assert scenarios_expander(app) is None


def test_scenarios_expander_absent_with_leg_error(app):
    leg_id = app.session_state["legs"][0]["id"]
    app.button(key=f"leg_{leg_id}_remove").click().run()

    assert not app.exception
    assert app.error  # error de patas del MVP
    assert scenarios_expander(app) is None


def test_scenarios_zero_days_shows_message_without_results(app):
    app.number_input(key="days").set_value(0).run()

    expander = scenarios_expander(app)
    assert [error.value for error in expander.get("error")] == [MSG_SCENARIO_ZERO_DAYS]
    assert not expander.get("metric")
    assert not expander.get("plotly_chart")


def test_user_mu_from_session_state_changes_label_and_pop():
    """Enmienda A4: AppTest no puede vaciar un number_input, así que μ se
    prueba iniciando session_state["mu_pct"] antes de la primera ejecución."""
    neutral = AppTest.from_file(APP_PATH, default_timeout=30)
    neutral.run()
    with_mu = AppTest.from_file(APP_PATH, default_timeout=30)
    with_mu.session_state["mu_pct"] = 50.0
    with_mu.run()

    assert not with_mu.exception
    expander = scenarios_expander(with_mu)
    texts = expander_texts(expander)
    assert any("μ del usuario" in text for text in texts)
    assert not any("Escenario: neutral al riesgo" in text for text in texts)
    # μ = 50 % anual > r − q: la PoP del long call sube.
    pop_neutral = float(expander_metric(scenarios_expander(neutral), "PoP exacta").rstrip(" %"))
    pop_mu = float(expander_metric(expander, "PoP exacta").rstrip(" %"))
    assert pop_mu > pop_neutral


def test_mu_widget_copies_to_session_state(app):
    app.number_input(key="mu_pct_input").set_value(10.0).run()

    assert app.session_state["mu_pct"] == pytest.approx(10.0)
    texts = expander_texts(scenarios_expander(app))
    assert any("μ del usuario" in text for text in texts)


def test_invalid_mu_shows_spanish_message(app):
    app.number_input(key="mu_pct_input").set_value(150.0).run()

    assert not app.exception
    expander = scenarios_expander(app)
    assert [error.value for error in expander.get("error")] == [MSG_BAD_MU]
    assert not expander.get("metric")


def test_invalid_n_sims_shows_spanish_message(app):
    app.number_input(key="n_sims_input").set_value(500).run()

    assert not app.exception
    assert app.session_state["n_sims"] == 500
    expander = scenarios_expander(app)
    assert [error.value for error in expander.get("error")] == [MSG_BAD_PATHS]
    assert not expander.get("plotly_chart")


def test_invalid_seed_shows_spanish_message(app):
    app.number_input(key="seed_input").set_value(-1).run()

    assert not app.exception
    expander = scenarios_expander(app)
    assert [error.value for error in expander.get("error")] == [MSG_BAD_SEED]


def test_seed_changes_simulation_not_exact_pop(app):
    """AC-A8: cambiar la semilla cambia la parte simulada, no la PoP exacta."""
    before = scenarios_expander(app)
    exact_before = expander_metric(before, "PoP exacta")
    mean_before = expander_metric(before, "Valor esperado (no descontado)")

    app.number_input(key="seed_input").set_value(7).run()

    after = scenarios_expander(app)
    assert app.session_state["seed"] == 7
    assert expander_metric(after, "PoP exacta") == exact_before
    assert expander_metric(after, "Valor esperado (no descontado)") != mean_before


def test_same_settings_give_same_result(app):
    """AC-A8: repetir el cálculo con los mismos datos da lo mismo."""
    first = [metric.value for metric in scenarios_expander(app).get("metric")]
    app.run()
    second = [metric.value for metric in scenarios_expander(app).get("metric")]
    assert first == second


# ---------------------------------------------------------------------------
# Etapa A, bloque 4b: volatilidad implícita de las primas manuales
# ---------------------------------------------------------------------------


def iv_buttons(at: AppTest) -> list:
    """Botones "Usar como volatilidad global" (clave use_iv_<id>)."""
    return [button for button in at.button if str(button.key).startswith("use_iv_")]


def expander_has_warning(at: AppTest) -> bool:
    """True si el desplegable de escenarios muestra algún st.warning."""
    return bool(scenarios_expander(at).get("warning"))


def set_manual_premium(at: AppTest, premium: float) -> int:
    """Escribe a mano la prima de la primera pata y devuelve su id."""
    leg_id = at.session_state["legs"][0]["id"]
    at.number_input(key=f"leg_{leg_id}_price").set_value(premium).run()
    return leg_id


def expected_iv_pct(premium: float) -> float:
    """IV en % (2 decimales) de la call ATM por defecto, calculada con el motor."""
    market = Market(underlying="Acción", spot=100.0, vol=0.20, days=30, rate=0.04, q=0.0)
    result = implied_vol(Leg("call", 1, 1.0, 100.0, premium), market)
    return round(result.vol * 100, 2)


def test_no_iv_button_without_manual_legs(app):
    """Primas automáticas: no hay IV ni botón (su IV sería la σ global)."""
    assert not iv_buttons(app)
    texts = expander_texts(scenarios_expander(app))
    assert not any("Volatilidad implícita (IV)" in text for text in texts)
    assert not expander_has_warning(app)


def test_iv_button_only_for_manual_option_leg(app):
    """Con una pata manual y otra automática, solo hay botón para la manual."""
    app.button(key="open_iron_condor").click().run()
    legs = app.session_state["legs"]
    manual_id = legs[1]["id"]
    premium = legs[1]["price"] + 0.10
    app.number_input(key=f"leg_{manual_id}_price").set_value(premium).run()

    assert not app.exception
    assert [button.key for button in iv_buttons(app)] == [f"use_iv_{manual_id}"]
    expander = scenarios_expander(app)
    assert [button.key for button in expander.get("button")] == [f"use_iv_{manual_id}"]
    warnings = [warning.value for warning in expander.get("warning")]
    assert len(warnings) == 1
    assert "primas automáticas" in warnings[0] and "hoy" in warnings[0]
    assert "no encaja con todos los strikes" in warnings[0]


def test_no_iv_button_for_manual_stock_leg(app):
    """Una acción con precio manual no tiene IV ni botón."""
    leg_id = app.session_state["legs"][0]["id"]
    app.selectbox(key=f"leg_{leg_id}_kind").set_value("stock").run()
    app.number_input(key=f"leg_{leg_id}_price").set_value(101.0).run()

    assert not app.exception
    assert app.session_state["legs"][0]["premium_manual"]
    assert not iv_buttons(app)


def test_manual_premium_shows_iv_and_button(app):
    leg_id = set_manual_premium(app, 3.0)

    assert not app.exception
    iv_pct = expected_iv_pct(3.0)
    captions = [caption.value for caption in scenarios_expander(app).get("caption")]
    assert any(f"volatilidad implícita {iv_pct:.2f} %" in text for text in captions)
    assert app.button(key=f"use_iv_{leg_id}").label == "Usar como volatilidad global"


def test_use_iv_button_sets_global_vol_and_recomputes(app):
    """AC-A13: el botón pone la IV en la barra lateral y todo se recalcula."""
    leg_id = set_manual_premium(app, 3.0)
    pop_before = expander_metric(scenarios_expander(app), "PoP exacta")

    app.button(key=f"use_iv_{leg_id}").click().run()

    assert not app.exception
    iv_pct = expected_iv_pct(3.0)
    assert app.session_state["vol_pct"] == iv_pct
    assert app.number_input(key="vol_pct").value == pytest.approx(iv_pct)
    assert expander_metric(scenarios_expander(app), "PoP exacta") != pop_before
    # La prima manual se respeta; con la nueva σ su IV es esa misma σ.
    assert app.session_state["legs"][0]["price"] == pytest.approx(3.0)


def test_use_iv_button_updates_automatic_premiums(app):
    """Las primas automáticas se recalculan con la nueva σ (refresh_auto_prices)."""
    app.button(key="open_bull_call_spread").click().run()
    legs = app.session_state["legs"]
    manual_id = legs[0]["id"]
    auto_before = legs[1]["price"]
    app.number_input(key=f"leg_{manual_id}_price").set_value(legs[0]["price"] * 1.5).run()

    app.button(key=f"use_iv_{manual_id}").click().run()

    assert not app.exception
    assert app.session_state["vol_pct"] > 20.0
    assert app.session_state["legs"][1]["price"] > auto_before


def test_out_of_bounds_premium_shows_iv_message(app):
    """Prima mayor que el spot en una call: no existe IV, se explica y no hay botón."""
    set_manual_premium(app, 150.0)

    assert not app.exception
    captions = [caption.value for caption in scenarios_expander(app).get("caption")]
    assert any(MSG_ABOVE_UPPER_BOUND in text for text in captions)
    assert not iv_buttons(app)


# ---------------------------------------------------------------------------
# Aviso "no es asesoría": una sola vez en el Constructor (corrección 20-11-26)
# ---------------------------------------------------------------------------


def test_not_advice_notice_not_duplicated(app):
    """El desplegable no repite el aviso: sale una vez en los avisos generales."""
    expander = scenarios_expander(app)
    assert MSG_NOT_ADVICE not in [info.value for info in expander.get("info")]
    builder_infos = [info.value for info in app.tabs[1].info]
    assert builder_infos.count(MSG_NOT_ADVICE) == 1
