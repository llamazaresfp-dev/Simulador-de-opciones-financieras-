"""Tests del despachador de modelos (Etapa B1, bloque 2).

`uses_binomial` decide el modelo y `option_price` lo aplica. Aquí
comprobamos que:
- Acción/ETF usan el árbol binomial por defecto (test "canario").
- Índice usa siempre Black-Scholes, con cualquier ajuste.
- Con "black_scholes" en Acción/ETF salen los números de la Etapa A.
- La curva "hoy" (200/201 pasos) casi coincide con la prima (500/501).
- Lo que ocurre al vencimiento (P&L, métricas, PoP, Monte Carlo) no
  depende del modelo: solo depende de las patas.
"""

import numpy as np
import pytest

from opciones import TEMPLATES, CommissionSettings, Leg, Market, build_legs, compute_metrics
from opciones.binomial import crr_greeks, crr_price, crr_price_grid
from opciones.models import PRICING_BINOMIAL, PRICING_BLACK_SCHOLES
from opciones import analyze
from opciones.payoff import GREEK_NAMES, leg_pnl_today, pnl_expiry, pnl_today, position_greeks, price_grid
from opciones.pricing import (
    bs_greeks,
    bs_price,
    default_premium,
    option_greeks,
    option_price,
    uses_binomial,
)
from opciones.simulation import SimulationSettings, exact_pop, simulate_scenario

FEES = CommissionSettings()  # 0,65 USD por contrato, cierre incluido
NO_FEES = CommissionSettings(per_contract=0.0, index_surcharge=0.0, include_close=True)
RISK_NEUTRAL = SimulationSettings()
MODELS = (PRICING_BINOMIAL, PRICING_BLACK_SCHOLES)


def make_market(underlying="Acción", model=PRICING_BINOMIAL, **changes):
    """Mercado de referencia del SPEC: σ 25 %, 45 días, r 4 %, q 1 %."""
    data = dict(underlying=underlying, spot=100.0, vol=0.25, days=45, rate=0.04, q=0.01,
                pricing_model=model)
    data.update(changes)
    return Market(**data)


def bs_of(kind, market, strike, S=None):
    """Precio Black-Scholes directo, sin pasar por el despachador."""
    S = market.spot if S is None else S
    return bs_price(kind, S, strike, market.rate, market.q, market.vol, market.T)


def iron_condor():
    return next(t for t in TEMPLATES if t.key == "iron_condor")


# --- uses_binomial: tabla de verdad ------------------------------------

@pytest.mark.parametrize("underlying, model, expected", [
    ("Acción", PRICING_BINOMIAL, True),
    ("ETF", PRICING_BINOMIAL, True),
    ("Índice", PRICING_BINOMIAL, False),
    ("Acción", PRICING_BLACK_SCHOLES, False),
    ("ETF", PRICING_BLACK_SCHOLES, False),
    ("Índice", PRICING_BLACK_SCHOLES, False),
    ("Acción", "desconocido", False),
    ("ETF", "", False),
])
def test_uses_binomial_truth_table(underlying, model, expected):
    assert uses_binomial(make_market(underlying, model)) is expected


# --- Canario: sin fijar nada, una acción usa el binomial ----------------

def test_canary_unpinned_stock_market_uses_binomial():
    # Market sin pricing_model: el valor por defecto debe ser el binomial.
    market = Market("Acción", 100.0, 0.25, 45, 0.04, 0.01)
    premium = default_premium("put", market, 100.0)
    assert premium == crr_price("put", 100.0, 100.0, 0.04, 0.01, 0.25, market.T)
    assert premium != pytest.approx(bs_of("put", market, 100.0), abs=1e-6)


def test_option_price_scalar_uses_500_steps_and_array_uses_200_steps():
    market = make_market()
    assert option_price("put", market, 100.0) == crr_price(
        "put", 100.0, 100.0, 0.04, 0.01, 0.25, market.T)
    S = np.array([90.0, 100.0, 110.0])
    np.testing.assert_array_equal(
        option_price("put", market, 100.0, S),
        crr_price_grid("put", S, 100.0, 0.04, 0.01, 0.25, market.T))


