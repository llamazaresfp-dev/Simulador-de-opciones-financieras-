"""Tests de precios y griegas Black-Scholes (bloque 1).

Comparamos contra valores de referencia de libro (Hull) para estar
seguros de que la fórmula es correcta antes de construir nada encima.
"""

import math

import numpy as np
import pytest

from opciones import Market, bs_greeks, bs_price, default_premium

# Tolerancia de 4 decimales para los precios del libro.
BOOK = 1e-4


# --- Precios de referencia (AC6) ---------------------------------------

def test_hull_call_and_put_prices():
    # Hull: S=42, K=40, r=10 %, sigma=20 %, T=0,5 años, sin dividendo.
    assert bs_price("call", 42, 40, 0.10, 0.0, 0.20, 0.5) == pytest.approx(4.7594, abs=BOOK)
    assert bs_price("put", 42, 40, 0.10, 0.0, 0.20, 0.5) == pytest.approx(0.8086, abs=BOOK)


def test_hull_call_delta():
    greeks = bs_greeks("call", 42, 40, 0.10, 0.0, 0.20, 0.5)
    assert greeks["delta"] == pytest.approx(0.7791, abs=BOOK)


def test_at_the_money_prices():
    # S=K=100, r=5 %, sigma=20 %, T=1, q=0.
    assert bs_price("call", 100, 100, 0.05, 0.0, 0.20, 1.0) == pytest.approx(10.4506, abs=BOOK)
    assert bs_price("put", 100, 100, 0.05, 0.0, 0.20, 1.0) == pytest.approx(5.5735, abs=BOOK)


# --- Griegas de referencia (AC8) ---------------------------------------

def test_reference_greeks_call():
    g = bs_greeks("call", 100, 100, 0.05, 0.0, 0.20, 1.0)
    assert g["delta"] == pytest.approx(0.6368, abs=BOOK)
    assert g["gamma"] == pytest.approx(0.018762, abs=1e-6)
    assert g["vega"] == pytest.approx(0.3752, abs=BOOK)   # por punto de vol
    assert g["theta"] == pytest.approx(-0.01757, abs=1e-5)  # por día
    assert g["rho"] == pytest.approx(0.5323, abs=BOOK)    # por punto de tipo


def test_put_greeks_signs():
    g = bs_greeks("put", 100, 100, 0.05, 0.0, 0.20, 1.0)
    # La delta de la put = delta de la call - 1 (con q = 0).
    assert g["delta"] == pytest.approx(0.6368 - 1, abs=BOOK)
    # Gamma y vega son iguales para call y put.
    assert g["gamma"] == pytest.approx(0.018762, abs=1e-6)
    assert g["vega"] == pytest.approx(0.3752, abs=BOOK)
    assert g["rho"] < 0


def test_greeks_raise_when_expired_or_zero_vol():
    with pytest.raises(ValueError):
        bs_greeks("call", 100, 100, 0.05, 0.0, 0.20, 0.0)
    with pytest.raises(ValueError):
        bs_greeks("put", 100, 100, 0.05, 0.0, 0.0, 1.0)


# --- Paridad put-call (AC7) --------------------------------------------

@pytest.mark.parametrize(
    "S, K, r, q, sigma, T",
    [
        (100, 100, 0.05, 0.0, 0.20, 1.0),
        (42, 40, 0.10, 0.0, 0.20, 0.5),
        (100, 110, 0.03, 0.02, 0.25, 0.75),
        (4500, 4400, 0.045, 0.015, 0.18, 30 / 365),
        (20, 25, 0.01, 0.04, 0.60, 2.0),
    ],
)
def test_put_call_parity(S, K, r, q, sigma, T):
    call = bs_price("call", S, K, r, q, sigma, T)
    put = bs_price("put", S, K, r, q, sigma, T)
    expected = S * math.exp(-q * T) - K * math.exp(-r * T)
    assert call - put == pytest.approx(expected, abs=1e-9)


# --- Dividendo q (AC2) -------------------------------------------------

def test_dividend_changes_price_and_delta():
    call_no_q = bs_price("call", 100, 100, 0.05, 0.0, 0.20, 1.0)
    call_q = bs_price("call", 100, 100, 0.05, 0.03, 0.20, 1.0)
    put_no_q = bs_price("put", 100, 100, 0.05, 0.0, 0.20, 1.0)
    put_q = bs_price("put", 100, 100, 0.05, 0.03, 0.20, 1.0)
    # El dividendo baja el precio esperado de la acción:
    # la call vale menos y la put vale más.
    assert call_q < call_no_q
    assert put_q > put_no_q

    delta_no_q = bs_greeks("call", 100, 100, 0.05, 0.0, 0.20, 1.0)["delta"]
    delta_q = bs_greeks("call", 100, 100, 0.05, 0.03, 0.20, 1.0)["delta"]
    assert delta_q < delta_no_q


