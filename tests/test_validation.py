"""Tests de validación de entradas y avisos (bloque 4: AC1, AC17, decisión 13).

Comprobamos que cada dato inválido produce un mensaje de error en
español, que días = 0 NO es un error (solo un aviso) y que los avisos
dependen del tipo de subyacente.
"""

import math

import pytest

from opciones import (
    MIN_VOL,
    Leg,
    Market,
    SimulationSettings,
    market_warnings,
    scenario_warnings,
    validate_legs,
    validate_market,
    validate_simulation,
)
from opciones.validation import (
    MSG_AMERICAN,
    MSG_BAD_PRICING_MODEL,
    MSG_BINOMIAL_ACTIVE,
    MSG_EUROPEAN,
    MSG_SCENARIO_AMERICAN,
)


def market(**changes):
    """Mercado válido por defecto; 'changes' sustituye los campos indicados."""
    data = dict(underlying="Acción", spot=100.0, vol=0.20, days=30, rate=0.05, q=0.0)
    data.update(changes)
    return Market(**data)


def call(**changes):
    data = dict(kind="call", side=1, quantity=1, strike=100.0, price=2.5)
    data.update(changes)
    return Leg(**data)


def stock(**changes):
    data = dict(kind="stock", side=1, quantity=100, strike=None, price=100.0)
    data.update(changes)
    return Leg(**data)


def assert_spanish_messages(messages):
    """Cada mensaje debe ser texto no vacío."""
    assert messages
    for message in messages:
        assert isinstance(message, str)
        assert message.strip()


# --- Mercado -----------------------------------------------------------------


def test_valid_market_has_no_errors():
    assert validate_market(market()) == []


def test_negative_days_is_error():
    errors = validate_market(market(days=-1))
    assert_spanish_messages(errors)
    assert any("días" in e for e in errors)


def test_zero_days_is_not_error_but_warns():
    assert validate_market(market(days=0)) == []
    warnings = market_warnings(market(days=0))
    assert any("0" in w and "intrínseco" in w for w in warnings)


def test_positive_days_has_no_zero_days_warning():
    warnings = market_warnings(market(days=30))
    assert not any("intrínseco" in w for w in warnings)


@pytest.mark.parametrize("vol", [0.0, MIN_VOL / 2, -0.2])
def test_vol_below_minimum_is_error(vol):
    errors = validate_market(market(vol=vol))
    assert_spanish_messages(errors)
    assert any("volatilidad" in e for e in errors)


def test_vol_at_minimum_is_valid():
    assert validate_market(market(vol=MIN_VOL)) == []


@pytest.mark.parametrize("spot", [0.0, -5.0])
def test_spot_zero_or_negative_is_error(spot):
    errors = validate_market(market(spot=spot))
    assert_spanish_messages(errors)
    assert any("spot" in e for e in errors)


@pytest.mark.parametrize("field", ["spot", "vol", "days", "rate", "q"])
@pytest.mark.parametrize("empty", [None, "", "abc", math.nan])
def test_empty_or_non_numeric_market_field_is_error(field, empty):
    errors = validate_market(market(**{field: empty}))
    assert_spanish_messages(errors)


def test_unknown_underlying_is_error():
    assert_spanish_messages(validate_market(market(underlying="Bono")))


def test_missing_market_is_error():
    assert_spanish_messages(validate_market(None))


def test_several_errors_are_all_reported():
    errors = validate_market(market(spot=-1, vol=0, days=-3))
    assert len(errors) == 3


# --- Patas -------------------------------------------------------------------


def test_valid_legs_have_no_errors():
    assert validate_legs([call(), call(kind="put", side=-1), stock()]) == []


@pytest.mark.parametrize("legs", [[], None])
def test_no_legs_is_clear_error(legs):
    errors = validate_legs(legs)
    assert_spanish_messages(errors)
    assert any("patas" in e for e in errors)


