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

from opciones import Leg, Market, default_premium, implied_vol
from opciones.implied_vol import MSG_ABOVE_UPPER_BOUND
from opciones.validation import (
    MSG_AMERICAN,
    MSG_BAD_MU,
    MSG_BAD_PATHS,
    MSG_BAD_SEED,
    MSG_BINOMIAL_ACTIVE,
    MSG_EUROPEAN,
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
    assert [tab.label for tab in app.tabs] == ["📊 Catálogo", "🛠️ Constructor", "⚙️ Ajustes", "📈 Backtest"]
    # Con los datos por defecto hay una pata y se dibuja el gráfico de P&L
    # (más el histograma de escenarios, dentro de su desplegable: Etapa A).
    assert len(app.get("plotly_chart")) == 2
    assert not app.error


def test_open_template_fills_legs_and_switches_to_builder(app):
    app.button(key="open_iron_condor").click().run()

    assert not app.exception
    assert app.session_state["main_tab"] == "🛠️ Constructor"
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


def expected_iv_pct(premium: float, kind: str = "call", q: float = 0.0,
                    pricing_model: str = "binomial") -> float:
    """IV en % (2 decimales) de la pata ATM por defecto, calculada con el motor.

    El modelo es explícito: la app por defecto valora Acción con el árbol
    binomial (americano), así que el oráculo usa ese mismo modelo. Con la
    call ATM y q = 0 la IV americana y la europea coinciden (una call sin
    dividendos no se ejerce antes); el test del put con q > 0 sí las distingue.
    """
    market = Market(underlying="Acción", spot=100.0, vol=0.20, days=30, rate=0.04, q=q,
                    pricing_model=pricing_model)
    result = implied_vol(Leg(kind, 1, 1.0, 100.0, premium), market)
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


def test_manual_put_iv_uses_american_model(app):
    """La IV de la app es la americana: put ATM, q = 2 %, prima 3,00.

    Aquí la IV americana (≈ 26,92 %) y la europea (≈ 27,01 %) difieren,
    así que el test demuestra qué modelo usa la app.
    """
    app.number_input(key="q_pct").set_value(2.0).run()
    leg_id = app.session_state["legs"][0]["id"]
    app.selectbox(key=f"leg_{leg_id}_kind").set_value("put").run()
    set_manual_premium(app, 3.0)

    assert not app.exception
    american = expected_iv_pct(3.0, kind="put", q=0.02, pricing_model="binomial")
    european = expected_iv_pct(3.0, kind="put", q=0.02, pricing_model="black_scholes")
    assert american != european
    captions = [caption.value for caption in scenarios_expander(app).get("caption")]
    assert any(f"volatilidad implícita {american:.2f} %" in text for text in captions)
    assert not any(f"volatilidad implícita {european:.2f} %" in text for text in captions)


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


# ---------------------------------------------------------------------------
# Etapa B1, bloque 6: selector del modelo de valoración
# ---------------------------------------------------------------------------


def app_market(at: AppTest, pricing_model: str) -> Market:
    """El Market que ve la app (barra lateral) con el modelo indicado."""
    state = at.session_state
    return Market(
        underlying=state["underlying"],
        spot=state["spot"],
        vol=state["vol_pct"] / 100,
        days=state["days"],
        rate=state["rate_pct"] / 100,
        q=state["q_pct"] / 100,
        pricing_model=pricing_model,
    )


def reset_label(at: AppTest, leg_id: int) -> str:
    return at.button(key=f"leg_{leg_id}_reset").label


def test_default_model_is_binomial(app):
    assert app.session_state["pricing_model"] == "binomial"
    leg = app.session_state["legs"][0]
    expected = default_premium("call", app_market(app, "binomial"), leg["strike"])
    assert leg["price"] == pytest.approx(expected, abs=1e-12)


def test_pricing_radio_has_both_options(app):
    radio = app.radio(key="pricing_model_input")
    assert radio.label == "Modelo de valoración para Acción/ETF"
    assert radio.options == ["Binomial (americano)", "Black-Scholes (europeo)"]
    assert radio.value == "binomial"


def test_switch_to_black_scholes_recomputes_auto_keeps_manual(app):
    app.button(key="open_bull_call_spread").click().run()
    legs = app.session_state["legs"]
    manual_id = legs[0]["id"]
    app.number_input(key=f"leg_{manual_id}_price").set_value(7.77).run()
    binomial_auto = app.session_state["legs"][1]["price"]

    app.radio(key="pricing_model_input").set_value("black_scholes").run()

    assert not app.exception
    assert app.session_state["pricing_model"] == "black_scholes"
    legs = app.session_state["legs"]
    assert legs[0]["price"] == pytest.approx(7.77)
    assert legs[0]["premium_manual"]
    expected = default_premium("call", app_market(app, "black_scholes"), legs[1]["strike"])
    assert legs[1]["price"] == pytest.approx(expected, abs=1e-12)
    # Y de vuelta a binomial: la prima automática vuelve al valor del árbol.
    app.radio(key="pricing_model_input").set_value("binomial").run()
    assert app.session_state["legs"][1]["price"] == pytest.approx(binomial_auto, abs=1e-12)
    assert app.session_state["legs"][0]["price"] == pytest.approx(7.77)


def test_switch_changes_put_premium(app):
    """Un put ATM: la prima binomial (americana) es mayor que la de BS."""
    leg_id = app.session_state["legs"][0]["id"]
    app.selectbox(key=f"leg_{leg_id}_kind").set_value("put").run()
    binomial_price = app.session_state["legs"][0]["price"]
    app.radio(key="pricing_model_input").set_value("black_scholes").run()
    bs_value = app.session_state["legs"][0]["price"]
    assert binomial_price > bs_value


def test_index_ignores_selector(app):
    app.selectbox(key="underlying").set_value("Índice").run()
    before = [leg["price"] for leg in app.session_state["legs"]]

    app.radio(key="pricing_model_input").set_value("black_scholes").run()

    assert not app.exception
    after = [leg["price"] for leg in app.session_state["legs"]]
    assert after == before
    builder_captions = [caption.value for caption in app.tabs[1].caption]
    settings_captions = [caption.value for caption in app.tabs[2].caption]
    assert any("no tiene efecto" in text for text in builder_captions)
    assert any("no tiene efecto" in text for text in settings_captions)
    assert MSG_EUROPEAN in [info.value for info in app.tabs[1].info]


def test_reset_button_label_follows_model(app):
    leg_id = app.session_state["legs"][0]["id"]
    assert reset_label(app, leg_id) == "🔄 binomial"
    captions = [caption.value for caption in app.tabs[1].caption]
    assert "Pata 1: precio binomial." in captions

    app.radio(key="pricing_model_input").set_value("black_scholes").run()
    assert reset_label(app, leg_id) == "🔄 BS"
    captions = [caption.value for caption in app.tabs[1].caption]
    assert "Pata 1: precio Black-Scholes." in captions

    app.selectbox(key=f"leg_{leg_id}_kind").set_value("stock").run()
    assert reset_label(app, leg_id) == "🔄 spot"
    assert "Pata 1: precio spot." in [caption.value for caption in app.tabs[1].caption]


def test_reset_button_label_with_index_is_bs(app):
    app.selectbox(key="underlying").set_value("Índice").run()
    leg_id = app.session_state["legs"][0]["id"]
    assert reset_label(app, leg_id) == "🔄 BS"


def test_manual_premium_caption_and_reset(app):
    leg_id = set_manual_premium(app, 4.0)
    assert "Pata 1: precio manual." in [caption.value for caption in app.tabs[1].caption]
    app.button(key=f"leg_{leg_id}_reset").click().run()
    assert not app.session_state["legs"][0]["premium_manual"]
    assert "Pata 1: precio binomial." in [caption.value for caption in app.tabs[1].caption]


def test_active_model_caption_and_warnings(app):
    captions = [caption.value for caption in app.tabs[1].caption]
    assert any(text.startswith("Modelo activo: Binomial (americano)") for text in captions)
    assert MSG_BINOMIAL_ACTIVE in [info.value for info in app.tabs[1].info]
    # No es una métrica (st.metric recorta los textos largos).
    assert not any("Modelo activo" in metric.label for metric in app.metric)

    app.radio(key="pricing_model_input").set_value("black_scholes").run()

    captions = [caption.value for caption in app.tabs[1].caption]
    assert any(text.startswith("Modelo activo: Black-Scholes (europeo)") for text in captions)
    infos = [info.value for info in app.tabs[1].info]
    assert MSG_AMERICAN in infos and MSG_BINOMIAL_ACTIVE not in infos


# ---------------------------------------------------------------------------
# Etapa C1, bloque 5: ticker, "Cargar datos", vencimiento y antigüedad.
# Siempre con FakeProvider (sin red), caché en tmp_path y reloj fijo.
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from datos import FakeProvider, NetworkError  # noqa: E402
from datos.errors import MSG_NETWORK  # noqa: E402
from datos.service import MSG_NO_CACHE, MSG_Q_INDEX, MSG_Q_MISSING  # noqa: E402

# Reloj fijo: viernes 20/11/2026 10:30 en Nueva York.
FIXED_NOW = datetime(2026, 11, 20, 10, 30, tzinfo=ZoneInfo("America/New_York"))


def data_app(tmp_path, provider=None, now=FIXED_NOW) -> AppTest:
    """App con proveedor falso, caché en tmp_path y reloj fijo inyectados."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["data_provider"] = provider or FakeProvider(today=now)
    at.session_state["cache_dir"] = str(tmp_path)
    at.session_state["clock"] = lambda: now
    at.run()
    return at


def choose_ticker(at: AppTest, underlying: str, ticker: str) -> AppTest:
    """Elige tipo de subyacente y ticker en la barra lateral."""
    if at.session_state["underlying"] != underlying:
        at.selectbox(key="underlying").set_value(underlying).run()
    at.selectbox(key="ticker_choice").set_value(ticker).run()
    return at


def load(at: AppTest) -> AppTest:
    """Pulsa "Cargar datos"."""
    at.button(key="load_data").click().run()
    return at


def expiry_selects(at: AppTest) -> list:
    return [box for box in at.selectbox if box.label == "Vencimiento"]


def captions(at: AppTest) -> list[str]:
    return [caption.value for caption in at.caption]


def test_manual_mode_is_default_and_inert(app):
    state = app.session_state
    assert state["ticker_choice"] == "Entrada manual"
    assert state["snapshot"] is None
    assert state["expiry_choice"] is None
    assert state["load_notice"] == []
    # Mismos valores por defecto que antes de la Etapa C1.
    assert (state["spot"], state["vol_pct"], state["days"]) == (100.0, 20.0, 30)
    assert (state["rate_pct"], state["q_pct"]) == (4.0, 0.0)
    assert app.button(key="load_data").disabled
    assert expiry_selects(app) == []
    assert not app.error and not app.warning
    assert not any("datos con" in text or "datos guardados" in text for text in captions(app))


def test_ticker_options_follow_underlying(app):
    assert app.selectbox(key="ticker_choice").options == [
        "Entrada manual", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
    ]
    app.selectbox(key="underlying").set_value("ETF").run()
    assert app.selectbox(key="ticker_choice").options == ["Entrada manual", "SPY", "QQQ", "IWM"]
    app.selectbox(key="underlying").set_value("Índice").run()
    assert app.selectbox(key="ticker_choice").options == ["Entrada manual", "SPX"]


def test_load_button_enabled_for_curated_ticker(tmp_path):
    at = choose_ticker(data_app(tmp_path), "ETF", "SPY")
    assert not at.exception
    assert not at.button(key="load_data").disabled


def test_load_fills_spot_rate_q_expiry_and_days(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    assert not at.exception
    state = at.session_state
    snapshot = state["snapshot"]
    assert snapshot is not None and snapshot.source == "live"
    assert state["spot"] == pytest.approx(snapshot.spot)
    assert at.number_input(key="spot").value == pytest.approx(snapshot.spot)
    # ^IRX 4,122 % -> 0.04122 -> 4.12 en la app.
    assert state["rate_pct"] == 4.12
    # trailingAnnualDividendYield de la fixture SPY: 0.0079093 -> 0.79 %.
    assert state["q_pct"] == 0.79
    # A2: primer vencimiento ofrecido y sus días con el reloj fijo (+10).
    first = sorted(snapshot.chains)[0]
    assert first == (FIXED_NOW.date() + timedelta(days=10)).isoformat()
    assert state["expiry_choice"] == first
    assert expiry_selects(at)[0].value == first
    assert state["days"] == 10
    assert not at.error


def test_loaded_values_stay_editable(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    at.number_input(key="spot").set_value(123.0).run()
    at.number_input(key="rate_pct").set_value(3.5).run()
    at.number_input(key="q_pct").set_value(1.25).run()
    assert not at.exception
    assert at.session_state["spot"] == 123.0
    assert at.session_state["rate_pct"] == 3.5
    assert at.session_state["q_pct"] == 1.25


def test_expiry_options_are_only_liquid_window_expiries(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    expected = [(FIXED_NOW.date() + timedelta(days=d)).isoformat() for d in (10, 17, 45, 90)]
    assert expiry_selects(at)[0].options == [f"{e} ({d} días)" for e, d in zip(expected, (10, 17, 45, 90))]


def test_changing_expiry_sets_days(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    target = (FIXED_NOW.date() + timedelta(days=45)).isoformat()
    expiry_selects(at)[0].set_value(target).run()
    assert not at.exception
    assert at.session_state["expiry_choice"] == target
    assert at.session_state["days"] == 45


def test_age_caption_shows_load_time(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    hour = FIXED_NOW.astimezone().strftime("%H:%M")
    assert f"datos con ~15 min de retraso; cargados a las {hour}" in captions(at)


def test_other_clock_gives_same_relative_result(tmp_path):
    other = datetime(2027, 3, 3, 15, 5, tzinfo=ZoneInfo("America/New_York"))
    at = load(choose_ticker(data_app(tmp_path, FakeProvider(today=other), other), "ETF", "SPY"))
    assert at.session_state["days"] == 10
    assert at.session_state["expiry_choice"] == (other.date() + timedelta(days=10)).isoformat()
    hour = other.astimezone().strftime("%H:%M")
    assert f"datos con ~15 min de retraso; cargados a las {hour}" in captions(at)


def test_expiry_labels_do_not_read_clock_outside_script_run(tmp_path):
    """Regresión: AppTest (y Streamlit) vuelven a llamar a format_func FUERA
    de la ejecución del script, donde st.session_state (el reloj fijo) no
    está. Las etiquetas deben salir del reloj fijo y no del real. El reloj
    está en el pasado (2020), así que la fecha real nunca coincide con él."""
    past = datetime(2020, 6, 10, 10, 30, tzinfo=ZoneInfo("America/New_York"))
    at = load(choose_ticker(data_app(tmp_path, FakeProvider(today=past), past), "ETF", "SPY"))
    assert not at.exception
    select = at.selectbox(key="expiry_choice")
    expiries = sorted(at.session_state["snapshot"].chains)
    # Llamada directa fuera de la ejecución del script, como hace AppTest.
    assert select.format_func(expiries[0]) == f"{expiries[0]} (10 días)"
    select.set_value(expiries[1]).run()
    assert not at.exception
    assert at.session_state["expiry_choice"] == expiries[1]


def test_missing_dividend_yield_sets_q_zero_with_caption(tmp_path):
    provider = FakeProvider(today=FIXED_NOW, dividend_yield=None)
    at = data_app(tmp_path, provider)
    at.session_state["q_pct"] = 2.0
    at = load(choose_ticker(at, "Acción", "AAPL"))
    assert not at.exception
    assert at.session_state["q_pct"] == 0.0
    assert MSG_Q_MISSING in captions(at)
    assert not at.error


def test_index_load_keeps_q_and_shows_note(tmp_path):
    at = choose_ticker(data_app(tmp_path), "Índice", "SPX")
    at.number_input(key="q_pct").set_value(1.2).run()
    at = load(at)
    assert not at.exception
    assert at.session_state["snapshot"].ticker == "SPX"
    assert at.session_state["q_pct"] == 1.2  # C10: q no se toca
    assert at.session_state["rate_pct"] == 4.12
    assert MSG_Q_INDEX in captions(at)
    assert "sin dividend yield para índices: edítalo, SPX ≈ 1,2 %" in captions(at)
    # Caché con la etiqueta curada, nunca con "^".
    assert (tmp_path / "SPX.json").exists()
    assert not (tmp_path / "^SPX.json").exists()


def test_provider_error_without_cache_shows_spanish_error(tmp_path):
    before = 100.0
    at = data_app(tmp_path, FakeProvider(today=FIXED_NOW, fail_with=NetworkError))
    at = load(choose_ticker(at, "ETF", "SPY"))
    assert not at.exception
    assert at.session_state["snapshot"] is None
    assert at.session_state["spot"] == before
    errors = [error.value for error in at.error]
    assert MSG_NETWORK in errors and MSG_NO_CACHE in errors
    assert expiry_selects(at) == []


def test_provider_error_with_cache_uses_saved_data(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    saved_spot = at.session_state["snapshot"].spot
    # El proveedor cae; la segunda carga recurre a la caché guardada.
    at.session_state["data_provider"] = FakeProvider(today=FIXED_NOW, fail_with=NetworkError)
    at.session_state["spot"] = 50.0
    at = load(at)
    assert not at.exception
    snapshot = at.session_state["snapshot"]
    assert snapshot is not None and snapshot.source == "cache"
    assert at.session_state["spot"] == pytest.approx(saved_spot)
    when = FIXED_NOW.astimezone().strftime("%d/%m %H:%M")
    assert f"datos guardados de {when}" in captions(at)
    assert MSG_NETWORK in [warning.value for warning in at.warning]
    assert not at.error
    assert expiry_selects(at)


def test_curated_ticker_without_expirations_suggests_source_problem(tmp_path):
    at = data_app(tmp_path, FakeProvider(today=FIXED_NOW, offsets=()))
    at = load(choose_ticker(at, "ETF", "SPY"))
    assert not at.exception
    errors = [error.value for error in at.error]
    assert (
        "Yahoo no devolvió datos para SPY: puede ser un problema temporal de la "
        "fuente o de la conexión; prueba más tarde."
    ) in errors
    assert at.session_state["snapshot"] is None


def test_underlying_change_resets_ticker_and_clears_snapshot(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    assert at.session_state["snapshot"] is not None
    at.selectbox(key="underlying").set_value("Acción").run()
    assert not at.exception
    assert at.session_state["ticker_choice"] == "Entrada manual"
    assert at.session_state["snapshot"] is None
    assert at.session_state["load_notice"] == []
    assert at.button(key="load_data").disabled
    assert expiry_selects(at) == []


def test_ticker_change_same_kind_clears_loaded_data(tmp_path):
    # C-V1: SPY cargado -> QQQ sin pulsar "Cargar datos".
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    assert expiry_selects(at)
    at.selectbox(key="ticker_choice").set_value("QQQ").run()
    assert not at.exception
    assert at.session_state["snapshot"] is None
    assert at.session_state.get("expiry_choice") is None
    assert at.session_state["load_notice"] == []
    assert expiry_selects(at) == []
    assert not any("cargados a las" in text for text in captions(at))
    assert not at.button(key="load_data").disabled


# ---------------------------------------------------------------------------
# Etapa C1, bloque 6: selector de patas reales, premium_source, IV de Yahoo
# como referencia y aviso de vencimiento distinto.
# ---------------------------------------------------------------------------

PICKER_LABEL = "Añadir pata desde la cadena real"


def picker_shown(at: AppTest) -> bool:
    return PICKER_LABEL in [expander.label for expander in at.expander]


def add_real_leg(at: AppTest, kind: str = "call", strike: float = 700.0) -> dict:
    """Añade una pata desde la cadena real y devuelve la pata nueva."""
    at.selectbox(key="pick_kind").set_value(kind).run()
    at.selectbox(key="pick_strike").set_value(strike).run()
    at.button(key="add_market_leg").click().run()
    assert not at.exception
    return at.session_state["legs"][-1]


def test_manual_mode_has_no_chain_picker(app):
    assert not picker_shown(app)
    assert not any(str(button.key) == "add_market_leg" for button in app.button)
    # Las patas normales no tienen origen de mercado.
    assert all(leg["premium_source"] is None for leg in app.session_state["legs"])


def test_chain_picker_disappears_when_ticker_changes(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    assert picker_shown(at)
    at.selectbox(key="ticker_choice").set_value("QQQ").run()
    assert not at.exception
    assert not picker_shown(at)


def test_market_leg_caption_and_manual_edit(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    leg = add_real_leg(at)
    assert f"Pata 2: precio mercado (mid de bid {leg['bid']:.2f} / ask {leg['ask']:.2f})." in captions(at)
    # El usuario edita la prima: deja de ser "de mercado".
    at.number_input(key=f"leg_{leg['id']}_price").set_value(20.0).run()
    edited = at.session_state["legs"][-1]
    assert edited["premium_source"] == "manual"
    assert edited["price"] == 20.0 and edited["premium_manual"]
    assert "Pata 2: precio manual." in captions(at)


def test_reset_clears_market_source(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    leg = add_real_leg(at)
    at.button(key=f"leg_{leg['id']}_reset").click().run()
    reset = at.session_state["legs"][-1]
    assert not reset["premium_manual"]
    assert reset["premium_source"] is None and reset["iv_yahoo"] is None
    assert reset["price"] == pytest.approx(default_premium("call", app_market(at, "binomial"), 700.0))


def test_kind_change_clears_market_source(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    leg = add_real_leg(at)
    at.selectbox(key=f"leg_{leg['id']}_kind").set_value("put").run()
    changed = at.session_state["legs"][-1]
    assert not changed["premium_manual"]
    assert changed["premium_source"] is None and changed["expiry"] is None


def test_strike_edit_turns_market_leg_into_manual(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    leg = add_real_leg(at)
    at.number_input(key=f"leg_{leg['id']}_strike").set_value(705.0).run()
    edited = at.session_state["legs"][-1]
    assert edited["premium_source"] == "manual" and edited["premium_manual"]
    assert edited["price"] == pytest.approx(leg["price"])
    assert edited["iv_yahoo"] is None


def test_yahoo_iv_only_shown_as_reference(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    leg = add_real_leg(at)
    texts = expander_texts(scenarios_expander(at))
    reference = f"IV Yahoo (referencia): {leg['iv_yahoo'] * 100:.2f} %"
    assert reference in texts
    # Solo aparece con el rótulo "referencia"; la IV del motor va aparte.
    assert sum("IV Yahoo" in text for text in texts) == 1
    assert any("Pata 2 (Call, strike 700.00): volatilidad implícita" in text for text in texts)


def test_expiry_mismatch_shows_warning_and_keeps_leg(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    leg = add_real_leg(at)
    assert not any("vencimiento elegido" in w.value for w in at.warning)
    other = (FIXED_NOW.date() + timedelta(days=45)).isoformat()
    expiry_selects(at)[0].set_value(other).run()
    assert not at.exception
    warnings = [w.value for w in at.warning]
    assert any(
        f"Pata 2: su cotización es del vencimiento {leg['expiry']}" in w and other in w
        for w in warnings
    )
    assert at.session_state["legs"][-1]["id"] == leg["id"]


# ---------------------------------------------------------------------------
# Etapa C1, bloque 7: flujo completo de principio a fin (AC-C1-2, AC-C1-16).
# FakeProvider + reloj fijo + caché en tmp_path: nunca red ni .cache_datos real.
# ---------------------------------------------------------------------------

import math  # noqa: E402

NAN_RE = re.compile(r"\bnan\b|\binf\b", re.IGNORECASE)


def shown_texts(at: AppTest) -> list[str]:
    """Todos los textos de resultados: métricas, markdown, captions y tablas."""
    texts = [metric.value for metric in at.metric]
    texts += [md.value for md in at.markdown]
    texts += captions(at)
    for table in at.table:
        texts += [str(value) for value in table.value.to_numpy().ravel()]
    return texts


def assert_analysis_ok(at: AppTest) -> None:
    """La app dibujó el análisis completo, sin excepción, error ni NaN."""
    assert not at.exception
    assert not at.error
    assert "Beneficio máximo" in [metric.label for metric in at.metric]
    assert len(at.get("plotly_chart")) == 2
    assert scenarios_expander(at) is not None
    bad = [text for text in shown_texts(at) if NAN_RE.search(str(text))]
    assert bad == []
    for leg in at.session_state["legs"]:
        assert math.isfinite(leg["price"]) and math.isfinite(leg["strike"])


def near_spot_strike(at: AppTest) -> float:
    """Strike líquido ofrecido más cercano al spot cargado."""
    spot = at.session_state["snapshot"].spot
    return min(at.selectbox(key="pick_strike").options, key=lambda s: abs(float(s.split()[0]) - spot))


def test_e2e_load_choose_expiry_add_real_leg_and_analyze(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    assert_analysis_ok(at)
    # Elegir otro vencimiento ofrecido (45 días) antes de añadir la pata.
    target = (FIXED_NOW.date() + timedelta(days=45)).isoformat()
    expiry_selects(at)[0].set_value(target).run()
    assert at.session_state["days"] == 45
    at.selectbox(key="pick_kind").set_value("put").run()
    strike = float(near_spot_strike(at).split()[0])
    leg = add_real_leg(at, "put", strike)
    assert leg["premium_source"] == "mercado" and leg["expiry"] == target
    assert leg["price"] == pytest.approx((leg["bid"] + leg["ask"]) / 2)
    assert_analysis_ok(at)
    assert not any("vencimiento elegido" in w.value for w in at.warning)
    # La pata inicial y la pata real conviven en el análisis.
    assert len(at.session_state["legs"]) == 2


def test_e2e_switch_spy_to_qqq_shows_no_spy_chain(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    add_real_leg(at)
    at.selectbox(key="ticker_choice").set_value("QQQ").run()
    assert not at.exception
    assert at.session_state["snapshot"] is None
    assert not picker_shown(at)
    assert expiry_selects(at) == []
    # Nada de la cadena de SPY sigue a la vista.
    assert not any("cargados a las" in text or "Solo opciones líquidas" in text for text in captions(at))
    # La pata ya añadida se conserva y el análisis sigue funcionando.
    assert_analysis_ok(at)


def test_e2e_network_error_with_cache_still_analyzes(tmp_path):
    at = load(choose_ticker(data_app(tmp_path), "ETF", "SPY"))
    at.session_state["data_provider"] = FakeProvider(today=FIXED_NOW, fail_with=NetworkError)
    at = load(at)
    assert at.session_state["snapshot"].source == "cache"
    assert MSG_NETWORK in [warning.value for warning in at.warning]
    leg = add_real_leg(at)
    assert leg["premium_source"] == "mercado"
    assert_analysis_ok(at)


def test_e2e_network_error_without_cache_keeps_manual_analysis(tmp_path):
    at = data_app(tmp_path, FakeProvider(today=FIXED_NOW, fail_with=NetworkError))
    at = load(choose_ticker(at, "ETF", "SPY"))
    assert not at.exception
    errors = [error.value for error in at.error]
    assert MSG_NETWORK in errors and MSG_NO_CACHE in errors
    assert not picker_shown(at)
    # El análisis con los datos manuales sigue dibujándose.
    assert "Beneficio máximo" in [metric.label for metric in at.metric]
    assert [text for text in shown_texts(at) if NAN_RE.search(str(text))] == []
    assert list(tmp_path.iterdir()) == []


def test_e2e_index_with_c10_note_and_real_leg(tmp_path):
    at = choose_ticker(data_app(tmp_path), "Índice", "SPX")
    at.number_input(key="q_pct").set_value(1.2).run()
    at = load(at)
    assert at.session_state["q_pct"] == 1.2
    assert MSG_Q_INDEX in captions(at)
    strike = float(near_spot_strike(at).split()[0])
    leg = add_real_leg(at, "call", strike)
    assert leg["premium_source"] == "mercado"
    assert_analysis_ok(at)


def test_e2e_manual_mode_identical_with_data_layer_injected(app, tmp_path):
    # Con proveedor, caché y reloj inyectados pero sin cargar nada, la app
    # muestra exactamente lo mismo que la app recién abierta (AC-C1-2).
    data = data_app(tmp_path)
    assert not data.exception
    assert [(m.label, m.value) for m in data.metric] == [(m.label, m.value) for m in app.metric]
    assert [md.value for md in data.markdown] == [md.value for md in app.markdown]
    assert data.session_state["legs"] == app.session_state["legs"]
    assert list(tmp_path.iterdir()) == []
