"""Tests de la probabilidad de beneficio (PoP) exacta (Etapa A, bloque 2).

Criterios: AC-A1 (parte exacta: neutral al riesgo vs μ), AC-A2 (long
call = N(d2), long put = N(−d2)) y AC-A3 (estrategias con varios tramos
contra una integración numérica independiente, y extremos PoP = 0 / 1).

El oráculo independiente NO usa los breakevens de las métricas: busca
los cambios de signo del P&L con una rejilla muy densa, afina cada uno
por bisección y luego integra la densidad lognormal con
scipy.integrate.quad (enmienda A2 del contrato de validación).
"""

import math

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import norm

from opciones import TEMPLATES, CommissionSettings, Leg, Market, build_legs, compute_metrics
from opciones.metrics import ZERO_TOL
from opciones.payoff import pnl_expiry
from opciones.simulation import SimulationSettings, exact_pop

FEES = CommissionSettings()  # 0,65 USD por contrato, cierre incluido
NO_FEES = CommissionSettings(per_contract=0.0, index_surcharge=0.0, include_close=True)
RISK_NEUTRAL = SimulationSettings()  # mu = None


def make_market(underlying="Acción", spot=100.0):
    """Mercado de referencia del SPEC: σ 25 %, 45 días, r 4 %, q 1 %."""
    return Market(underlying=underlying, spot=spot, vol=0.25, days=45, rate=0.04, q=0.01)


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