@pytest.mark.parametrize("strike", [-100.0, 0.0, None, ""])
def test_bad_strike_is_error(strike):
    errors = validate_legs([call(strike=strike)])
    assert_spanish_messages(errors)
    assert any("strike" in e for e in errors)


@pytest.mark.parametrize("price", [-1.0, None, ""])
def test_bad_premium_is_error(price):
    errors = validate_legs([call(price=price)])
    assert_spanish_messages(errors)
    assert any("prima" in e for e in errors)


@pytest.mark.parametrize("price", [-1.0, None])
def test_bad_stock_price_is_error(price):
    assert_spanish_messages(validate_legs([stock(price=price)]))


def test_zero_premium_is_valid():
    assert validate_legs([call(price=0.0)]) == []


@pytest.mark.parametrize("quantity", [-1, 0, None, ""])
def test_bad_quantity_is_error(quantity):
    errors = validate_legs([call(quantity=quantity)])
    assert_spanish_messages(errors)
    assert any("cantidad" in e for e in errors)


def test_bad_kind_and_side_are_errors():
    assert_spanish_messages(validate_legs([call(kind="future")]))
    assert_spanish_messages(validate_legs([call(side=0)]))


def test_error_names_the_leg_number():
    errors = validate_legs([call(), call(strike=-5)])
    assert errors and all(e.startswith("Pata 2") for e in errors)


# --- Avisos por subyacente (AC17) -------------------------------------------


# Etapa B1 (AC-B12): el aviso de Acción/ETF depende del modelo activo.
# Antes (Etapa A) este test exigía «7 %» con Black-Scholes; ahora el
# helper market() usa el modelo por defecto (binomial) y el texto de
# Black-Scholes cita «1–8 %» y «24 %» (se prueba más abajo).
@pytest.mark.parametrize("underlying", ["Acción", "ETF"])
def test_stock_and_etf_warn_about_american_options(underlying):
    warnings = market_warnings(market(underlying=underlying))
    american = [w for w in warnings if "americanas" in w]
    assert len(american) == 1
    assert not any("europeas" in w for w in warnings)


@pytest.mark.parametrize("underlying", ["Acción", "ETF"])
def test_binomial_active_warning(underlying):
    warnings = market_warnings(market(underlying=underlying, pricing_model="binomial"))
    binomial = [w for w in warnings if "binomial" in w]
    assert len(binomial) == 1
    text = binomial[0]
    assert "americano" in text and "aproximación binomial" in text
    for word in ("primas", "«hoy»", "griegas", "volatilidad implícita"):
        assert word in text
    assert not any("subvalora" in w for w in warnings)


def test_default_model_shows_binomial_warning():
    # El modelo por defecto de Market es el binomial.
    assert MSG_BINOMIAL_ACTIVE in market_warnings(market(underlying="Acción"))


@pytest.mark.parametrize("underlying", ["Acción", "ETF"])
def test_black_scholes_warns_about_underpriced_puts(underlying):
    warnings = market_warnings(market(underlying=underlying, pricing_model="black_scholes"))
    bs = [w for w in warnings if "Black-Scholes" in w]
    assert len(bs) == 1
    text = bs[0]
    assert "subvalora los puts americanos" in text
    assert "1–8 %" in text and "24 %" in text
    assert not any("aproximación binomial" in w for w in warnings)
    assert not any("europeas" in w for w in warnings)


@pytest.mark.parametrize("pricing_model", ["binomial", "black_scholes", "otro"])
def test_index_says_european_options(pricing_model):
    warnings = market_warnings(market(underlying="Índice", pricing_model=pricing_model))
    assert MSG_EUROPEAN in warnings
    assert any("europeas" in w for w in warnings)
    assert not any("americanas" in w for w in warnings)
    assert not any("binomial" in w for w in warnings)


def test_index_european_text_unchanged():
    assert MSG_EUROPEAN == (
        "Las opciones sobre índices son europeas (solo se ejercen al vencimiento): "
        "Black-Scholes es el modelo adecuado."
    )


