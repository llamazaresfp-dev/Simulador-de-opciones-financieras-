"""Tests de escenarios al vencimiento (Etapa A, bloques 2 y 3a).

Bloque 2 (PoP exacta): AC-A1 (parte exacta: neutral al riesgo vs μ),
AC-A2 (long call = N(d2), long put = N(−d2)) y AC-A3 (estrategias con
varios tramos contra una integración numérica independiente, y
extremos PoP = 0 / 1).

Bloque 3a (Monte Carlo): AC-A1 (media de S_T), AC-A4 (PoP simulada vs
exacta), AC-A5 (percentiles e histograma), AC-A6 (valor esperado),
AC-A8 (semilla y valores por defecto), AC-A9 (rapidez) y AC-A10 (sin
NaN ni infinitos).

El oráculo independiente NO usa los breakevens de las métricas: busca
los cambios de signo del P&L con una rejilla muy densa, afina cada uno
por bisección y luego integra la densidad lognormal con
scipy.integrate.quad (enmienda A2 del contrato de validación).
"""

import math
import time

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import norm

from opciones import TEMPLATES, CommissionSettings, Leg, Market, build_legs, compute_metrics
from opciones.metrics import ZERO_TOL
from opciones.payoff import pnl_expiry
from opciones.commissions import open_fee
from opciones.simulation import (
    ScenarioResult,
    SimulationSettings,
    _sample_terminal,
    exact_pop,
    simulate_scenario,
)

FEES = CommissionSettings()  # 0,65 USD por contrato, cierre incluido
NO_FEES = CommissionSettings(per_contract=0.0, index_surcharge=0.0, include_close=True)
RISK_NEUTRAL = SimulationSettings()  # mu = None


def make_market(underlying="Acción", spot=100.0):
    """Mercado de referencia del SPEC: σ 25 %, 45 días, r 4 %, q 1 %."""
    # Etapa B1: fijado a Black-Scholes porque build_legs usa default_premium
    # y las cifras de referencia (PoP, N(−d2)) son de primas BS.
    return Market(underlying=underlying, spot=spot, vol=0.25, days=45, rate=0.04, q=0.01,
                  pricing_model="black_scholes")


MARKET = make_market()


def template_legs(key, market=MARKET):
    template = next(t for t in TEMPLATES if t.key == key)
    return build_legs(template, market)


# --- Oráculo independiente ---------------------------------------------


def _lognormal_pdf(x, market, drift):
    """Densidad lognormal del precio final S_T (escrita a mano)."""
    sigma_t = market.vol * math.sqrt(market.T)
    mean_log = math.log(market.spot) + (drift - market.vol**2 / 2) * market.T
    return math.exp(-((math.log(x) - mean_log) ** 2) / (2 * sigma_t**2)) / (
        x * sigma_t * math.sqrt(2 * math.pi)
    )


def oracle_pop(market, legs, settings, drift=None, n_points=200_001):
    """PoP por integración numérica independiente (sin usar breakevens).

    1. Rejilla densa en el espacio z (±10 desviaciones) -> precios S.
    2. Donde el signo de "P&L > ZERO_TOL" cambia, bisección para
       encontrar el punto exacto (sirve también para los saltos de
       comisión, que no son raíces de una recta).
    3. quad de la densidad lognormal en cada tramo ganador.
    """
    if drift is None:
        drift = market.rate - market.q
    sigma_t = market.vol * math.sqrt(market.T)
    shift = (drift - market.vol**2 / 2) * market.T
    z = np.linspace(-10, 10, n_points)
    prices = market.spot * np.exp(shift + sigma_t * z)

    def wins(S):
        return np.asarray(pnl_expiry(legs, market, settings, S)) > ZERO_TOL

    signs = wins(prices)
    edges = [prices[0]]
    for i in np.nonzero(signs[1:] != signs[:-1])[0]:
        lo, hi = prices[i], prices[i + 1]
        for _ in range(200):
            mid = (lo + hi) / 2
            if wins(mid) == signs[i]:
                lo = mid
            else:
                hi = mid
        edges.append((lo + hi) / 2)
    edges.append(prices[-1])

    # El signo de cada tramo es el del primer punto de la rejilla dentro de él.
    total = 0.0
    current = bool(signs[0])
    for a, b in zip(edges[:-1], edges[1:]):
        if current:
            value, _ = quad(_lognormal_pdf, a, b, args=(market, drift), epsabs=1e-12, limit=200)
            total += value
        current = not current
    return total