def test_option_price_accepts_other_spot_and_sigma():
    market = make_market()
    assert option_price("call", market, 105.0, S=98.0, sigma=0.4) == crr_price(
        "call", 98.0, 105.0, 0.04, 0.01, 0.4, market.T)


def test_option_price_rejects_invalid_kind():
    with pytest.raises(ValueError):
        option_price("stock", make_market(), 100.0)


def test_default_premium_invalid_data_still_returns_zero():
    market = make_market()
    assert default_premium("stock", market, 100.0) == 0.0
    assert default_premium("call", market, None) == 0.0
    assert default_premium("call", market, -5.0) == 0.0
    assert default_premium("call", make_market(spot="abc"), 100.0) == 0.0


# --- Índice: siempre Black-Scholes -------------------------------------

@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("strike", [90.0, 100.0, 110.0])
def test_index_premium_is_black_scholes_with_any_model(model, kind, strike):
    market = make_market("Índice", model)
    assert default_premium(kind, market, strike) == bs_of(kind, market, strike)


@pytest.mark.parametrize("model", MODELS)
def test_index_today_curve_is_black_scholes_with_any_model(model):
    market = make_market("Índice", model)
    leg = Leg("put", 1, 1.0, 100.0, 3.0)
    S = price_grid(market, [leg])
    expected = 1 * 1.0 * 100 * (bs_of("put", market, 100.0, S) - 3.0)
    np.testing.assert_array_equal(leg_pnl_today(leg, market, NO_FEES, S), expected)


# --- black_scholes en Acción/ETF = Etapa A ------------------------------

@pytest.mark.parametrize("underlying", ["Acción", "ETF"])
@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("strike", [90.0, 100.0, 110.0])
def test_black_scholes_pinned_premium_equals_stage_a(underlying, kind, strike):
    market = make_market(underlying, PRICING_BLACK_SCHOLES)
    assert default_premium(kind, market, strike) == bs_of(kind, market, strike)


def test_black_scholes_pinned_reference_premium():
    # Valor de referencia de la Etapa A (call S=K=100, σ 20 %, 1 año, r 5 %).
    market = Market("Acción", 100.0, 0.20, 365, 0.05, 0.0, PRICING_BLACK_SCHOLES)
    assert default_premium("call", market, 100.0) == pytest.approx(10.4506, abs=1e-4)


@pytest.mark.parametrize("underlying", ["Acción", "ETF"])
def test_black_scholes_pinned_today_curve_equals_stage_a(underlying):
    market = make_market(underlying, PRICING_BLACK_SCHOLES)
    legs = build_legs(iron_condor(), market)
    S = price_grid(market, legs)
    expected = np.zeros_like(S)
    for leg in legs:
        value = bs_of(leg.kind, market, leg.strike, S)
        expected += leg.side * leg.quantity * leg.multiplier * (value - leg.price)
    np.testing.assert_allclose(pnl_today(legs, market, NO_FEES, S), expected, rtol=0, atol=1e-12)


# --- Curva "hoy" binomial (B7) ------------------------------------------

@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("strike", [90.0, 100.0, 110.0])
@pytest.mark.parametrize("vol, days", [(0.15, 30), (0.25, 45), (0.40, 180), (0.25, 365)])
@pytest.mark.parametrize("rate, q", [(0.04, 0.01), (0.05, 0.03)])
def test_today_grid_matches_premium_at_spot(kind, strike, vol, days, rate, q):
    # B7: la curva "hoy" usa 200/201 pasos y la prima 500/501; en el spot
    # la diferencia debe ser ≤ 0,02 USD por acción (medido ≤ ≈ 0,01).
    market = make_market(vol=vol, days=days, rate=rate, q=q)
    S = np.array([80.0, market.spot, 120.0])
    grid = option_price(kind, market, strike, S)
    premium = option_price(kind, market, strike)
    assert grid[1] == pytest.approx(premium, abs=0.02)