@pytest.mark.parametrize("underlying", ["Acción", "ETF", "Índice"])
@pytest.mark.parametrize("pricing_model", ["binomial", "black_scholes"])
def test_always_says_not_advice(underlying, pricing_model):
    warnings = market_warnings(market(underlying=underlying, pricing_model=pricing_model))
    assert_spanish_messages(warnings)
    assert any("no asesoría" in w for w in warnings)
    assert any("cierre" in w and "con valor" in w for w in warnings)


def test_close_commission_note_is_present():
    warnings = market_warnings(market())
    assert any("cierre" in w and "con valor" in w for w in warnings)


def test_market_warning_messages_are_distinct():
    assert len({MSG_BINOMIAL_ACTIVE, MSG_AMERICAN, MSG_EUROPEAN}) == 3


# --- Modelo de valoración (Etapa B1) ------------------------------------------


@pytest.mark.parametrize("pricing_model", ["binomial", "black_scholes"])
@pytest.mark.parametrize("underlying", ["Acción", "ETF", "Índice"])
def test_valid_pricing_models_are_accepted(pricing_model, underlying):
    assert validate_market(market(underlying=underlying, pricing_model=pricing_model)) == []


@pytest.mark.parametrize("pricing_model", ["otro", "", None, 3, "Binomial"])
def test_unknown_pricing_model_is_error(pricing_model):
    errors = validate_market(market(pricing_model=pricing_model))
    assert errors == [MSG_BAD_PRICING_MODEL]
    assert "modelo de valoración" in errors[0]


def test_unknown_pricing_model_warnings_do_not_crash():
    assert_spanish_messages(market_warnings(market(pricing_model="otro")))


def test_warnings_do_not_crash_with_invalid_market():
    # La interfaz puede pedir avisos aunque haya errores: no debe fallar.
    assert_spanish_messages(market_warnings(market(days=None, underlying="Bono")))


# --- Escenarios: validate_simulation (Etapa A, decisión A11) -----------------


def sim(**changes):
    """Ajustes de simulación válidos por defecto."""
    data = dict(n_paths=100_000, seed=42, mu=None)
    data.update(changes)
    return SimulationSettings(**data)


def test_valid_simulation_has_no_errors():
    assert validate_simulation(market(), [call()], sim()) == []


def test_default_simulation_settings_are_valid():
    assert validate_simulation(market(), [call()], SimulationSettings()) == []


@pytest.mark.parametrize("n_paths", [999, 1_000_001, 0, -5, 1.5, 1000.0, "a", None, True, math.nan])
def test_bad_n_paths_is_error(n_paths):
    errors = validate_simulation(market(), [call()], sim(n_paths=n_paths))
    assert_spanish_messages(errors)
    assert any("simulaciones" in e for e in errors)


@pytest.mark.parametrize("n_paths", [1_000, 1_000_000])
def test_n_paths_limits_are_valid(n_paths):
    assert validate_simulation(market(), [call()], sim(n_paths=n_paths)) == []


@pytest.mark.parametrize("seed", [-1, 2**32, 1.5, "a", None, True, False, math.inf])
def test_bad_seed_is_error(seed):
    errors = validate_simulation(market(), [call()], sim(seed=seed))
    assert_spanish_messages(errors)
    assert any("semilla" in e for e in errors)


@pytest.mark.parametrize("seed", [0, 2**32 - 1])
def test_seed_limits_are_valid(seed):
    assert validate_simulation(market(), [call()], sim(seed=seed)) == []


@pytest.mark.parametrize("mu", [-0.51, 1.01, math.nan, math.inf, -math.inf, "a", True])
def test_bad_mu_is_error(mu):
    errors = validate_simulation(market(), [call()], sim(mu=mu))
    assert_spanish_messages(errors)
    assert any("crecimiento esperado" in e for e in errors)


@pytest.mark.parametrize("mu", [-0.5, 1.0, 0, 0.05, None])
def test_mu_limits_and_empty_are_valid(mu):
    assert validate_simulation(market(), [call()], sim(mu=mu)) == []


