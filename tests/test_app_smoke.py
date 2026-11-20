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


def test_app_loads_without_exception(app):
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Catálogo", "Constructor", "Ajustes"]
    # Con los datos por defecto hay una pata y se dibuja el gráfico.
    assert len(app.get("plotly_chart")) == 1
    assert not app.error


def test_open_template_fills_legs_and_switches_to_builder(app):
    app.button(key="open_iron_condor").click().run()

    assert not app.exception
    assert app.session_state["main_tab"] == "Constructor"
    legs = app.session_state["legs"]
    assert len(legs) == 4
    assert [leg["kind"] for leg in legs] == ["put", "put", "call", "call"]
    assert all(not leg["premium_manual"] for leg in legs)
    assert len(app.get("plotly_chart")) == 1


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
    assert not app.error
    notices = [info.value for info in app.info]
    assert any(text.startswith("Días al vencimiento = 0") for text in notices)
    assert len(app.get("plotly_chart")) == 1
    # Sin griegas: la tabla muestra "—".
    assert set(app.table[0].value["Valor"]) == {"—"}


def test_zero_volatility_shows_error_and_no_chart(app):
    app.number_input(key="vol_pct").set_value(0.0).run()

    assert not app.exception
    errors = [error.value for error in app.error]
    assert any("volatilidad" in text for text in errors)
    assert len(app.get("plotly_chart")) == 0