def d2_at(market, x, drift=None):
    """d2 de Black-Scholes evaluado en el precio x (con crecimiento drift)."""
    if drift is None:
        drift = market.rate - market.q
    sigma_t = market.vol * math.sqrt(market.T)
    return (math.log(market.spot / x) + (drift - market.vol**2 / 2) * market.T) / sigma_t


# --- AC-A2: long call y long put contra N(d2) ---------------------------


def test_long_call_matches_reference_and_n_d2():
    legs = template_legs("long_call")
    pop = exact_pop(MARKET, legs, FEES, RISK_NEUTRAL)
    (breakeven,) = compute_metrics(legs, MARKET, FEES).breakevens
    assert breakeven == pytest.approx(103.69, abs=0.01)
    assert pop == pytest.approx(0.3392, abs=5e-4)
    assert pop == pytest.approx(norm.cdf(d2_at(MARKET, breakeven)), abs=1e-12)


def test_long_put_matches_n_minus_d2():
    legs = template_legs("long_put")
    pop = exact_pop(MARKET, legs, FEES, RISK_NEUTRAL)
    (breakeven,) = compute_metrics(legs, MARKET, FEES).breakevens
    assert pop == pytest.approx(norm.cdf(-d2_at(MARKET, breakeven)), abs=1e-12)
    assert pop == pytest.approx(0.3508, abs=5e-4)


# --- AC-A3: estrategias de varios tramos contra el oráculo --------------


@pytest.mark.parametrize(
    "key",
    ["long_straddle", "iron_condor", "bull_call_spread", "covered_call", "protective_put"],
)
@pytest.mark.parametrize("underlying,spot", [("Acción", 100.0), ("Índice", 4500.0)])
def test_multi_piece_strategies_match_oracle(key, underlying, spot):
    market = make_market(underlying, spot)
    legs = template_legs(key, market)
    pop = exact_pop(market, legs, FEES, RISK_NEUTRAL)
    assert pop == pytest.approx(oracle_pop(market, legs, FEES), abs=1e-6)


def test_iron_condor_reference_value():
    # El iron condor gana solo entre sus dos breakevens:
    # PoP = P(be_bajo < S_T < be_alto) = N(d2(be_bajo)) − N(d2(be_alto)).
    # Nota: el plan citaba 0,5323, pero con la plantilla del catálogo en el
    # mercado de referencia (strikes 90/95/105/110, comisiones por defecto)
    # la fórmula cerrada y el oráculo dan 0,5721 (ver informe de EXECUTE).
    legs = template_legs("iron_condor")
    low, high = compute_metrics(legs, MARKET, FEES).breakevens
    pop = exact_pop(MARKET, legs, FEES, RISK_NEUTRAL)
    closed_form = norm.cdf(d2_at(MARKET, low)) - norm.cdf(d2_at(MARKET, high))
    assert pop == pytest.approx(closed_form, abs=1e-12)
    assert pop == pytest.approx(0.5721, abs=5e-4)


@pytest.mark.parametrize("key", [t.key for t in TEMPLATES])
def test_whole_catalog_matches_oracle_with_high_fees(key):
    fees = CommissionSettings(per_contract=5.0)
    legs = template_legs(key)
    pop = exact_pop(MARKET, legs, fees, RISK_NEUTRAL)
    assert pop == pytest.approx(oracle_pop(MARKET, legs, fees), abs=1e-6)


# --- Saltos de comisión justo en el strike (enmienda A2) ----------------