def test_zero_days_is_error_for_scenarios_only():
    # El MVP acepta días = 0; los escenarios no (no hay distribución).
    assert validate_market(market(days=0)) == []
    errors = validate_simulation(market(days=0), [call()], sim())
    assert_spanish_messages(errors)
    assert any("no hay distribución" in e for e in errors)


def test_zero_vol_reuses_existing_market_message():
    existing = validate_market(market(vol=0.0))
    errors = validate_simulation(market(vol=0.0), [call()], sim())
    assert existing
    for message in existing:
        assert message in errors


@pytest.mark.parametrize("legs", [[], None])
def test_no_legs_reuses_existing_message(legs):
    errors = validate_simulation(market(), legs, sim())
    assert errors == validate_legs(legs)


def test_bad_leg_reuses_existing_message():
    errors = validate_simulation(market(), [call(strike=0)], sim())
    assert errors == validate_legs([call(strike=0)])


def test_missing_market_or_settings_do_not_crash():
    assert_spanish_messages(validate_simulation(None, [call()], sim()))
    errors = validate_simulation(market(), [call()], None)
    assert_spanish_messages(errors)
    assert any("ajustes de la simulación" in e for e in errors)


def test_several_simulation_errors_are_all_reported():
    errors = validate_simulation(market(days=0), [call()], sim(n_paths=5, seed=-1, mu=2.0))
    assert len(errors) == 4


def test_simulation_messages_are_distinct():
    messages = set()
    for changes in [dict(n_paths=5), dict(seed=-1), dict(mu=2.0)]:
        messages.update(validate_simulation(market(), [call()], sim(**changes)))
    messages.update(validate_simulation(market(days=0), [call()], sim()))
    assert len(messages) == 4


# --- Escenarios: scenario_warnings (AC-A15, decisión A10) --------------------


@pytest.mark.parametrize("underlying", ["Acción", "ETF", "Índice"])
def test_scenario_warnings_always_present(underlying):
    warnings = scenario_warnings(market(underlying=underlying))
    assert_spanish_messages(warnings)
    assert any("no una predicción" in w for w in warnings)
    assert any("colas más gruesas" in w and "lognormal" in w for w in warnings)
    assert MSG_NOT_ADVICE_TEXT in warnings


# Etapa B1 (AC-B12): antes este test exigía que el aviso dijera que la IV
# y la simulación «quedan sesgadas»; ahora la IV usa el modelo americano y
# el aviso dice que solo queda el modelo lognormal de precio final de
# estilo europeo, donde el ejercicio anticipado no importa al vencimiento.
@pytest.mark.parametrize("underlying", ["Acción", "ETF"])
@pytest.mark.parametrize("pricing_model", ["binomial", "black_scholes"])
def test_scenario_warnings_american_bias(underlying, pricing_model):
    warnings = scenario_warnings(market(underlying=underlying, pricing_model=pricing_model))
    american = [w for w in warnings if "americanas" in w]
    assert american == [MSG_SCENARIO_AMERICAN]
    text = american[0]
    assert "lognormal" in text and "precio final" in text and "europeo" in text
    assert "ejercicio anticipado" in text and "vencimiento" in text
    assert "sesgad" not in text
    assert not any("europeas" in w for w in warnings)


@pytest.mark.parametrize("pricing_model", ["binomial", "black_scholes"])
def test_scenario_warnings_index_is_european(pricing_model):
    warnings = scenario_warnings(market(underlying="Índice", pricing_model=pricing_model))
    assert MSG_EUROPEAN in warnings
    assert any("europeas" in w for w in warnings)
    assert not any("americanas" in w for w in warnings)


def test_scenario_warnings_do_not_crash_with_invalid_market():
    assert_spanish_messages(scenario_warnings(None))
    assert_spanish_messages(scenario_warnings(market(underlying="Bono", days=None)))


# Mismo texto de "no es asesoría" que market_warnings (coherencia con el MVP).
MSG_NOT_ADVICE_TEXT = market_warnings(market())[0]