# --- Casos límite: T = 0 y sigma = 0 -----------------------------------

def test_expired_returns_intrinsic_value():
    assert bs_price("call", 110, 100, 0.05, 0.0, 0.20, 0.0) == pytest.approx(10.0)
    assert bs_price("call", 90, 100, 0.05, 0.0, 0.20, 0.0) == pytest.approx(0.0)
    assert bs_price("put", 90, 100, 0.05, 0.0, 0.20, 0.0) == pytest.approx(10.0)
    assert bs_price("put", 110, 100, 0.05, 0.0, 0.20, 0.0) == pytest.approx(0.0)


def test_expired_array_returns_intrinsic_value():
    S = np.array([80.0, 100.0, 120.0])
    np.testing.assert_allclose(bs_price("call", S, 100, 0.05, 0.0, 0.2, 0.0), [0, 0, 20])
    np.testing.assert_allclose(bs_price("put", S, 100, 0.05, 0.0, 0.2, 0.0), [20, 0, 0])


def test_zero_vol_returns_deterministic_limit_without_nan():
    r, q, T = 0.05, 0.02, 1.0
    S = np.array([80.0, 100.0, 120.0])
    K = 100.0
    forward_diff = S * np.exp(-q * T) - K * np.exp(-r * T)
    call = bs_price("call", S, K, r, q, 0.0, T)
    put = bs_price("put", S, K, r, q, 0.0, T)
    assert not np.isnan(call).any()
    assert not np.isnan(put).any()
    np.testing.assert_allclose(call, np.maximum(forward_diff, 0))
    np.testing.assert_allclose(put, np.maximum(-forward_diff, 0))


# --- Escalar vs array y valores extremos -------------------------------

def test_scalar_and_array_inputs_match():
    S = np.array([50.0, 90.0, 100.0, 110.0, 200.0])
    prices = bs_price("call", S, 100, 0.05, 0.01, 0.25, 0.5)
    assert isinstance(prices, np.ndarray)
    for s, p in zip(S, prices):
        single = bs_price("call", float(s), 100, 0.05, 0.01, 0.25, 0.5)
        assert isinstance(single, float)
        assert single == pytest.approx(p, abs=1e-12)


def test_extreme_spot_values_have_no_nan():
    S = np.array([0.0, 1e-9, 1e-3, 1e5, 1e8])
    for kind in ("call", "put"):
        prices = bs_price(kind, S, 100, 0.05, 0.01, 0.20, 0.5)
        assert np.isfinite(prices).all()
        assert (prices >= 0).all()


def test_tiny_vol_and_tiny_time_have_no_nan():
    S = np.linspace(50, 150, 101)
    for kind in ("call", "put"):
        assert np.isfinite(bs_price(kind, S, 100, 0.05, 0.0, 0.0001, 1.0)).all()
        assert np.isfinite(bs_price(kind, S, 100, 0.05, 0.0, 0.20, 1e-9)).all()


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        bs_price("stock", 100, 100, 0.05, 0.0, 0.20, 1.0)


# --- Prima por defecto (AC4) -------------------------------------------

def make_market(**changes):
    data = dict(underlying="Acción", spot=100.0, vol=0.20, days=365, rate=0.05, q=0.0)
    data.update(changes)
    return Market(**data)


def test_default_premium_equals_bs_price():
    market = make_market(q=0.01)
    for kind in ("call", "put"):
        expected = bs_price(kind, market.spot, 105, market.rate, market.q, market.vol, market.T)
        assert default_premium(kind, market, 105) == pytest.approx(expected)


def test_default_premium_reference_value():
    assert default_premium("call", make_market(), 100) == pytest.approx(10.4506, abs=BOOK)


def test_default_premium_zero_when_not_computable():
    market = make_market()
    assert default_premium("call", market, None) == 0.0
    assert default_premium("call", market, -5) == 0.0
    assert default_premium("stock", market, 100) == 0.0
    assert default_premium("put", make_market(spot=float("nan")), 100) == 0.0


def test_default_premium_with_zero_days_is_intrinsic():
    market = make_market(spot=110.0, days=0)
    assert default_premium("call", market, 100) == pytest.approx(10.0)
    assert default_premium("put", market, 100) == pytest.approx(0.0)