def test_short_call_commission_jump_at_strike():
    # Prima 0,0095 -> +0,95 USD; abrir cuesta 0,65 -> P&L +0,30 por debajo de
    # K y −0,35 justo por encima (se paga el cierre): el signo cambia EN el strike.
    legs = [Leg("call", -1, 1, 105.0, 0.0095)]
    assert pnl_expiry(legs, MARKET, FEES, 104.999999) == pytest.approx(0.30, abs=1e-3)
    assert pnl_expiry(legs, MARKET, FEES, 105.000001) == pytest.approx(-0.35, abs=1e-3)
    pop = exact_pop(MARKET, legs, FEES, RISK_NEUTRAL)
    # Se gana exactamente cuando S_T < K: P = N(−d2(K)).
    assert pop == pytest.approx(norm.cdf(-d2_at(MARKET, 105.0)), abs=1e-12)
    assert pop == pytest.approx(oracle_pop(MARKET, legs, FEES), abs=1e-6)


def test_short_put_commission_jump_at_strike():
    legs = [Leg("put", -1, 1, 95.0, 0.0095)]
    pop = exact_pop(MARKET, legs, FEES, RISK_NEUTRAL)
    assert pop == pytest.approx(norm.cdf(d2_at(MARKET, 95.0)), abs=1e-12)
    assert pop == pytest.approx(oracle_pop(MARKET, legs, FEES), abs=1e-6)


@pytest.mark.parametrize("fee", [5.0, 20.0])
def test_iron_condor_with_large_fees_matches_oracle(fee):
    fees = CommissionSettings(per_contract=fee)
    legs = template_legs("iron_condor")
    pop = exact_pop(MARKET, legs, fees, RISK_NEUTRAL)
    assert pop == pytest.approx(oracle_pop(MARKET, legs, fees), abs=1e-6)


# --- Extremos: PoP = 0 y PoP = 1 -----------------------------------------


def test_pop_zero_when_fees_exceed_any_profit():
    fees = CommissionSettings(per_contract=60.0)
    legs = template_legs("iron_condor")
    assert compute_metrics(legs, MARKET, fees).best_pnl < 0
    assert exact_pop(MARKET, legs, fees, RISK_NEUTRAL) == 0.0


def test_pop_zero_for_overpriced_long_put():
    # Put comprada con prima mayor que su valor máximo posible (K = 100):
    # aunque S_T llegue a 0, la put vale 100 < 150 pagados -> nunca se gana.
    legs = [Leg("put", 1, 1, 100.0, 150.0)]
    assert exact_pop(MARKET, legs, FEES, RISK_NEUTRAL) == pytest.approx(0.0, abs=1e-12)


def test_pop_one_when_always_profitable():
    # Straddle gratis sin comisiones: P&L = 100·|S − K| > 0 salvo en S = K.
    legs = [Leg("call", 1, 1, 100.0, 0.0), Leg("put", 1, 1, 100.0, 0.0)]
    assert exact_pop(MARKET, legs, NO_FEES, RISK_NEUTRAL) == pytest.approx(1.0, abs=1e-12)


def test_pop_one_for_stock_bought_at_zero():
    legs = [Leg("stock", 1, 100, None, 0.0)]
    assert exact_pop(MARKET, legs, NO_FEES, RISK_NEUTRAL) == pytest.approx(1.0, abs=1e-12)


def test_pop_is_within_unit_interval_for_catalog():
    for template in TEMPLATES:
        pop = exact_pop(MARKET, build_legs(template, MARKET), FEES, RISK_NEUTRAL)
        assert 0.0 <= pop <= 1.0
        assert math.isfinite(pop)


# --- AC-A1 (parte exacta): neutral al riesgo vs μ -----------------------


def test_risk_neutral_uses_rate_minus_q():
    legs = template_legs("long_call")
    neutral = exact_pop(MARKET, legs, FEES, SimulationSettings(mu=None))
    explicit = exact_pop(MARKET, legs, FEES, SimulationSettings(mu=MARKET.rate - MARKET.q))
    assert neutral == pytest.approx(explicit, abs=1e-15)


def test_mu_mode_uses_mu():
    legs = template_legs("long_call")
    mu = 0.10
    (breakeven,) = compute_metrics(legs, MARKET, FEES).breakevens
    pop = exact_pop(MARKET, legs, FEES, SimulationSettings(mu=mu))
    assert pop == pytest.approx(norm.cdf(d2_at(MARKET, breakeven, drift=mu)), abs=1e-12)
    assert pop == pytest.approx(oracle_pop(MARKET, legs, FEES, drift=mu), abs=1e-6)