@pytest.mark.parametrize("kind", ["call", "put"])
def test_today_grid_is_finite_and_at_least_intrinsic(kind):
    market = make_market()
    leg = Leg(kind, 1, 1.0, 100.0, 0.0)
    S = price_grid(market, [leg])
    values = option_price(kind, market, 100.0, S)
    intrinsic = np.maximum(S - 100.0, 0.0) if kind == "call" else np.maximum(100.0 - S, 0.0)
    assert np.all(np.isfinite(values))
    assert np.all(values >= intrinsic - 1e-12)


def test_today_curve_with_zero_days_is_intrinsic_with_both_models():
    leg = Leg("put", 1, 1.0, 100.0, 2.0)
    S = np.linspace(80.0, 120.0, 41)
    for model in MODELS:
        market = make_market(model=model, days=0)
        expected = 100 * (np.maximum(100.0 - S, 0.0) - 2.0)
        np.testing.assert_allclose(leg_pnl_today(leg, market, NO_FEES, S), expected, atol=1e-12)


# --- Vencimiento: no depende del modelo (AC-B11) -----------------------

def legs_built_with_black_scholes():
    """Patas del iron condor del catálogo con primas BS (como en la Etapa A)."""
    return build_legs(iron_condor(), make_market(model=PRICING_BLACK_SCHOLES))


def test_expiry_pnl_and_metrics_identical_with_both_models():
    legs = legs_built_with_black_scholes()
    bs_market = make_market(model=PRICING_BLACK_SCHOLES)
    tree_market = make_market(model=PRICING_BINOMIAL)
    S = price_grid(bs_market, legs)
    np.testing.assert_array_equal(pnl_expiry(legs, bs_market, FEES, S),
                                  pnl_expiry(legs, tree_market, FEES, S))
    assert compute_metrics(legs, bs_market, FEES) == compute_metrics(legs, tree_market, FEES)


@pytest.mark.parametrize("model", MODELS)
def test_exact_pop_of_iron_condor_is_0_5721_with_both_models(model):
    # La PoP depende de las primas de las patas, no del modelo: con patas
    # construidas con primas BS da 0,5721 con ambos modelos.
    legs = legs_built_with_black_scholes()
    pop = exact_pop(make_market(model=model), legs, FEES, RISK_NEUTRAL)
    assert pop == pytest.approx(0.5721, abs=5e-4)


def test_exact_pop_identical_between_models():
    legs = legs_built_with_black_scholes()
    pops = [exact_pop(make_market(model=m), legs, FEES, RISK_NEUTRAL) for m in MODELS]
    assert pops[0] == pops[1]


def test_monte_carlo_seed_42_identical_between_models():
    legs = legs_built_with_black_scholes()
    sim = SimulationSettings(n_paths=20_000, seed=42)
    results = [simulate_scenario(make_market(model=m), legs, FEES, sim) for m in MODELS]
    first, second = results
    assert first.pop_exact == second.pop_exact
    assert first.pop_mc == second.pop_mc
    assert first.mean_pnl == second.mean_pnl
    assert first.pnl_std == second.pnl_std
    assert (first.p5, first.p50, first.p95) == (second.p5, second.p50, second.p95)
    np.testing.assert_array_equal(first.hist_counts, second.hist_counts)
    np.testing.assert_array_equal(first.hist_edges, second.hist_edges)


# --- AC-B8: griegas según el modelo (bloque 3) ------------------------------

def crr_greeks_of(kind, market, strike):
    """Griegas del árbol directas, sin pasar por el despachador."""
    return crr_greeks(kind, market.spot, strike, market.rate, market.q, market.vol, market.T)


def bs_greeks_of(kind, market, strike):
    """Griegas Black-Scholes directas, sin pasar por el despachador."""
    return bs_greeks(kind, market.spot, strike, market.rate, market.q, market.vol, market.T)


