"""Tests de P&L por pata y de estrategia, griegas de posición y rejilla de precios (bloque 2)."""

import numpy as np
import pytest

from opciones import CommissionSettings, Leg, Market, bs_greeks, bs_price, default_premium
from opciones.payoff import (
    leg_pnl_expiry,
    leg_pnl_today,
    pnl_expiry,
    pnl_today,
    position_greeks,
    price_grid,
)

# Comisiones a cero: así comprobamos la fórmula pura de AC5.
NO_FEES = CommissionSettings(per_contract=0.0, index_surcharge=0.0, include_close=True)


def market(days=30, underlying="Acción"):
    return Market(underlying=underlying, spot=100, vol=0.20, days=days, rate=0.05)


# --- P&L al vencimiento por pata (AC5) ----------------------------------

def test_long_call_expiry():
    leg = Leg("call", 1, 1, 100, 3.0)
    # S = 110: valor 10, P&L = 1 × 1 × 100 × (10 − 3) = 700.
    assert leg_pnl_expiry(leg, market(), NO_FEES, 110.0) == pytest.approx(700.0)
    # S = 90: vence sin valor, se pierde la prima.
    assert leg_pnl_expiry(leg, market(), NO_FEES, 90.0) == pytest.approx(-300.0)


def test_short_call_expiry():
    leg = Leg("call", -1, 2, 100, 3.0)
    # S = 110: −1 × 2 × 100 × (10 − 3) = −1400.
    assert leg_pnl_expiry(leg, market(), NO_FEES, 110.0) == pytest.approx(-1400.0)
    assert leg_pnl_expiry(leg, market(), NO_FEES, 90.0) == pytest.approx(600.0)


def test_long_and_short_put_expiry():
    long_put = Leg("put", 1, 1, 100, 2.0)
    short_put = Leg("put", -1, 1, 100, 2.0)
    assert leg_pnl_expiry(long_put, market(), NO_FEES, 80.0) == pytest.approx(1800.0)
    assert leg_pnl_expiry(long_put, market(), NO_FEES, 120.0) == pytest.approx(-200.0)
    assert leg_pnl_expiry(short_put, market(), NO_FEES, 80.0) == pytest.approx(-1800.0)
    assert leg_pnl_expiry(short_put, market(), NO_FEES, 120.0) == pytest.approx(200.0)


def test_stock_leg_uses_multiplier_one():
    long_stock = Leg("stock", 1, 100, None, 50.0)
    short_stock = Leg("stock", -1, 100, None, 50.0)
    # 100 acciones, el precio sube 5 USD: +500 (multiplicador 1, no 100).
    assert leg_pnl_expiry(long_stock, market(), NO_FEES, 55.0) == pytest.approx(500.0)
    assert leg_pnl_expiry(short_stock, market(), NO_FEES, 55.0) == pytest.approx(-500.0)


def test_option_multiplier_is_100():
    leg = Leg("call", 1, 1, 100, 0.0)
    assert leg.multiplier == 100
    assert Leg("stock", 1, 1, None, 0.0).multiplier == 1
    assert leg_pnl_expiry(leg, market(), NO_FEES, 101.0) == pytest.approx(100.0)


def test_expiry_is_vectorised():
    leg = Leg("call", 1, 1, 100, 3.0)
    S = np.array([90.0, 100.0, 110.0])
    assert leg_pnl_expiry(leg, market(), NO_FEES, S) == pytest.approx([-300.0, -300.0, 700.0])


# --- Comisiones dentro del P&L ------------------------------------------

def test_expiry_pnl_subtracts_open_and_close_fees():
    leg = Leg("call", 1, 1, 100, 3.0)
    settings = CommissionSettings()
    # ITM: apertura 0,65 + cierre 0,65.
    assert leg_pnl_expiry(leg, market(), settings, 110.0) == pytest.approx(700.0 - 1.30)
    # Vence sin valor: solo apertura.
    assert leg_pnl_expiry(leg, market(), settings, 90.0) == pytest.approx(-300.0 - 0.65)


def test_today_pnl_always_subtracts_close_fee():
    leg = Leg("call", 1, 1, 200, 0.10)  # muy fuera del dinero
    settings = CommissionSettings()
    value = bs_price("call", 100.0, 200, 0.05, 0.0, 0.20, 30 / 365)
    expected = 100 * (value - 0.10) - 1.30
    assert leg_pnl_today(leg, market(), settings, 100.0) == pytest.approx(expected)


# --- Prima por defecto y prima editada (AC4) ----------------------------

def test_default_premium_gives_zero_pnl_today_at_spot():
    # Si la prima es la de Black-Scholes, "hoy" al spot actual no se gana ni se pierde.
    m = market()
    leg = Leg("put", 1, 1, 95, default_premium("put", m, 95))
    assert leg.price == pytest.approx(bs_price("put", 100, 95, 0.05, 0.0, 0.20, 30 / 365))
    assert leg_pnl_today(leg, m, NO_FEES, m.spot) == pytest.approx(0.0, abs=1e-9)


def test_edited_premium_is_used_in_pnl():
    m = market()
    default = default_premium("call", m, 100)
    edited = Leg("call", 1, 1, 100, default + 1.0)
    # Pagar 1 USD más por acción cuesta 100 USD más en P&L.
    base = Leg("call", 1, 1, 100, default)
    diff = leg_pnl_expiry(base, m, NO_FEES, 120.0) - leg_pnl_expiry(edited, m, NO_FEES, 120.0)
    assert diff == pytest.approx(100.0)
    assert leg_pnl_today(edited, m, NO_FEES, m.spot) == pytest.approx(-100.0, abs=1e-9)


