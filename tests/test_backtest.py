"""Tests de run_backtest (Etapa C2, bloque 3).

Cubre AC-C2-5 (sin mirar el futuro), AC-C2-6 (muestreo, cola y arranque
saltados y contados), AC-C2-7 (Black-Scholes forzado, build_legs,
fechas inválidas, ganar con y sin comisiones), AC-C2-10 y AC-C2-11
(oráculos con series sintéticas), AC-C2-12 (línea μ y N efectivo) y
AC-C2-15 (tiempo).

Oráculos: series de 40 años sintéticos (10 080 sesiones), iron condor,
H = 30, W = 30, paso 10 (980 fechas), comisiones por defecto, r = q = 0.
Valores MEDIDOS (21-11-26) con estas entradas exactas y cotas usadas
(ninguna a menos del 25 % del valor medido):

- GBM σ = 20 %: |media PoP − tasa observada| = 0,0083 (semilla 1) y
  0,0276 (semilla 2) ≤ 0,05; |curtosis en exceso| = 0,152 / 0,032 < 1.
- Regímenes 10/20/40 % en bloques de 504 sesiones (E-3): desviación
  máxima en deciles con n ≥ 100 = 0,083 / 0,110 ≤ 0,15; brecha
  (Brier climatológico − Brier) = 0,060 / 0,061 ≥ 0,03;
  |Brier − Σp(1−p)/N| = 0,007 / 0,017 ≤ 0,04.
- Saltos (10 % + 2 % de días con salto N(0, 6 %)), semilla 1: curtosis
  en exceso 4,79 > 2; desviación máxima 0,447 ≥ 0,20.
- Tiempo de cada oráculo: ≈ 1,5-1,7 s.
"""

import math
import time

import numpy as np
import pytest

import opciones.backtest as backtest_module
from opciones import TEMPLATES, CommissionSettings, Market, build_legs
from opciones.backtest import (
    SKIP_REASONS,
    BacktestResult,
    expiry_index,
    realized_vol,
    run_backtest,
    to_day_numbers,
    trailing_dividend_yield,
    trailing_mu,
)
from opciones.calibration import (
    brier_score,
    calibration_bins,
    climatological_brier,
    effective_n,
    max_deviation,
    tail_diagnostics,
)
from opciones.simulation import exact_pop
from tests.synthetic import business_days, gbm_series, jump_series, regime_series

IRON_CONDOR = next(t for t in TEMPLATES if t.key == "iron_condor")
FEES = CommissionSettings()
NO_FEES = CommissionSettings(per_contract=0.0, index_surcharge=0.0, include_close=False)

H = 30
W = 30
ORACLE_SESSIONS = 40 * 252
ORACLE_STEP = 10


def _run(series, step=5, settings=FEES, **kwargs):
    """run_backtest con valores por defecto de los tests (sin dividendos ni ^IRX)."""
    dates, close, adj = series
    options = dict(
        div_dates=None,
        div_amounts=None,
        rate_dates=None,
        rate_values=None,
        template=IRON_CONDOR,
        underlying="ETF",
        horizon_days=H,
        vol_window=W,
        step=step,
        settings=settings,
        fallback_rate=0.0,
    )
    options.update(kwargs)
    return run_backtest(dates, close, adj, **options)


class _Spy:
    """Envuelve exact_pop y guarda cada (mercado, patas, μ) con que se llama."""

    def __init__(self):
        self.calls = []

    def __call__(self, market, legs, settings, sim):
        self.calls.append((market, legs, sim.mu))
        return exact_pop(market, legs, settings, sim)


# --- Estructura y muestreo --------------------------------------------------


def test_estructura_del_resultado():
    result = _run(gbm_series(400, 0.2, seed=1))
    assert isinstance(result, BacktestResult)
    assert set(result.skipped) == set(SKIP_REASONS)
    assert set(SKIP_REASONS) == {"no_window", "no_expiry", "invalid_market", "no_rate"}
    n = result.n
    assert n > 0
    for array in (result.dates, result.pop, result.win, result.z, result.vol):
        assert len(array) == n
    assert result.pop_mu is None
    assert np.all((result.pop >= 0) & (result.pop <= 1))
    assert np.all(np.isfinite(result.z)) and np.all(np.isfinite(result.vol))