def test_higher_mu_increases_long_call_pop():
    legs = template_legs("long_call")
    pops = [exact_pop(MARKET, legs, FEES, SimulationSettings(mu=mu)) for mu in (-0.5, 0.0, 0.1, 1.0)]
    assert pops == sorted(pops)
    assert len(set(pops)) == 4
    assert pops[0] == pytest.approx(0.123, abs=1e-3)
    assert pops[-1] == pytest.approx(0.828, abs=1e-3)


def test_pop_does_not_depend_on_seed_or_paths():
    legs = template_legs("iron_condor")
    a = exact_pop(MARKET, legs, FEES, SimulationSettings(n_paths=1_000, seed=1))
    b = exact_pop(MARKET, legs, FEES, SimulationSettings(n_paths=500_000, seed=99))
    assert a == b


def test_simulation_settings_defaults():
    sim = SimulationSettings()
    assert sim.n_paths == 100_000
    assert sim.seed == 42
    assert sim.mu is None


# =====================================================================
# Bloque 3a: Monte Carlo y ScenarioResult
# =====================================================================

FLOAT_FIELDS = ["pop_exact", "pop_mc", "mean_pnl", "pnl_std", "p5", "p50", "p95", "mu_used"]


def assert_all_finite(result):
    """Ningún campo del resultado puede ser NaN ni infinito (AC-A10)."""
    for name in FLOAT_FIELDS:
        value = getattr(result, name)
        assert isinstance(value, float), name
        assert math.isfinite(value), name
    assert np.all(np.isfinite(result.hist_counts))
    assert np.all(np.isfinite(result.hist_edges))


# --- AC-A8: valores por defecto y reproducibilidad -----------------------


def test_scenario_uses_default_paths_and_records_them():
    result = simulate_scenario(MARKET, template_legs("long_call"), FEES, SimulationSettings())
    assert isinstance(result, ScenarioResult)
    assert result.n_paths == 100_000
    assert isinstance(result.n_paths, int)
    assert result.hist_counts.sum() == 100_000


def test_same_seed_gives_identical_result():
    legs = template_legs("iron_condor")
    a = simulate_scenario(MARKET, legs, FEES, SimulationSettings(seed=42))
    b = simulate_scenario(MARKET, legs, FEES, SimulationSettings(seed=42))
    for name in FLOAT_FIELDS:
        assert getattr(a, name) == getattr(b, name), name
    assert np.array_equal(a.hist_counts, b.hist_counts)
    assert np.array_equal(a.hist_edges, b.hist_edges)


def test_other_seed_changes_mc_but_not_exact_pop():
    legs = template_legs("iron_condor")
    a = simulate_scenario(MARKET, legs, FEES, SimulationSettings(seed=42))
    b = simulate_scenario(MARKET, legs, FEES, SimulationSettings(seed=7))
    assert a.pop_exact == b.pop_exact
    assert a.pop_mc != b.pop_mc
    assert a.mean_pnl != b.mean_pnl


def test_pop_exact_field_is_the_exact_pop():
    legs = template_legs("iron_condor")
    result = simulate_scenario(MARKET, legs, FEES, RISK_NEUTRAL)
    assert result.pop_exact == exact_pop(MARKET, legs, FEES, RISK_NEUTRAL)
    assert result.pop_exact == pytest.approx(0.5721, abs=5e-4)


# --- AC-A1: media de S_T y escenario μ -----------------------------------


def test_mean_terminal_price_is_forward_in_risk_neutral_mode():
    drift = MARKET.rate - MARKET.q
    prices = _sample_terminal(MARKET, SimulationSettings(), drift)
    assert prices.shape == (100_000,)
    expected = MARKET.spot * math.exp(drift * MARKET.T)
    standard_error = prices.std() / math.sqrt(prices.size)
    assert abs(prices.mean() - expected) <= 4 * standard_error