@pytest.mark.parametrize("kind, strike", [("call", 95.0), ("put", 105.0)])
def test_option_greeks_binomial_uses_tree(kind, strike):
    market = make_market()
    assert option_greeks(kind, market, strike) == crr_greeks_of(kind, market, strike)


@pytest.mark.parametrize("underlying, model", [
    ("Índice", PRICING_BINOMIAL),
    ("Índice", PRICING_BLACK_SCHOLES),
    ("Acción", PRICING_BLACK_SCHOLES),
    ("ETF", PRICING_BLACK_SCHOLES),
])
@pytest.mark.parametrize("kind, strike", [("call", 95.0), ("put", 105.0)])
def test_option_greeks_black_scholes_identical_to_stage_a(underlying, model, kind, strike):
    market = make_market(underlying, model)
    assert option_greeks(kind, market, strike) == bs_greeks_of(kind, market, strike)


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("changes", [dict(days=0), dict(vol=0.0)])
def test_option_greeks_undefined_raise_value_error(model, changes):
    with pytest.raises(ValueError):
        option_greeks("call", make_market(model=model, **changes), 100.0)


def test_option_greeks_rejects_invalid_kind():
    with pytest.raises(ValueError):
        option_greeks("stock", make_market(), 100.0)


def test_binomial_position_greeks_are_sum_of_legs():
    market = make_market()
    legs = [
        Leg("put", 1, 2, 95.0, 1.0),
        Leg("call", -1, 3, 105.0, 1.0),
        Leg("stock", 1, 50, None, 100.0),
    ]
    put_g = crr_greeks_of("put", market, 95.0)
    call_g = crr_greeks_of("call", market, 105.0)
    total = position_greeks(legs, market)
    for name in GREEK_NAMES:
        expected = put_g[name] * 1 * 2 * 100 + call_g[name] * (-1) * 3 * 100
        if name == "delta":
            expected += 50  # la acción solo aporta delta: ±cantidad
        assert total[name] == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_binomial_position_greeks_stock_leg_only_delta():
    total = position_greeks([Leg("stock", -1, 40, None, 100.0)], make_market())
    assert total == {"delta": -40.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("changes", [dict(days=0), dict(vol=0.0)])
def test_position_greeks_none_without_time_or_volatility(model, changes):
    legs = [Leg("put", 1, 1, 100.0, 3.0), Leg("stock", 1, 100, None, 100.0)]
    total = position_greeks(legs, make_market(model=model, **changes))
    assert total == {name: None for name in GREEK_NAMES}


@pytest.mark.parametrize("underlying, model", [
    ("Índice", PRICING_BINOMIAL),
    ("Índice", PRICING_BLACK_SCHOLES),
    ("Acción", PRICING_BLACK_SCHOLES),
])
def test_black_scholes_position_greeks_identical_to_stage_a(underlying, model):
    market = make_market(underlying, model)
    legs = [Leg("put", 1, 2, 95.0, 1.0), Leg("call", -1, 1, 105.0, 1.0)]
    put_g = bs_greeks_of("put", market, 95.0)
    call_g = bs_greeks_of("call", market, 105.0)
    total = position_greeks(legs, market)
    for name in GREEK_NAMES:
        # Mismo orden de suma que la Etapa A: igualdad exacta.
        expected = 0.0
        expected += put_g[name] * (1 * 2 * 100)
        expected += call_g[name] * (-1 * 1 * 100)
        assert total[name] == expected


def test_analyze_greeks_equal_position_greeks_with_binomial():
    market = make_market()
    legs = build_legs(iron_condor(), market)
    result = analyze(market, legs, FEES)
    assert result.greeks == position_greeks(legs, market)


# --- Bloque 7: rendimiento de analyze() y casos límite (AC-B13, AC-B14) ----

import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

from opciones import binomial as binomial_module  # noqa: E402
from opciones import implied_vol  # noqa: E402
from opciones.models import MIN_VOL  # noqa: E402


def clear_engine_caches():
    """Vacía todas las cachés del motor para medir en frío."""
    binomial_module._cached_price.cache_clear()
    binomial_module._cached_grid.cache_clear()
    binomial_module._cached_greeks.cache_clear()
    sys.modules["opciones.implied_vol"]._cached_american_iv.cache_clear()


def elapsed(function):
    start = time.perf_counter()
    function()
    return time.perf_counter() - start


def test_iron_condor_analyze_cold_and_warm_are_fast():
    market = make_market()               # Acción, binomial por defecto
    legs = build_legs(iron_condor(), market)
    clear_engine_caches()
    cold = elapsed(lambda: analyze(market, legs, FEES))
    warm = elapsed(lambda: analyze(market, legs, FEES))
    assert cold < 2.0
    assert warm < 0.3


def test_iron_condor_analyze_warm_equals_cold():
    market = make_market()
    legs = build_legs(iron_condor(), market)
    clear_engine_caches()
    cold = analyze(market, legs, FEES)
    warm = analyze(market, legs, FEES)
    np.testing.assert_allclose(warm.today_curve, cold.today_curve, rtol=0, atol=1e-12)
    for name in GREEK_NAMES:
        assert warm.greeks[name] == pytest.approx(cold.greeks[name], abs=1e-12)


EDGE_MARKETS = [
    dict(days=0),
    dict(vol=MIN_VOL),
    dict(days=1),
    dict(days=3650),
    dict(rate=-0.05, q=0.20),
    dict(rate=0.20, q=-0.05),
    dict(vol=10.0, days=3650),
]


def edge_legs(market):
    """Patas con strikes lejanísimos (1 y 10 000), una ATM y acciones."""
    legs = [Leg("call", 1, 1, 1.0, 0.0), Leg("put", -1, 1, 10_000.0, 0.0),
            Leg("put", 1, 2, 100.0, 0.0), Leg("stock", 1, 100, None, market.spot)]
    for leg in legs:
        if leg.kind != "stock":
            leg.price = default_premium(leg.kind, market, leg.strike)
    return legs


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("changes", EDGE_MARKETS)
def test_edge_markets_never_give_nan_or_raise(model, changes):
    market = make_market(model=model, **changes)
    legs = edge_legs(market)
    for leg in legs:
        assert math.isfinite(leg.price) and leg.price >= 0.0
    result = analyze(market, legs, FEES)
    assert np.all(np.isfinite(result.today_curve))
    assert np.all(np.isfinite(result.expiry_curve))
    for name in GREEK_NAMES:
        value = result.greeks[name]
        if market.days == 0:
            assert value is None
        else:
            assert value is not None and math.isfinite(value)
    for leg in legs:
        iv = implied_vol(leg, market)
        assert (iv.vol is None) != (iv.message is None)


@pytest.mark.parametrize("model", MODELS)
def test_zero_days_today_equals_intrinsic_and_greeks_none(model):
    market = make_market(model=model, days=0)
    S = np.array([80.0, 100.0, 120.0])
    np.testing.assert_allclose(option_price("put", market, 100.0, S),
                               np.maximum(100.0 - S, 0.0), atol=1e-12)
    greeks = position_greeks([Leg("put", 1, 1, 100.0, 2.0)], market)
    assert all(value is None for value in greeks.values())


@pytest.mark.parametrize("model", MODELS)
def test_zero_premium_iv_gives_message(model):
    market = make_market(model=model)
    result = implied_vol(Leg("call", 1, 1, 100.0, 0.0), market)
    assert result.vol is None and result.message


@pytest.mark.parametrize("model", MODELS)
def test_stock_only_position_has_no_tree(model):
    market = make_market(model=model)
    legs = [Leg("stock", 1, 100, None, 100.0)]
    result = analyze(market, legs, NO_FEES)
    np.testing.assert_allclose(result.today_curve, 100.0 * (result.grid - 100.0), atol=1e-9)
    assert result.greeks["delta"] == 100
    assert result.greeks["vega"] == 0.0
