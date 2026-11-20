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

from opciones.validation import (
    MSG_BAD_MU,
    MSG_BAD_PATHS,
    MSG_BAD_SEED,
    MSG_FAT_TAILS,
    MSG_MODEL,
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


def test_no_today_inside_scenarios_expander(app):
    """AC-A7: dentro del desplegable no hay nada de la curva «hoy»."""
    expander = scenarios_expander(app)
    for text in expander_texts(expander):
        assert "hoy" not in text.lower()
    chart = expander.get("plotly_chart")[0]
    assert "Hoy" not in chart.proto.spec


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