def test_mean_terminal_price_follows_mu():
    mu = 0.5
    prices = _sample_terminal(MARKET, SimulationSettings(mu=mu), mu)
    expected = MARKET.spot * math.exp(mu * MARKET.T)
    standard_error = prices.std() / math.sqrt(prices.size)
    assert abs(prices.mean() - expected) <= 4 * standard_error


def test_simulation_uses_the_sampling_helper():
    # Enmienda A8: simulate_scenario usa exactamente las muestras de
    # _sample_terminal (misma semilla -> mismos precios -> mismos números).
    legs = template_legs("long_call")
    sim = SimulationSettings(seed=123)
    result = simulate_scenario(MARKET, legs, FEES, sim)
    prices = _sample_terminal(MARKET, sim, MARKET.rate - MARKET.q)
    pnl = pnl_expiry(legs, MARKET, FEES, prices)
    assert result.pop_mc == float(np.mean(pnl > ZERO_TOL))
    assert result.mean_pnl == float(np.mean(pnl))
    assert result.p50 == float(np.percentile(pnl, 50))


def test_mu_used_reports_the_scenario():
    legs = template_legs("long_call")
    neutral = simulate_scenario(MARKET, legs, FEES, SimulationSettings())
    assert neutral.mu_used == pytest.approx(MARKET.rate - MARKET.q, abs=1e-15)
    custom = simulate_scenario(MARKET, legs, FEES, SimulationSettings(mu=0.2))
    assert custom.mu_used == 0.2


def test_higher_mu_increases_simulated_long_call_results():
    legs = template_legs("long_call")
    results = [simulate_scenario(MARKET, legs, FEES, SimulationSettings(mu=mu)) for mu in (-0.5, 0.0, 1.0)]
    pops = [r.pop_mc for r in results]
    means = [r.mean_pnl for r in results]
    assert pops == sorted(pops) and len(set(pops)) == 3
    assert means == sorted(means) and len(set(means)) == 3


# --- AC-A4: PoP simulada vs exacta en todo el catálogo ------------------


@pytest.mark.parametrize("key", [t.key for t in TEMPLATES])
@pytest.mark.parametrize("underlying,spot", [("Acción", 100.0), ("Índice", 4500.0)])
@pytest.mark.parametrize("fee", [0.65, 5.0])
def test_mc_pop_within_four_standard_errors_of_exact(key, underlying, spot, fee):
    market = make_market(underlying, spot)
    fees = CommissionSettings(per_contract=fee)
    result = simulate_scenario(market, template_legs(key, market), fees, RISK_NEUTRAL)
    p = result.pop_exact
    standard_error = math.sqrt(p * (1 - p) / result.n_paths)
    assert abs(result.pop_mc - p) <= 4 * standard_error


# --- AC-A5: percentiles e histograma ------------------------------------


@pytest.mark.parametrize("key", [t.key for t in TEMPLATES])
def test_percentiles_ordered_and_inside_metric_range(key):
    legs = template_legs(key)
    result = simulate_scenario(MARKET, legs, FEES, RISK_NEUTRAL)
    assert result.p5 <= result.p50 <= result.p95
    metrics = compute_metrics(legs, MARKET, FEES)
    if metrics.worst_pnl is not None:
        assert result.p5 >= metrics.worst_pnl - 1e-9
    if metrics.best_pnl is not None:
        assert result.p95 <= metrics.best_pnl + 1e-9
    assert result.hist_counts.sum() == result.n_paths
    assert len(result.hist_edges) == len(result.hist_counts) + 1
    assert len(result.hist_counts) == 50
    assert np.all(np.diff(result.hist_edges) > 0)


def test_histogram_is_clipped_to_central_percentiles():
    # Long call: ganancia ilimitada. El histograma cubre del percentil 0,5 %
    # al 99,5 %; lo que queda fuera se acumula en los bins de los extremos.
    legs = template_legs("long_call")
    sim = SimulationSettings()
    result = simulate_scenario(MARKET, legs, FEES, sim)
    pnl = pnl_expiry(legs, MARKET, FEES, _sample_terminal(MARKET, sim, MARKET.rate - MARKET.q))
    low, high = np.percentile(pnl, [0.5, 99.5])
    assert result.hist_edges[0] == pytest.approx(low)
    assert result.hist_edges[-1] == pytest.approx(high)
    assert pnl.max() > high  # hay cola fuera del rango...
    assert result.hist_counts[-1] >= np.sum(pnl > high)  # ...y cae en el último bin
    assert result.hist_counts.sum() == sim.n_paths


