"""Tests de la volatilidad implícita (Etapa A, bloque 1: AC-A11, AC-A12).

La idea: si calculamos un precio con Black-Scholes y una sigma, la IV
de ese precio debe devolvernos un número que reproduce el precio
(ida y vuelta precio -> IV -> precio). Además, cuando no existe IV,
la función devuelve un mensaje en español, nunca un número falso ni
una excepción.
"""

import math
import sys

import pytest

from opciones import IVResult, Leg, Market, bs_price, implied_vol
from opciones.implied_vol import (
    MSG_ABOVE_UPPER_BOUND,
    MSG_BELOW_LOWER_BOUND,
    MSG_INVALID_DATA,
    MSG_NO_TIME,
    MSG_PREMIUM_NOT_POSITIVE,
    MSG_SOLVER_FAILED,
    MSG_STOCK_LEG,
)

SPOT = 100.0
RATE = 0.04
Q = 0.01

STRIKES = (70, 85, 95, 100, 105, 115, 130)
SIGMAS = (0.01, 0.05, 0.25, 1.0, 3.0)
DAYS = (1, 45)


def make_market(days=45, vol=0.25, rate=RATE, q=Q, spot=SPOT):
    # Etapa B1: fijado a Black-Scholes (estos tests son la IV europea de la Etapa A).
    return Market(underlying="Acción", spot=spot, vol=vol, days=days, rate=rate, q=q,
                  pricing_model="black_scholes")


def option_leg(kind, strike, premium):
    return Leg(kind=kind, side=1, quantity=1, strike=strike, price=premium)


def model_price(kind, market, strike, sigma):
    return bs_price(kind, market.spot, strike, market.rate, market.q, sigma, market.T)


def bounds(kind, market, strike):
    """Límites sin arbitraje (inferior, superior) de la prima."""
    stock_pv = market.spot * math.exp(-market.q * market.T)
    strike_pv = strike * math.exp(-market.rate * market.T)
    if kind == "call":
        return max(stock_pv - strike_pv, 0.0), stock_pv
    return max(strike_pv - stock_pv, 0.0), strike_pv


def sigma_check_applies(kind, strike, days):
    """Enmienda A1: |iv − σ| solo es exigible donde la vega no es casi 0.

    ATM y OTM siempre; ITM solo cerca del dinero (~5 %) con T = 45 días.
    """
    out_or_at = strike >= SPOT if kind == "call" else strike <= SPOT
    if out_or_at:
        return True
    return days == 45 and abs(strike - SPOT) <= 5


# --- Ida y vuelta (AC-A11) ---------------------------------------------

@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("days", DAYS)
@pytest.mark.parametrize("strike", STRIKES)
@pytest.mark.parametrize("sigma", SIGMAS)
def test_round_trip_grid(kind, days, strike, sigma):
    market = make_market(days=days)
    premium = model_price(kind, market, strike, sigma)
    result = implied_vol(option_leg(kind, strike, premium), market)

    low, high = bounds(kind, market, strike)
    if not (low < premium < high):
        # Fuera de los límites (o en ellos) no debe salir un número.
        assert result.vol is None
        assert result.message
        return

    # Aserción universal (enmienda A1): la IV reproduce la prima.
    assert result.message is None
    assert result.vol is not None
    assert abs(model_price(kind, market, strike, result.vol) - premium) <= 1e-9
    if sigma_check_applies(kind, strike, days):
        assert abs(result.vol - sigma) <= 1e-9


@pytest.mark.parametrize("kind", ["call", "put"])
def test_premium_equal_to_model_price_returns_global_vol(kind):
    market = make_market(vol=0.32)
    premium = model_price(kind, market, 100, market.vol)
    result = implied_vol(option_leg(kind, 100, premium), market)
    assert abs(result.vol - market.vol) < 1e-9
    assert result.message is None


def test_round_trip_with_zero_rate_and_dividend():
    market = make_market(rate=0.0, q=0.03)
    premium = model_price("put", market, 102, 0.40)
    result = implied_vol(option_leg("put", 102, premium), market)
    assert result.vol == pytest.approx(0.40, abs=1e-9)


def test_round_trip_with_negative_rate():
    market = make_market(rate=-0.01, q=0.02)
    premium = model_price("call", market, 98, 0.18)
    result = implied_vol(option_leg("call", 98, premium), market)
    assert result.vol == pytest.approx(0.18, abs=1e-9)


# --- Casos sin IV (AC-A12) ---------------------------------------------

def test_zero_premium_deep_otm_is_not_a_fake_minimum_vol():
    # La trampa: brentq devolvería 1e-6 en silencio. Debe salir mensaje.
    result = implied_vol(option_leg("call", 200, 0.0), make_market())
    assert result.vol is None
    assert result.message == MSG_PREMIUM_NOT_POSITIVE


def test_negative_premium_message():
    result = implied_vol(option_leg("put", 100, -1.0), make_market())
    assert result.vol is None
    assert result.message == MSG_PREMIUM_NOT_POSITIVE


def test_put_premium_exactly_at_lower_bound():
    market = make_market()
    low, _ = bounds("put", market, 130)
    result = implied_vol(option_leg("put", 130, low), market)
    assert result.vol is None
    assert result.message == MSG_BELOW_LOWER_BOUND


