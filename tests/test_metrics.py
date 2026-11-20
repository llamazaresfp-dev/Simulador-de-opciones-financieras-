"""Tests de métricas exactas al vencimiento (bloque 3: AC10, AC11, AC12, AC14).

Los valores de libro usan comisiones a cero. Los casos con comisiones
(0,65 USD por contrato, cierre incluido) están calculados a mano y
recalculados en el comentario de cada test.
"""

import numpy as np
import pytest

from opciones import CommissionSettings, Leg, Market, compute_metrics
from opciones.payoff import pnl_expiry

NO_FEES = CommissionSettings(per_contract=0.0, index_surcharge=0.0, include_close=True)
FEES = CommissionSettings()  # 0,65 USD por contrato, cierre incluido
MARKET = Market(underlying="Acción", spot=100, vol=0.20, days=30, rate=0.05)

PNL_TOL = 1e-6  # tolerancia para valores de P&L (USD)
BE_TOL = 1e-3  # tolerancia para breakevens (precio)


def call(side, strike, price, qty=1):
    return Leg("call", side, qty, strike, price)


def put(side, strike, price, qty=1):
    return Leg("put", side, qty, strike, price)


def stock(side, price, qty=100):
    return Leg("stock", side, qty, None, price)


def metrics(legs, settings=NO_FEES):
    return compute_metrics(legs, MARKET, settings)


def assert_breakevens(result, expected):
    assert len(result.breakevens) == len(expected)
    for got, want in zip(result.breakevens, expected):
        assert got == pytest.approx(want, abs=BE_TOL)


# --- Estrategias de libro, sin comisiones (AC10, AC11, AC12) ------------

def test_long_call():
    m = metrics([call(+1, 100, 3.0)])
    assert m.profit_unlimited and not m.loss_unlimited
    assert m.best_pnl is None
    assert m.worst_pnl == pytest.approx(-300.0, abs=PNL_TOL)  # prima × 100
    assert_breakevens(m, [103.0])  # K + prima


def test_long_put():
    m = metrics([put(+1, 100, 3.0)])
    assert not m.profit_unlimited and not m.loss_unlimited
    assert m.best_pnl == pytest.approx(9700.0, abs=PNL_TOL)  # en S = 0
    assert m.worst_pnl == pytest.approx(-300.0, abs=PNL_TOL)
    assert_breakevens(m, [97.0])


def test_short_call():
    m = metrics([call(-1, 100, 3.0)])
    assert m.loss_unlimited and not m.profit_unlimited
    assert m.worst_pnl is None
    assert m.best_pnl == pytest.approx(300.0, abs=PNL_TOL)
    assert_breakevens(m, [103.0])


def test_short_put():
    m = metrics([put(-1, 100, 3.0)])
    assert not m.profit_unlimited and not m.loss_unlimited
    assert m.best_pnl == pytest.approx(300.0, abs=PNL_TOL)
    assert m.worst_pnl == pytest.approx(-9700.0, abs=PNL_TOL)
    assert_breakevens(m, [97.0])


def test_long_straddle_two_breakevens():
    m = metrics([call(+1, 100, 3.0), put(+1, 100, 3.0)])
    assert m.profit_unlimited and not m.loss_unlimited
    assert m.worst_pnl == pytest.approx(-600.0, abs=PNL_TOL)
    assert_breakevens(m, [94.0, 106.0])


def test_bull_call_spread_never_loses_more_than_paid():
    # Pagado: (3 − 1) × 100 = 200. Ganancia máx.: (110 − 100) × 100 − 200 = 800.
    m = metrics([call(+1, 100, 3.0), call(-1, 110, 1.0)])
    assert not m.profit_unlimited and not m.loss_unlimited
    assert m.worst_pnl == pytest.approx(-200.0, abs=PNL_TOL)
    assert m.best_pnl == pytest.approx(800.0, abs=PNL_TOL)
    assert_breakevens(m, [102.0])