def test_histogram_handles_constant_pnl():
    # Call comprada + put vendida (strike 100, prima 0) + 100 acciones
    # vendidas a 100: al vencimiento el P&L es siempre 0 (todos los
    # percentiles iguales). El histograma no debe romperse.
    legs = [
        Leg("call", 1, 1, 100.0, 0.0),
        Leg("put", -1, 1, 100.0, 0.0),
        Leg("stock", -1, 100, None, 100.0),
    ]
    result = simulate_scenario(MARKET, legs, NO_FEES, RISK_NEUTRAL)
    assert result.hist_counts.sum() == result.n_paths
    assert result.p5 == pytest.approx(result.p95, abs=1e-6)
    assert_all_finite(result)


# --- AC-A6: valor esperado (no descontado) del long call ----------------


def _long_call_ev_formula(market, leg, settings):
    """100·prima·(e^{rT} − 1) − comisión de apertura − comisión de cierre·P(S_T > K)."""
    fee = open_fee(leg, market, settings)  # misma tarifa al cerrar
    prob_itm = norm.cdf(d2_at(market, leg.strike))
    return 100 * leg.price * (math.exp(market.rate * market.T) - 1) - fee - fee * prob_itm


def test_long_call_ev_formula_matches_numeric_integration():
    # Enmienda A3: comprobación determinista (sin azar) de la fórmula contra
    # la integral del P&L del motor sobre la densidad normal de z.
    legs = template_legs("long_call")
    drift = MARKET.rate - MARKET.q
    sigma_t = MARKET.vol * math.sqrt(MARKET.T)
    z = np.linspace(-10, 10, 2_000_001)
    prices = MARKET.spot * np.exp((drift - MARKET.vol**2 / 2) * MARKET.T + sigma_t * z)
    pnl = np.asarray(pnl_expiry(legs, MARKET, FEES, prices))
    integral = np.trapezoid(pnl * norm.pdf(z), z)
    formula = _long_call_ev_formula(MARKET, legs[0], FEES)
    assert integral == pytest.approx(formula, abs=1e-3)
    assert formula == pytest.approx(0.8435, abs=1e-3)


def test_long_call_mc_mean_matches_ev_formula():
    legs = template_legs("long_call")
    result = simulate_scenario(MARKET, legs, FEES, RISK_NEUTRAL)
    formula = _long_call_ev_formula(MARKET, legs[0], FEES)
    standard_error = result.pnl_std / math.sqrt(result.n_paths)
    assert abs(result.mean_pnl - formula) <= 4 * standard_error


# --- AC-A10: sin NaN ni infinitos en casos extremos ---------------------


@pytest.mark.parametrize("key", [t.key for t in TEMPLATES])
@pytest.mark.parametrize("vol,days", [(3.0, 45), (0.25, 1), (3.0, 1), (0.01, 365)])
@pytest.mark.parametrize("mu", [None, -0.5, 1.0])
def test_results_are_finite_in_extreme_cases(key, vol, days, mu):
    market = Market(underlying="Acción", spot=100.0, vol=vol, days=days, rate=0.04, q=0.01)
    sim = SimulationSettings(n_paths=1_000, mu=mu)
    result = simulate_scenario(market, template_legs(key, market), FEES, sim)
    assert_all_finite(result)
    assert 0.0 <= result.pop_mc <= 1.0
    assert result.hist_counts.sum() == 1_000


# --- AC-A9: rapidez ----------------------------------------------------


def test_iron_condor_100k_paths_under_one_second():
    legs = template_legs("iron_condor")
    simulate_scenario(MARKET, legs, FEES, RISK_NEUTRAL)  # calentamiento
    start = time.perf_counter()
    simulate_scenario(MARKET, legs, FEES, RISK_NEUTRAL)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0
