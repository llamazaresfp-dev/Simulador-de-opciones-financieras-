"""Tests de validación de entradas y avisos (bloque 4: AC1, AC17, decisión 13).

Comprobamos que cada dato inválido produce un mensaje de error en
español, que días = 0 NO es un error (solo un aviso) y que los avisos
dependen del tipo de subyacente.
"""

import math

import pytest

from opciones import MIN_VOL, Leg, Market, market_warnings, validate_legs, validate_market


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


@pytest.mark.parametrize("underlying", ["Acción", "ETF"])
def test_stock_and_etf_warn_about_american_options(underlying):
    warnings = market_warnings(market(underlying=underlying))
    american = [w for w in warnings if "americanas" in w]
    assert len(american) == 1
    assert "puts" in american[0]
    assert "7 %" in american[0]
    assert not any("europeas" in w for w in warnings)


def test_index_says_european_options():
    warnings = market_warnings(market(underlying="Índice"))
    assert any("europeas" in w for w in warnings)
    assert not any("americanas" in w for w in warnings)


@pytest.mark.parametrize("underlying", ["Acción", "ETF", "Índice"])
def test_always_says_not_advice(underlying):
    warnings = market_warnings(market(underlying=underlying))
    assert_spanish_messages(warnings)
    assert any("no asesoría" in w for w in warnings)


def test_close_commission_note_is_present():
    warnings = market_warnings(market())
    assert any("cierre" in w and "con valor" in w for w in warnings)


def test_warnings_do_not_crash_with_invalid_market():
    # La interfaz puede pedir avisos aunque haya errores: no debe fallar.
    assert_spanish_messages(market_warnings(market(days=None, underlying="Bono")))