def test_bear_put_spread():
    # Largo put 110 @ 6, corto put 100 @ 2: coste 400, ganancia máx. 600.
    m = metrics([put(+1, 110, 6.0), put(-1, 100, 2.0)])
    assert m.worst_pnl == pytest.approx(-400.0, abs=PNL_TOL)
    assert m.best_pnl == pytest.approx(600.0, abs=PNL_TOL)
    assert_breakevens(m, [106.0])


CONDOR = [put(+1, 90, 0.5), put(-1, 95, 1.5), call(-1, 105, 1.5), call(+1, 110, 0.5)]


def test_iron_condor_no_fees():
    m = metrics(CONDOR)
    assert not m.profit_unlimited and not m.loss_unlimited
    assert m.best_pnl == pytest.approx(200.0, abs=PNL_TOL)
    assert m.worst_pnl == pytest.approx(-300.0, abs=PNL_TOL)
    assert_breakevens(m, [93.0, 107.0])


def test_covered_call():
    # Acción @ 100 + call corto 105 @ 2: máx. (5 + 2) × 100; mín. en S = 0.
    m = metrics([stock(+1, 100.0), call(-1, 105, 2.0)])
    assert not m.profit_unlimited and not m.loss_unlimited
    assert m.best_pnl == pytest.approx(700.0, abs=PNL_TOL)
    assert m.worst_pnl == pytest.approx(-9800.0, abs=PNL_TOL)
    assert_breakevens(m, [98.0])


def test_protective_put():
    # Acción @ 100 + put largo 95 @ 2: pérdida máx. (95 − 100 − 2) × 100.
    m = metrics([stock(+1, 100.0), put(+1, 95, 2.0)])
    assert m.profit_unlimited and not m.loss_unlimited
    assert m.worst_pnl == pytest.approx(-700.0, abs=PNL_TOL)
    assert_breakevens(m, [102.0])


def test_no_breakeven_always_positive():
    # Acción @ 100 + put largo 110 @ 5: P&L = max(S, 110) − 105 >= 5 (× 100).
    m = metrics([stock(+1, 100.0), put(+1, 110, 5.0)])
    assert m.breakevens == []
    assert m.worst_pnl == pytest.approx(500.0, abs=PNL_TOL)
    assert m.profit_unlimited


def test_three_breakevens():
    # Coste neto 1 → −100 hasta 100; sube a +400 en 105; baja a −600 en 115;
    # después sube con pendiente +100 → tres cruces: 101, 109 y 121.
    legs = [call(+1, 100, 2.0), call(-1, 105, 0.5, qty=2), call(+1, 115, 0.0, qty=2)]
    m = metrics(legs)
    assert m.profit_unlimited and not m.loss_unlimited
    assert m.worst_pnl == pytest.approx(-600.0, abs=PNL_TOL)
    assert_breakevens(m, [101.0, 109.0, 121.0])


# --- Casos de comisión calculados a mano (AC14) -------------------------

def test_short_call_with_fees():
    # S <= 100: 200 − 0,65 = 199,35. S > 100: además paga cierre (0,65),
    # P = 200 − 100 (S − 100) − 1,30 = 0 → S = 100 + 1,987 = 101,987.
    m = metrics([call(-1, 100, 2.0)], FEES)
    assert m.loss_unlimited and m.worst_pnl is None
    assert m.best_pnl == pytest.approx(199.35, abs=PNL_TOL)
    assert_breakevens(m, [101.987])
    # Salto de −0,65 justo por encima del strike.
    assert pnl_expiry([call(-1, 100, 2.0)], MARKET, FEES, 100.0) == pytest.approx(199.35)
    assert pnl_expiry([call(-1, 100, 2.0)], MARKET, FEES, 100.0 + 1e-9) == pytest.approx(
        198.70, abs=1e-5
    )


BULL = [call(+1, 100, 3.0), call(-1, 110, 1.0)]


