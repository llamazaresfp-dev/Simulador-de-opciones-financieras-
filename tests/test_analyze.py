"""Tests de analyze() (bloque 4: AC1, AC9, AC18 parcial, decisión 13).

analyze() es la única función que llamará la interfaz: devuelve de una
vez la rejilla de precios, las dos curvas, las métricas, las griegas y
el total de comisiones.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from opciones import (
    MIN_VOL,
    Analysis,
    CommissionSettings,
    Leg,
    Market,
    Metrics,
    analyze,
    compute_metrics,
)
from opciones.payoff import leg_pnl_expiry

REPO_ROOT = Path(__file__).resolve().parent.parent
FEES = CommissionSettings()  # 0,65 USD por contrato, cierre incluido
NO_FEES = CommissionSettings(per_contract=0.0, index_surcharge=0.0, include_close=False)


def market(**changes):
    # Etapa B1: fijado a Black-Scholes (números de referencia de la Etapa A).
    data = dict(underlying="Acción", spot=100.0, vol=0.20, days=30, rate=0.05, q=0.0,
                pricing_model="black_scholes")
    data.update(changes)
    return Market(**data)


BULL_SPREAD = [
    Leg("call", 1, 1, 100.0, 4.0),
    Leg("call", -1, 1, 110.0, 1.5),
]

IRON_CONDOR = [
    Leg("put", 1, 1, 90.0, 0.5),
    Leg("put", -1, 1, 95.0, 1.5),
    Leg("call", -1, 1, 105.0, 1.5),
    Leg("call", 1, 1, 110.0, 0.5),
]


def test_returns_analysis_with_all_fields():
    result = analyze(market(), BULL_SPREAD, FEES)
    assert isinstance(result, Analysis)
    assert isinstance(result.metrics, Metrics)
    assert len(result.grid) == len(result.expiry_curve) == len(result.today_curve)
    assert set(result.greeks) == {"delta", "gamma", "theta", "vega", "rho"}


def test_zero_days_today_curve_is_intrinsic_and_greeks_none():
    m = market(days=0)
    result = analyze(m, BULL_SPREAD, NO_FEES)
    S = result.grid
    intrinsic = np.maximum(S - 100.0, 0.0) - np.maximum(S - 110.0, 0.0)
    expected = 100 * (intrinsic - (4.0 - 1.5))
    np.testing.assert_allclose(result.today_curve, expected, atol=1e-9)
    assert all(value is None for value in result.greeks.values())


def test_positive_days_have_greeks():
    result = analyze(market(), BULL_SPREAD, FEES)
    assert all(value is not None for value in result.greeks.values())
    assert result.greeks["delta"] > 0  # bull spread: gana si sube


def test_expiry_curve_is_sum_of_legs():
    m = market()
    result = analyze(m, IRON_CONDOR, FEES)
    total = sum(leg_pnl_expiry(leg, m, FEES, result.grid) for leg in IRON_CONDOR)
    np.testing.assert_allclose(result.expiry_curve, total, atol=1e-9)


def test_grid_covers_all_strikes():
    legs = [Leg("call", 1, 1, 200.0, 0.1), Leg("put", 1, 1, 40.0, 0.1)]
    result = analyze(market(), legs, FEES)
    assert result.grid.min() <= 40.0
    assert result.grid.max() >= 200.0


def test_metrics_match_compute_metrics():
    m = market()
    result = analyze(m, BULL_SPREAD, FEES)
    assert result.metrics == compute_metrics(BULL_SPREAD, m, FEES)


def test_commission_total_open_and_close():
    # 2 contratos × 0,65 al abrir + 2 × 0,65 al cerrar = 2,60 USD.
    result = analyze(market(), BULL_SPREAD, FEES)
    assert result.commission_total == pytest.approx(2.60)


def test_commission_total_without_close_and_index_surcharge():
    settings = CommissionSettings(include_close=False)
    result = analyze(market(underlying="Índice"), BULL_SPREAD, settings)
    assert result.commission_total == pytest.approx(2 * (0.65 + 0.60))


def test_stock_has_no_commission():
    result = analyze(market(), [Leg("stock", 1, 100, None, 100.0)], FEES)
    assert result.commission_total == 0.0


@pytest.mark.parametrize(
    "changes",
    [
        dict(vol=MIN_VOL),
        dict(days=1e-6),
        dict(vol=MIN_VOL, days=1e-6),
        dict(days=0),
        dict(vol=3.0, days=3650),
    ],
)
def test_curves_have_no_nan(changes):
    result = analyze(market(**changes), IRON_CONDOR, FEES)
    assert np.all(np.isfinite(result.grid))
    assert np.all(np.isfinite(result.expiry_curve))
    assert np.all(np.isfinite(result.today_curve))


def test_engine_imports_without_streamlit():
    # Intérprete nuevo: no depende de lo que pytest ya tenga cargado.
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import opciones, opciones.implied_vol, opciones.simulation, "
            "opciones.binomial, sys; "
            "assert 'streamlit' not in sys.modules",
        ],
        check=True,
        cwd=REPO_ROOT,
    )


# --- Exportaciones de la Etapa B1 (bloque 5) ----------------------------------

B1_EXPORTS = (
    "crr_greeks", "crr_price", "crr_price_grid",
    "option_greeks", "option_price", "uses_binomial",
)


def test_stage_b1_names_are_exported():
    import opciones
    from opciones import binomial as binomial_module, pricing

    for name in B1_EXPORTS:
        assert name in opciones.__all__
        assert callable(getattr(opciones, name))
    assert opciones.crr_price is binomial_module.crr_price
    assert opciones.option_price is pricing.option_price


def test_new_names_sorted_and_no_binomial_name():
    import opciones

    # Nada llamado `binomial` en la API: sombrearía el submódulo
    # (el mismo problema que ya tiene `implied_vol`).
    assert "binomial" not in opciones.__all__
    assert opciones.binomial.__name__ == "opciones.binomial"
    # Los nombres nuevos van en orden alfabético dentro de __all__.
    positions = [opciones.__all__.index(name) for name in B1_EXPORTS]
    assert positions == sorted(positions)