def test_muestreo_por_paso_y_saltos_contados():
    series = gbm_series(400, 0.2, seed=1)
    days = to_day_numbers(series[0])
    step = 7
    result = _run(series, step=step)
    sampled = list(range(0, 400, step))
    no_window = [i for i in sampled if i < 252]
    no_expiry = [i for i in sampled if i >= 252 and days[i] + H > days[-1]]
    kept = [i for i in sampled if i >= 252 and days[i] + H <= days[-1]]
    assert result.skipped["no_window"] == len(no_window) == 36
    assert result.skipped["no_expiry"] == len(no_expiry) > 0
    assert result.skipped["invalid_market"] == 0 and result.skipped["no_rate"] == 0
    assert list(result.dates) == [series[0][i] for i in kept]


def test_first_date_marca_el_inicio():
    series = gbm_series(400, 0.2, seed=1)
    result = _run(series, step=5, first_date=series[0][300])
    assert result.dates[0] == series[0][300]
    assert result.skipped["no_window"] == 0


def test_years_analyzed_y_n_efectivo():
    series = gbm_series(1000, 0.2, seed=1)
    result = _run(series, step=5)
    days = to_day_numbers([result.dates[0], result.dates[-1]])
    assert result.years_analyzed == pytest.approx((days[1] - days[0]) / 365.25)
    expected = min(result.n, result.years_analyzed * 365 / H)
    assert effective_n(result.n, result.years_analyzed, H) == pytest.approx(expected)
    assert expected < result.n  # el solapamiento reduce N


def test_sin_fechas_avisa():
    result = _run(gbm_series(200, 0.2, seed=1))
    assert result.n == 0
    assert backtest_module.MSG_NO_DATES in result.warnings


# --- Modelo, patas y mercado ------------------------------------------------