# --- P&L de la estrategia = suma de patas (AC9) -------------------------

def iron_condor():
    return [
        Leg("put", 1, 1, 90, 0.50),
        Leg("put", -1, 1, 95, 1.50),
        Leg("call", -1, 1, 105, 1.50),
        Leg("call", 1, 1, 110, 0.50),
    ]


def test_strategy_expiry_equals_sum_of_legs():
    legs = iron_condor()
    m = market(underlying="Índice")
    settings = CommissionSettings()
    S = price_grid(m, legs)
    total = sum(leg_pnl_expiry(leg, m, settings, S) for leg in legs)
    assert pnl_expiry(legs, m, settings, S) == pytest.approx(total)


def test_strategy_today_equals_sum_of_legs():
    legs = iron_condor() + [Leg("stock", 1, 100, None, 100.0)]
    m = market()
    settings = CommissionSettings()
    S = price_grid(m, legs)
    total = sum(leg_pnl_today(leg, m, settings, S) for leg in legs)
    assert pnl_today(legs, m, settings, S) == pytest.approx(total)


def test_iron_condor_expiry_values_without_fees():
    legs = iron_condor()
    m = market()
    # Prima neta cobrada 2,00 → +200 en la meseta; pérdida máx. 300 en las alas.
    assert pnl_expiry(legs, m, NO_FEES, 100.0) == pytest.approx(200.0)
    assert pnl_expiry(legs, m, NO_FEES, 80.0) == pytest.approx(-300.0)
    assert pnl_expiry(legs, m, NO_FEES, 120.0) == pytest.approx(-300.0)


# --- Días = 0: "hoy" = valor intrínseco (AC1 parcial, decisión 13) -------

def test_today_with_zero_days_is_intrinsic_minus_fees():
    m = market(days=0)
    settings = CommissionSettings()
    legs = [Leg("call", 1, 1, 100, 3.0), Leg("put", -1, 2, 95, 1.0)]
    S = np.array([80.0, 95.0, 100.0, 120.0])
    intrinsic = (
        100 * (np.maximum(S - 100, 0) - 3.0)
        - 2 * 100 * (np.maximum(95 - S, 0) - 1.0)
    )
    # "Hoy" liquida todo: apertura + cierre en cada pata (1 + 2 contratos).
    fees = 2 * 0.65 * 3
    result = pnl_today(legs, m, settings, S)
    assert result == pytest.approx(intrinsic - fees)
    assert not np.any(np.isnan(result))


# --- Griegas de posición (AC8 parcial) ----------------------------------

def test_position_greeks_long_and_short_signs():
    m = Market("Acción", spot=100, vol=0.20, days=365, rate=0.05)
    ref = bs_greeks("call", 100, 100, 0.05, 0.0, 0.20, 1.0)
    long_g = position_greeks([Leg("call", 1, 2, 100, 10.0)], m)
    short_g = position_greeks([Leg("call", -1, 2, 100, 10.0)], m)
    for name in ("delta", "gamma", "theta", "vega", "rho"):
        assert long_g[name] == pytest.approx(ref[name] * 100 * 2)
        assert short_g[name] == pytest.approx(-ref[name] * 100 * 2)


def test_position_greeks_stock_leg():
    m = market()
    long_g = position_greeks([Leg("stock", 1, 50, None, 100.0)], m)
    short_g = position_greeks([Leg("stock", -1, 50, None, 100.0)], m)
    assert long_g == {"delta": 50.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    assert short_g["delta"] == -50.0


def test_position_greeks_sum_of_legs():
    m = market()
    legs = [Leg("put", 1, 1, 95, 1.0), Leg("stock", 1, 100, None, 100.0)]
    put_g = bs_greeks("put", 100, 95, 0.05, 0.0, 0.20, 30 / 365)
    total = position_greeks(legs, m)
    assert total["delta"] == pytest.approx(put_g["delta"] * 100 + 100)
    assert total["gamma"] == pytest.approx(put_g["gamma"] * 100)


def test_position_greeks_none_with_zero_days():
    g = position_greeks([Leg("call", 1, 1, 100, 3.0), Leg("stock", 1, 100, None, 100.0)], market(days=0))
    assert g == {"delta": None, "gamma": None, "theta": None, "vega": None, "rho": None}


# --- Rejilla de precios (AC9) -------------------------------------------

def test_grid_covers_about_30_percent_around_spot():
    grid = price_grid(market(), [Leg("call", 1, 1, 100, 3.0)])
    assert grid[0] <= 70.0
    assert grid[-1] >= 130.0
    assert np.all(np.diff(grid) > 0)


def test_grid_covers_far_strikes():
    legs = [Leg("put", 1, 1, 20, 0.1), Leg("call", 1, 1, 300, 0.1)]
    grid = price_grid(market(), legs)
    assert grid[0] < 20.0
    assert grid[-1] > 300.0


def test_grid_includes_strikes_and_neighbours():
    legs = iron_condor()
    grid = price_grid(market(), legs)
    for K in (90, 95, 105, 110):
        for point in (K - 1e-9, K, K + 1e-9):
            assert np.any(np.isclose(grid, point, rtol=0, atol=1e-12))


def test_grid_never_negative():
    grid = price_grid(market(), [Leg("put", 1, 1, 1e-10, 0.0)])
    assert grid[0] >= 0.0


def test_grid_with_only_stock_legs():
    grid = price_grid(market(), [Leg("stock", 1, 100, None, 100.0)])
    assert grid[0] <= 70.0 and grid[-1] >= 130.0