def test_bull_call_spread_with_fees():
    # S <= 100: −200 − 1,30 = −201,30.
    # 100 < S < 110: el largo es ITM → +0,65 de cierre:
    #   100 (S − 100) − 201,95 = 0 → S = 102,0195.
    # S = 110: el corto NO es ITM estricto → 1000 − 201,95 = 798,05.
    # S > 110: el corto también paga cierre → meseta 797,40.
    # Peor caso: justo a la derecha de 100 el largo ya paga cierre (0,65)
    # pero aún no vale casi nada → límite −201,95 (por debajo de −201,30).
    # Es un ínfimo: se roza, no se alcanza; las métricas lo reportan.
    m = metrics(BULL, FEES)
    assert not m.profit_unlimited and not m.loss_unlimited
    assert m.worst_pnl == pytest.approx(-201.95, abs=PNL_TOL)
    assert pnl_expiry(BULL, MARKET, FEES, 100.0) == pytest.approx(-201.30, abs=PNL_TOL)
    assert pnl_expiry(BULL, MARKET, FEES, 100.0 + 1e-6) == pytest.approx(-201.95, abs=1e-3)
    assert m.best_pnl == pytest.approx(798.05, abs=PNL_TOL)
    assert_breakevens(m, [102.0195])
    # El máximo se alcanza exactamente en S = 110; a la derecha, meseta 797,40.
    assert pnl_expiry(BULL, MARKET, FEES, 110.0) == pytest.approx(798.05, abs=PNL_TOL)
    assert pnl_expiry(BULL, MARKET, FEES, 120.0) == pytest.approx(797.40, abs=PNL_TOL)


def test_iron_condor_with_fees():
    # Crédito 200 − apertura 4 × 0,65 = 197,40 (meseta 95–105, sin cierres).
    # S < 90: −500 + 200 − 2,60 − 1,30 = −303,90.
    # 90 < S < 95: 200 − 100 (95 − S) − 2,60 − 0,65 = 0 → S = 93,0325 (simétrico 106,9675).
    m = metrics(CONDOR, FEES)
    assert m.best_pnl == pytest.approx(197.40, abs=PNL_TOL)
    assert m.worst_pnl == pytest.approx(-303.90, abs=PNL_TOL)
    assert_breakevens(m, [93.0325, 106.9675])


def test_fees_move_breakeven_and_reduce_profit():
    without = metrics([call(+1, 100, 3.0)])
    with_fees = metrics([call(+1, 100, 3.0)], FEES)
    assert with_fees.breakevens[0] > without.breakevens[0]
    assert with_fees.worst_pnl < without.worst_pnl
    # Sin cierre incluido solo cuenta la apertura: 103 + 0,65 / 100.
    open_only = CommissionSettings(include_close=False)
    assert_breakevens(metrics([call(+1, 100, 3.0)], open_only), [103.0065])


# --- Escenarios límite --------------------------------------------------

def test_two_legs_same_strike():
    m = metrics([call(+1, 100, 3.0), call(+1, 100, 3.0)])
    assert m.worst_pnl == pytest.approx(-600.0, abs=PNL_TOL)
    assert_breakevens(m, [103.0])


def test_stock_only_long_and_short():
    long_stock = metrics([stock(+1, 100.0)])
    assert long_stock.profit_unlimited and long_stock.best_pnl is None
    assert long_stock.worst_pnl == pytest.approx(-10000.0, abs=PNL_TOL)
    assert_breakevens(long_stock, [100.0])

    short_stock = metrics([stock(-1, 100.0)])
    assert short_stock.loss_unlimited and short_stock.worst_pnl is None
    assert short_stock.best_pnl == pytest.approx(10000.0, abs=PNL_TOL)
    assert_breakevens(short_stock, [100.0])


def test_flat_pnl_has_no_breakeven():
    # Call largo @ 3 y corto @ 4 al mismo strike: siempre +100.
    m = metrics([call(+1, 100, 3.0), call(-1, 100, 4.0)])
    assert m.best_pnl == pytest.approx(100.0, abs=PNL_TOL)
    assert m.worst_pnl == pytest.approx(100.0, abs=PNL_TOL)
    assert not m.profit_unlimited and not m.loss_unlimited
    assert m.breakevens == []