def test_put_itm_premium_below_discounted_intrinsic():
    market = make_market()
    low, _ = bounds("put", market, 120)
    result = implied_vol(option_leg("put", 120, low - 0.5), market)
    assert result.vol is None
    assert result.message == MSG_BELOW_LOWER_BOUND


def test_call_itm_premium_below_lower_bound():
    market = make_market()
    low, _ = bounds("call", market, 80)
    result = implied_vol(option_leg("call", 80, low - 0.01), market)
    assert result.message == MSG_BELOW_LOWER_BOUND


def test_call_premium_at_or_above_upper_bound():
    market = make_market()
    _, high = bounds("call", market, 100)
    for premium in (high, high + 1.0):
        result = implied_vol(option_leg("call", 100, premium), market)
        assert result.vol is None
        assert result.message == MSG_ABOVE_UPPER_BOUND


def test_put_premium_at_or_above_upper_bound():
    market = make_market()
    _, high = bounds("put", market, 100)
    for premium in (high, high + 1.0):
        result = implied_vol(option_leg("put", 100, premium), market)
        assert result.vol is None
        assert result.message == MSG_ABOVE_UPPER_BOUND


def test_days_zero_message():
    result = implied_vol(option_leg("call", 100, 2.0), make_market(days=0))
    assert result.vol is None
    assert result.message == MSG_NO_TIME


def test_stock_leg_message():
    leg = Leg(kind="stock", side=1, quantity=100, strike=None, price=100.0)
    result = implied_vol(leg, make_market())
    assert result.vol is None
    assert result.message == MSG_STOCK_LEG


def test_check_order_stock_before_days_and_premium():
    # Orden fijo: acción -> días = 0 -> prima <= 0 -> límites.
    stock = Leg(kind="stock", side=1, quantity=1, strike=None, price=0.0)
    assert implied_vol(stock, make_market(days=0)).message == MSG_STOCK_LEG
    zero = option_leg("call", 100, 0.0)
    assert implied_vol(zero, make_market(days=0)).message == MSG_NO_TIME


def test_all_messages_are_distinct_spanish_text():
    messages = [
        MSG_STOCK_LEG,
        MSG_NO_TIME,
        MSG_PREMIUM_NOT_POSITIVE,
        MSG_BELOW_LOWER_BOUND,
        MSG_ABOVE_UPPER_BOUND,
        MSG_SOLVER_FAILED,
        MSG_INVALID_DATA,
    ]
    assert len(set(messages)) == len(messages)
    assert all(isinstance(m, str) and m for m in messages)


# --- Nunca lanza; vol y message excluyentes ----------------------------

BAD_CASES = [
    (option_leg("call", 100, float("nan")), make_market()),
    (option_leg("call", 100, None), make_market()),
    (option_leg("call", None, 2.0), make_market()),
    (option_leg("call", 0, 2.0), make_market()),
    (option_leg("put", 0, 2.0), make_market()),
    (option_leg("call", float("nan"), 2.0), make_market()),
    (option_leg("call", 100, 2.0), make_market(spot=float("nan"))),
    (option_leg("call", 100, 2.0), make_market(spot=0.0)),
    (option_leg("call", 100, 2.0), make_market(days=None)),
    (option_leg("call", 100, 2.0), make_market(rate=float("inf"))),
    (option_leg("call", 100, 2.0), make_market(q=None)),
    (option_leg("call", 100, True), make_market()),
    (Leg(kind="raro", side=1, quantity=1, strike=100, price=2.0), make_market()),
]


@pytest.mark.parametrize("leg, market", BAD_CASES)
def test_bad_inputs_never_raise_and_give_message(leg, market):
    result = implied_vol(leg, market)
    assert isinstance(result, IVResult)
    assert result.vol is None
    assert isinstance(result.message, str) and result.message


def test_invalid_data_message_for_non_numeric():
    result = implied_vol(option_leg("call", 100, float("nan")), make_market())
    assert result.message == MSG_INVALID_DATA


def test_solver_failure_becomes_message(monkeypatch):
    # Si el buscador de raíces falla (ValueError), devolvemos un mensaje.
    # Nota: `opciones.implied_vol` es también el nombre de la función
    # exportada, así que tomamos el módulo de sys.modules.
    module = sys.modules["opciones.implied_vol"]

    def broken_brentq(*args, **kwargs):
        raise ValueError("f(a) y f(b) tienen el mismo signo")

    monkeypatch.setattr(module, "brentq", broken_brentq)
    market = make_market()
    premium = model_price("call", market, 100, 0.25)
    result = implied_vol(option_leg("call", 100, premium), market)
    assert result.vol is None
    assert result.message == MSG_SOLVER_FAILED


@pytest.mark.parametrize("kind", ["call", "put"])
def test_vol_and_message_are_mutually_exclusive(kind):
    market = make_market()
    good = implied_vol(option_leg(kind, 100, model_price(kind, market, 100, 0.2)), market)
    bad = implied_vol(option_leg(kind, 100, 0.0), market)
    for result in (good, bad):
        assert (result.vol is None) != (result.message is None)
