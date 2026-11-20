"""Tests de comisiones (bloque 2).

Casos calculados a mano con los valores por defecto:
0,65 USD por contrato, +0,60 USD si el subyacente es un índice.
"""

import numpy as np
import pytest

from opciones import CommissionSettings, Leg, Market
from opciones.commissions import close_fee_expiry, close_fee_today, open_fee


def stock_market():
    return Market(underlying="Acción", spot=100, vol=0.20, days=30, rate=0.05)


def index_market():
    return Market(underlying="Índice", spot=100, vol=0.20, days=30, rate=0.05)


def long_call(quantity=1, strike=100):
    return Leg(kind="call", side=1, quantity=quantity, strike=strike, price=2.0)


def short_put(quantity=1, strike=100):
    return Leg(kind="put", side=-1, quantity=quantity, strike=strike, price=2.0)


def stock_leg():
    return Leg(kind="stock", side=1, quantity=100, strike=None, price=100.0)


# --- Comisión de apertura (AC13) ---------------------------------------

def test_open_fee_default_is_065_per_contract():
    assert open_fee(long_call(), stock_market(), CommissionSettings()) == pytest.approx(0.65)


def test_open_fee_index_adds_surcharge():
    # 0,65 + 0,60 = 1,25 por contrato en índices.
    assert open_fee(long_call(), index_market(), CommissionSettings()) == pytest.approx(1.25)


def test_open_fee_scales_with_quantity():
    assert open_fee(long_call(quantity=3), stock_market(), CommissionSettings()) == pytest.approx(1.95)
    assert open_fee(long_call(quantity=3), index_market(), CommissionSettings()) == pytest.approx(3.75)


def test_open_fee_same_for_short_side():
    # Vender también paga comisión (no depende de la dirección).
    assert open_fee(short_put(), stock_market(), CommissionSettings()) == pytest.approx(0.65)


def test_stock_pays_no_commission():
    settings = CommissionSettings()
    assert open_fee(stock_leg(), stock_market(), settings) == 0.0
    assert close_fee_today(stock_leg(), stock_market(), settings) == 0.0
    fees = close_fee_expiry(stock_leg(), np.array([50.0, 100.0, 150.0]), stock_market(), settings)
    assert np.all(fees == 0.0)


# --- Comisión de cierre al vencimiento (decisión 6) ---------------------

def test_call_at_strike_has_no_close_fee():
    # S = K: la call vence sin valor, no hay que cerrarla.
    fee = close_fee_expiry(long_call(), 100.0, stock_market(), CommissionSettings())
    assert fee == 0.0


def test_call_just_above_strike_pays_close_fee():
    fee = close_fee_expiry(long_call(), 100.01, stock_market(), CommissionSettings())
    assert fee == pytest.approx(0.65)


def test_put_just_below_strike_pays_close_fee():
    fee = close_fee_expiry(short_put(), 99.99, stock_market(), CommissionSettings())
    assert fee == pytest.approx(0.65)


def test_put_at_strike_has_no_close_fee():
    fee = close_fee_expiry(short_put(), 100.0, stock_market(), CommissionSettings())
    assert fee == 0.0


def test_worthless_options_have_no_close_fee():
    settings = CommissionSettings()
    assert close_fee_expiry(long_call(), 80.0, stock_market(), settings) == 0.0
    assert close_fee_expiry(short_put(), 120.0, stock_market(), settings) == 0.0


def test_close_fee_expiry_is_vectorised():
    S = np.array([90.0, 100.0, 100.01, 110.0])
    fees = close_fee_expiry(long_call(quantity=2), S, index_market(), CommissionSettings())
    assert fees == pytest.approx([0.0, 0.0, 2.50, 2.50])


def test_include_close_false_only_open_fee():
    settings = CommissionSettings(include_close=False)
    assert open_fee(long_call(), stock_market(), settings) == pytest.approx(0.65)
    assert close_fee_expiry(long_call(), 150.0, stock_market(), settings) == 0.0
    assert close_fee_today(long_call(), stock_market(), settings) == 0.0


# --- Comisión de cierre en la curva "hoy" (decisión 14) -----------------

def test_today_close_fee_charged_even_far_out_of_the_money():
    # Liquidar hoy significa cerrar todas las patas de opción, valgan lo que valgan.
    far_otm_call = long_call(strike=500)
    assert close_fee_today(far_otm_call, stock_market(), CommissionSettings()) == pytest.approx(0.65)
    assert close_fee_today(far_otm_call, index_market(), CommissionSettings()) == pytest.approx(1.25)


def test_today_close_fee_scales_with_quantity():
    fee = close_fee_today(short_put(quantity=4), stock_market(), CommissionSettings())
    assert fee == pytest.approx(2.60)