def test_flat_zero_pnl_has_no_breakeven():
    # Todo el P&L es 0: no hay un punto concreto donde "se cruce" el cero.
    m = metrics([call(+1, 100, 3.0), call(-1, 100, 3.0)])
    assert m.best_pnl == pytest.approx(0.0, abs=PNL_TOL)
    assert m.worst_pnl == pytest.approx(0.0, abs=PNL_TOL)
    assert m.breakevens == []


def test_empty_strategy():
    m = metrics([])
    assert m.best_pnl == 0.0 and m.worst_pnl == 0.0
    assert m.breakevens == []


def test_zero_exactly_at_strike_reported_once():
    # Largo sintético (call largo + put corto, primas 0): P = 100 (S − 100).
    m = metrics([call(+1, 100, 0.0), put(-1, 100, 0.0)])
    assert m.profit_unlimited and not m.loss_unlimited
    assert_breakevens(m, [100.0])


def test_touch_zero_at_strike():
    # Straddle con primas 0: P = 100 |S − 100| toca el cero solo en S = 100.
    m = metrics([call(+1, 100, 0.0), put(+1, 100, 0.0)])
    assert m.worst_pnl == pytest.approx(0.0, abs=PNL_TOL)
    assert_breakevens(m, [100.0])


def test_zero_plateau_starts_at_strike():
    # Acción @ 100 + call corto 100 @ 0: P = S − 100 hasta 100 y luego 0.
    m = metrics([stock(+1, 100.0), call(-1, 100, 0.0)])
    assert m.best_pnl == pytest.approx(0.0, abs=PNL_TOL)
    assert_breakevens(m, [100.0])


def test_very_close_strikes():
    # Bull spread de anchura 0,0001: coste 0,005, ganancia máx. 0,005.
    m = metrics([call(+1, 100, 0.00005), call(-1, 100.0001, 0.0)])
    assert m.worst_pnl == pytest.approx(-0.005, abs=PNL_TOL)
    assert m.best_pnl == pytest.approx(0.005, abs=PNL_TOL)
    assert len(m.breakevens) == 1
    assert m.breakevens[0] == pytest.approx(100.00005, abs=1e-6)


def test_index_surcharge_in_metrics():
    # Índice: 0,65 + 0,60 = 1,25 por contrato. Call largo 100 @ 3:
    # peor caso justo encima de 100 (apertura + cierre): −300 − 2,50 = −302,50;
    # breakeven 103 + 2,50 / 100 = 103,025.
    index = Market(underlying="Índice", spot=100, vol=0.20, days=30, rate=0.05)
    m = compute_metrics([call(+1, 100, 3.0)], index, FEES)
    assert m.worst_pnl == pytest.approx(-302.50, abs=PNL_TOL)
    assert_breakevens(m, [103.025])


# --- Coherencia con la curva (misma fuente de verdad) -------------------

@pytest.mark.parametrize(
    "legs",
    [
        BULL,
        CONDOR,
        [call(-1, 100, 2.0)],
        [stock(+1, 100.0), call(-1, 105, 2.0)],
        [call(+1, 100, 2.0), call(-1, 105, 0.5, qty=2), call(+1, 115, 0.0, qty=2)],
    ],
)
def test_metrics_bound_the_sampled_curve(legs):
    m = metrics(legs, FEES)
    grid = np.linspace(0.0, 200.0, 20001)
    curve = pnl_expiry(legs, MARKET, FEES, grid)
    if m.best_pnl is not None:
        assert curve.max() <= m.best_pnl + PNL_TOL
    if m.worst_pnl is not None:
        assert curve.min() >= m.worst_pnl - PNL_TOL
    # Cada breakeven cambia el signo (o anula) el P&L a su alrededor.
    for be in m.breakevens:
        left = pnl_expiry(legs, MARKET, FEES, be - 1e-3)
        right = pnl_expiry(legs, MARKET, FEES, be + 1e-3)
        assert left * right <= 0.0