def test_modelo_forzado_black_scholes_y_patas_del_catalogo(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(backtest_module, "exact_pop", spy)
    series = gbm_series(400, 0.2, seed=2)
    result = _run(series, step=20)
    assert len(spy.calls) == result.n > 0
    for market, legs, mu in spy.calls:
        assert market.pricing_model == "black_scholes"
        assert market.days == H
        assert mu is None
        expected = build_legs(IRON_CONDOR, market)
        assert [(l.kind, l.side, l.strike) for l in legs] == [(l.kind, l.side, l.strike) for l in expected]
        assert [l.price for l in legs] == pytest.approx([l.price for l in expected])


def test_mercado_usa_vol_q_y_r_del_dia(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(backtest_module, "exact_pop", spy)
    dates, close, adj = gbm_series(400, 0.2, seed=3)
    div_dates = [dates[100], dates[200], dates[300]]
    amounts = [0.5, 0.6, 0.7]
    rate_dates = [dates[0], dates[280]]
    rates = [0.01, 0.05]
    i = 290
    _run(
        (dates, close, adj),
        step=1000,
        first_date=dates[i],
        div_dates=div_dates,
        div_amounts=amounts,
        rate_dates=rate_dates,
        rate_values=rates,
        underlying="Acción",
    )
    market = spy.calls[0][0]
    assert market.spot == pytest.approx(close[i])
    assert market.vol == pytest.approx(realized_vol(adj, i, W))
    expected_q = trailing_dividend_yield(to_day_numbers(div_dates), np.array(amounts), to_day_numbers([dates[i]])[0], close[i])
    assert expected_q > 0
    assert market.q == pytest.approx(expected_q)
    assert market.rate == pytest.approx(0.05)
    assert market.underlying == "Acción"


def test_indice_q_cero_con_nota(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(backtest_module, "exact_pop", spy)
    dates, close, adj = gbm_series(400, 0.2, seed=3)
    result = _run((dates, close, adj), step=50, div_dates=[dates[280]], div_amounts=[5.0], underlying="Índice")
    assert all(call[0].q == 0.0 for call in spy.calls)
    assert backtest_module.MSG_INDEX_NO_DIVIDENDS in result.warnings


def test_tasa_constante_de_respaldo_con_aviso():
    result = _run(gbm_series(400, 0.2, seed=1), fallback_rate=0.03)
    assert backtest_module.MSG_RATE_FALLBACK in result.warnings


def test_vol_menor_que_minima_cuenta_invalid_market():
    dates = business_days(400)
    flat = np.full(400, 100.0)
    result = _run((dates, flat, flat.copy()), step=5)
    assert result.n == 0
    assert result.skipped["invalid_market"] > 0
    assert result.skipped["invalid_market"] + result.skipped["no_window"] + result.skipped["no_expiry"] == len(
        range(0, 400, 5)
    )


def test_no_rate_contado():
    series = gbm_series(400, 0.2, seed=1)
    dates = series[0]
    # El ^IRX empieza en la sesión 300: las fechas 255..295 no tienen tasa.
    result = _run(series, step=5, rate_dates=[dates[300]], rate_values=[0.04])
    sampled_without_rate = [i for i in range(0, 400, 5) if 252 <= i < 300]
    assert result.skipped["no_rate"] == len(sampled_without_rate)
    assert backtest_module.MSG_RATE_FALLBACK not in result.warnings


# --- Ganar con y sin comisiones (caso a mano) -------------------------------


def _hand_case(final_price_rule):
    """Serie de 300 sesiones con el cierre de vencimiento fijado a mano."""
    dates, close, adj = gbm_series(300, 0.2, seed=5)
    i = 260
    days = to_day_numbers(dates)
    j = expiry_index(days, i, H)
    # Volatilidad "a mano": std (ddof=1) de 30 log-rendimientos × √252.
    returns = np.log(adj[i - 29 : i + 1] / adj[i - 30 : i])
    vol = float(np.std(returns, ddof=1) * math.sqrt(252))
    market = Market("ETF", float(close[i]), vol, H, 0.0, 0.0, "black_scholes")
    legs = build_legs(IRON_CONDOR, market)
    close = close.copy()
    adj = adj.copy()
    close[j] = adj[j] = final_price_rule(market, legs)
    return (dates, close, adj), dates[i]


def _credit(legs):
    """Prima neta cobrada por acción (positiva en un iron condor)."""
    return sum(-leg.side * leg.price for leg in legs)


@pytest.mark.parametrize(
    "rule, win_with_fees, win_without_fees",
    [
        # Precio en el centro: se cobra toda la prima (> comisiones de 2,60).
        (lambda m, legs: m.spot, True, True),
        # Precio 0,01 por debajo del breakeven sin comisiones de la call
        # vendida: P&L bruto = 100 × 0,01 = +1,00 USD; con comisiones
        # 1,00 − 2,60 (apertura) − 0,65 (cierre de la call ITM) = −2,25.
        (lambda m, legs: legs[2].strike + _credit(legs) - 0.01, False, True),
        # Precio muy alto: pérdida máxima con y sin comisiones.
        (lambda m, legs: m.spot * 1.5, False, False),
    ],
)
def test_ganar_con_y_sin_comisiones(rule, win_with_fees, win_without_fees):
    series, first = _hand_case(rule)
    with_fees = _run(series, step=1000, first_date=first, settings=FEES)
    without_fees = _run(series, step=1000, first_date=first, settings=NO_FEES)
    assert with_fees.n == without_fees.n == 1
    assert bool(with_fees.win[0]) is win_with_fees
    assert bool(without_fees.win[0]) is win_without_fees


def test_z_calculado_a_mano():
    series, first = _hand_case(lambda m, legs: m.spot * 1.05)
    result = _run(series, step=1000, first_date=first)
    vol = result.vol[0]
    T = H / 365
    expected = (math.log(1.05) - (0.0 - vol**2 / 2) * T) / (vol * math.sqrt(T))
    assert result.z[0] == pytest.approx(expected, rel=1e-9)


# --- Sin mirar el futuro (AC-C2-5, AC-C2-12) --------------------------------


def _future_case():
    dates, close, adj = gbm_series(400, 0.25, seed=7)
    div_dates = [dates[150], dates[310], dates[330]]
    amounts = [0.4, 0.5, 0.6]
    rate_dates = [dates[0], dates[305], dates[320]]
    rates = [0.02, 0.03, 0.04]
    return dates, close, adj, div_dates, amounts, rate_dates, rates


def _run_future(dates, close, adj, div_dates, amounts, rate_dates, rates, first):
    return _run(
        (dates, close, adj),
        step=1000,
        first_date=first,
        div_dates=div_dates,
        div_amounts=amounts,
        rate_dates=rate_dates,
        rate_values=rates,
        underlying="Acción",
        with_mu=True,
    )


def test_sin_mirar_el_futuro_pop_vol_y_mu():
    dates, close, adj, div_dates, amounts, rate_dates, rates = _future_case()
    i = 310
    before = _run_future(dates, close, adj, div_dates, amounts, rate_dates, rates, dates[i])

    # Se altera TODO lo posterior a t: precios, dividendos y ^IRX.
    close2 = close.copy()
    adj2 = adj.copy()
    close2[i + 1 :] *= 1.7
    adj2[i + 1 :] *= 0.6
    amounts2 = [0.4, 0.5, 9.0]  # el de la sesión 330 es futuro
    rates2 = [0.02, 0.03, 0.09]  # el de la sesión 320 es futuro
    after = _run_future(dates, close2, adj2, div_dates, amounts2, rate_dates, rates2, dates[i])

    assert before.n == after.n == 1
    assert after.pop[0] == before.pop[0]
    assert after.pop_mu[0] == before.pop_mu[0]
    assert after.vol[0] == before.vol[0]


def test_sin_mirar_el_futuro_win_si_no_cambia_el_vencimiento():
    dates, close, adj, div_dates, amounts, rate_dates, rates = _future_case()
    i = 300
    j = expiry_index(to_day_numbers(dates), i, H)
    before = _run_future(dates, close, adj, div_dates, amounts, rate_dates, rates, dates[i])
    close2 = close.copy()
    adj2 = adj.copy()
    # Se altera todo salvo el cierre de vencimiento.
    close2[i + 1 : j] *= 1.3
    close2[j + 1 :] *= 0.5
    adj2[i + 1 :] *= 1.2
    after = _run_future(dates, close2, adj2, div_dates, [0.4, 0.5, 3.0], rate_dates, [0.02, 0.03, 0.2], dates[i])
    assert after.win[0] == before.win[0]
    assert after.pop[0] == before.pop[0]
    assert after.z[0] == before.z[0]


# --- Línea μ (AC-C2-12) -----------------------------------------------------


def test_linea_mu_presente_con_el_mismo_n(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(backtest_module, "exact_pop", spy)
    series = gbm_series(400, 0.2, seed=4)
    result = _run(series, step=10, with_mu=True)
    neutral = _run(series, step=10)
    assert result.pop_mu is not None
    assert len(result.pop_mu) == result.n == neutral.n
    np.testing.assert_array_equal(result.pop, neutral.pop)
    # El μ usado es el histórico de 252 sesiones con datos ≤ t.
    adj = series[2]
    mus = [mu for _, _, mu in spy.calls if mu is not None]
    days = to_day_numbers(series[0])
    first_i = int(np.searchsorted(days, to_day_numbers([result.dates[0]])[0]))
    assert mus[0] == pytest.approx(trailing_mu(adj, first_i, result.vol[0]))


# --- Oráculos (AC-C2-10, AC-C2-11) -----------------------------------------


@pytest.mark.parametrize("seed", [1, 2])
def test_oraculo_gbm_calibrado_en_agregado(seed):
    result = _run(gbm_series(ORACLE_SESSIONS, 0.20, seed=seed), step=ORACLE_STEP)
    assert result.n >= 900
    # Medido: 0,0083 (semilla 1), 0,0276 (semilla 2).
    assert abs(result.pop.mean() - result.win.mean()) <= 0.05
    # Medido: 0,152 / 0,032.
    assert abs(tail_diagnostics(result.z).excess_kurtosis) < 1.0


@pytest.mark.parametrize("seed", [1, 2])
def test_oraculo_regimenes_deciles_y_brier(seed):
    result = _run(regime_series(ORACLE_SESSIONS, seed=seed, block=504), step=ORACLE_STEP)
    rows = calibration_bins(result.pop, result.win)
    full = [row for row in rows if row.n >= 100]
    assert len(full) >= 5
    # Medido: 0,083 (semilla 1), 0,110 (semilla 2).
    for row in full:
        assert abs(row.observed - row.mean_pop) <= 0.15
    brier = brier_score(result.pop, result.win)
    # Medido: brecha 0,060 / 0,061.
    assert climatological_brier(result.win) - brier >= 0.03
    # Medido: 0,007 / 0,017.
    assert abs(brier - float(np.mean(result.pop * (1 - result.pop)))) <= 0.04


def test_oraculo_saltos_colas_gordas_y_descalibrado():
    result = _run(jump_series(ORACLE_SESSIONS, seed=1), step=ORACLE_STEP)
    # Medido: curtosis 4,79; desviación máxima 0,447.
    assert tail_diagnostics(result.z).excess_kurtosis > 2
    assert max_deviation(calibration_bins(result.pop, result.win)) >= 0.20


# --- Tiempo (AC-C2-15) ------------------------------------------------------


def test_tiempo_diez_anos_paso_5():
    series = gbm_series(11 * 252, 0.2, seed=1)
    start = time.perf_counter()
    result = _run(series, step=5)
    elapsed = time.perf_counter() - start
    assert result.n >= 440
    assert elapsed < 5.0


def test_tiempo_diez_anos_paso_5_con_mu():
    series = gbm_series(11 * 252, 0.2, seed=1)
    start = time.perf_counter()
    result = _run(series, step=5, with_mu=True)
    elapsed = time.perf_counter() - start
    assert result.n >= 440
    assert elapsed < 10.0
