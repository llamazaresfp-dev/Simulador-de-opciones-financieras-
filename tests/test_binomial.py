"""Tests del árbol binomial CRR (Etapa B1, bloque 1).

Comprobamos el árbol contra valores de libro (Hull), contra Black-Scholes
(límite europeo) y contra propiedades que toda opción americana cumple
(nunca vale menos que su intrínseco, ni menos que la europea, etc.).
Las cifras de referencia se han recalculado con las entradas exactas de
cada test.
"""

import ast
import dataclasses
import math
import pathlib
import subprocess
import sys

import numpy as np
import pytest

from opciones.binomial import (
    CRR_GRID_STEPS,
    CRR_PRICE_STEPS,
    _crr_greeks,
    _crr_values,
    _effective_steps,
    crr_greeks,
    crr_price,
    crr_price_grid,
)
from opciones.models import (
    MIN_VOL,
    PRICING_BINOMIAL,
    PRICING_BLACK_SCHOLES,
    PRICING_MODELS,
    Market,
)
from opciones.pricing import bs_greeks, bs_price

BINOMIAL_SOURCE = pathlib.Path(__file__).resolve().parent.parent / "opciones" / "binomial.py"


def intrinsic(kind, S, K):
    return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)


# --- Campo Market.pricing_model ------------------------------------------

def test_market_pricing_model_is_last_field_with_binomial_default():
    names = [field.name for field in dataclasses.fields(Market)]
    assert names[-1] == "pricing_model"
    assert names[-2] == "q"
    assert Market("Acción", 100, 0.25, 45, 0.04).pricing_model == "binomial"
    assert Market("Acción", 100, 0.25, 45, 0.04, 0.01).q == 0.01
    assert PRICING_BINOMIAL == "binomial"
    assert PRICING_BLACK_SCHOLES == "black_scholes"
    assert PRICING_MODELS == ("binomial", "black_scholes")


def test_market_accepts_black_scholes_by_keyword_and_position():
    by_name = Market("ETF", 100, 0.2, 30, 0.04, q=0.0, pricing_model="black_scholes")
    by_position = Market("ETF", 100, 0.2, 30, 0.04, 0.0, "black_scholes")
    assert by_name == by_position
    assert by_name.T == pytest.approx(30 / 365)


# --- AC-B1: valores de libro (Hull), árbol sin promediar -----------------

def test_hull_american_put_two_steps():
    # Hull: S=50, K=52, r=5 %, sigma=30 %, T=2 años, N=2 → 7,4284 (medido 7,42840).
    value = _crr_values("put", [50], 52, 0.05, 0.0, 0.30, 2, 2, True)[0]
    assert value == pytest.approx(7.4284, abs=5e-4)


def test_hull_american_put_five_steps():
    # Hull: S=50, K=50, r=10 %, sigma=40 %, T=5 meses, N=5 → 4,4885 (medido 4,48846).
    value = _crr_values("put", [50], 50, 0.10, 0.0, 0.40, 5 / 12, 5, True)[0]
    assert value == pytest.approx(4.4885, abs=5e-4)


# --- AC-B2: límite europeo y propiedades americanas -----------------------

def test_european_tree_matches_black_scholes_reference_put():
    # Put S=K=100, r=4 %, q=1 %, sigma=25 %, T=0,5: árbol 6,23843 vs BS 6,24017
    # (error medido 1,745e-3).
    tree = _crr_values("put", [100], 100, 0.04, 0.01, 0.25, 0.5, 1000, False)[0]
    bs = bs_price("put", 100, 100, 0.04, 0.01, 0.25, 0.5)
    assert tree == pytest.approx(bs, abs=2e-3)


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("K", [80, 90, 100, 110, 120])
@pytest.mark.parametrize("sigma", [0.15, 0.25, 0.35])
@pytest.mark.parametrize("T", [45 / 365, 0.5])
@pytest.mark.parametrize("r, q", [(0.04, 0.01), (0.0, 0.0), (0.05, 0.03)])
def test_european_tree_matches_black_scholes_sweep(kind, K, sigma, T, r, q):
    # Árbol europeo de 1000 pasos sin promediar; el peor caso medido del
    # barrido está por debajo de 3e-3 (el error crece con sigma·raíz(T)).
    tree = _crr_values(kind, [100], K, r, q, sigma, T, 1000, False)[0]
    assert tree == pytest.approx(bs_price(kind, 100, K, r, q, sigma, T), abs=3e-3)


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("K", [80, 90, 100, 110, 120])
@pytest.mark.parametrize("sigma", [0.10, 0.25, 0.50, 0.80])
@pytest.mark.parametrize("T", [0.1, 0.5, 1.0, 2.0])
@pytest.mark.parametrize("r, q", [(0.04, 0.01), (0.0, 0.0), (0.05, 0.03)])
def test_averaged_european_price_matches_black_scholes_wide_range(kind, K, sigma, T, r, q):
    # El precio que usa la app (media de 500 y 501 pasos) en versión europea
    # frente a Black-Scholes, en un rango amplio (σ hasta 80 %, T hasta 2 años).
    # Tolerancia escalada: el error del árbol crece con σ·raíz(T) (el paso
    # del árbol en log-precio es σ·raíz(dt) y la "rejilla" alrededor del
    # strike es más gruesa). Por eso usamos 3e-3 hasta σ·raíz(T) = 0,25
    # (el rango del test de 1000 pasos) y lo ampliamos de forma proporcional
    # por encima. Peor caso medido (20-11-26): put K=120, σ=80 %, T=2 años,
    # r=q=0 → error 7,6e-3 frente a una tolerancia de 1,36e-2; la mayor
    # proporción error/tolerancia es ≈ 0,70 (put K=110, σ=25 %, T=1, r=q=0).
    price = crr_price(kind, 100, K, r, q, sigma, T, american=False)
    tolerance = 3e-3 * max(1.0, sigma * math.sqrt(T) / 0.25)
    assert price == pytest.approx(bs_price(kind, 100, K, r, q, sigma, T), abs=tolerance)


@pytest.mark.parametrize("K", [90, 100, 110])
@pytest.mark.parametrize("T", [45 / 365, 1.0])
def test_american_call_without_dividend_equals_european(K, T):
    # Con q = 0 nunca conviene ejercer una call antes: americana = europea.
    american = _crr_values("call", [100], K, 0.04, 0.0, 0.25, T, 500, True)[0]
    european = _crr_values("call", [100], K, 0.04, 0.0, 0.25, T, 500, False)[0]
    assert american == pytest.approx(european, abs=1e-9)


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("S", [80, 100, 120])
@pytest.mark.parametrize("K", [90, 110])
@pytest.mark.parametrize("T", [10 / 365, 1.0])
@pytest.mark.parametrize("sigma", [0.1, 0.4])
@pytest.mark.parametrize("r, q", [(0.04, 0.01), (0.0, 0.05), (0.08, 0.0)])
def test_early_exercise_premium_is_not_negative(kind, S, K, T, sigma, r, q):
    american = crr_price(kind, S, K, r, q, sigma, T, steps=100)
    european = crr_price(kind, S, K, r, q, sigma, T, steps=100, american=False)
    assert american - european >= -1e-12
    assert american >= intrinsic(kind, S, K) - 1e-12


def test_deep_in_the_money_put_equals_intrinsic():
    # Put S=100, K=140, r=4 %, q=1 %, sigma=20 %, T=1 año: ejercer ya es óptimo.
    assert crr_price("put", 100, 140, 0.04, 0.01, 0.20, 1.0) == pytest.approx(40.0, abs=1e-9)


@pytest.mark.parametrize("K", [80, 100, 120])
@pytest.mark.parametrize("r, q", [(0.04, 0.01), (0.05, 0.0), (0.0, 0.03)])
@pytest.mark.parametrize("T", [45 / 365, 1.0])
def test_american_put_call_parity_bounds(K, r, q, T):
    # Paridad americana: S·e^(−qT) − K <= C − P <= S − K·e^(−rT).
    S, sigma = 100.0, 0.3
    diff = crr_price("call", S, K, r, q, sigma, T) - crr_price("put", S, K, r, q, sigma, T)
    assert diff >= S * math.exp(-q * T) - K - 1e-6
    assert diff <= S - K * math.exp(-r * T) + 1e-6


# --- AC-B3: promedio N / N+1 -----------------------------------------------

def test_price_and_grid_step_constants():
    assert CRR_PRICE_STEPS == 500
    assert CRR_GRID_STEPS == 200


def test_crr_price_is_mean_of_500_and_501_steps():
    args = ("put", [100], 105, 0.04, 0.01, 0.3, 0.5)
    expected = 0.5 * (_crr_values(*args, 500, True)[0] + _crr_values(*args, 501, True)[0])
    assert crr_price("put", 100, 105, 0.04, 0.01, 0.3, 0.5) == pytest.approx(expected, abs=1e-12)


def test_crr_price_grid_is_mean_of_200_and_201_steps():
    spots = np.array([90.0, 100.0, 110.0])
    args = ("call", spots, 100, 0.04, 0.01, 0.25, 0.5)
    expected = 0.5 * (_crr_values(*args, 200, True) + _crr_values(*args, 201, True))
    np.testing.assert_allclose(crr_price_grid(*args), expected, atol=1e-12)


def test_averaging_reduces_error_against_fine_tree():
    # Referencia: árbol americano promediado de 2000/2001 pasos.
    # Medido: el promedio 500/501 gana a N=500 solo en 22 de 24 casos;
    # peor error del promedio 3,2e-3 (put K=110, sigma=40 %, T=1 año).
    wins, cases, worst = 0, 0, 0.0
    for kind in ("call", "put"):
        for K in (90, 100, 110):
            for sigma in (0.2, 0.4):
                for T in (45 / 365, 1.0):
                    args = (kind, [100], K, 0.04, 0.01, sigma, T)
                    ref = 0.5 * (_crr_values(*args, 2000, True)[0] + _crr_values(*args, 2001, True)[0])
                    averaged = crr_price(kind, 100, K, 0.04, 0.01, sigma, T)
                    single = _crr_values(*args, 500, True)[0]
                    wins += abs(averaged - ref) < abs(single - ref)
                    worst = max(worst, abs(averaged - ref))
                    cases += 1
    assert wins >= 0.8 * cases
    assert worst <= 5e-3


# --- AC-B7 (parte pura): malla de la curva "hoy" ------------------------------

@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("q", [0.0, 0.03])
def test_grid_is_at_least_intrinsic_and_finite(kind, q):
    spots = np.linspace(0.0, 250.0, 401)
    values = crr_price_grid(kind, spots, 100, 0.04, q, 0.25, 45 / 365)
    assert values.shape == spots.shape
    assert np.all(np.isfinite(values))
    intrinsic_values = np.maximum(spots - 100, 0) if kind == "call" else np.maximum(100 - spots, 0)
    assert np.all(values >= intrinsic_values - 1e-12)


# --- Guardas: nunca NaN ni infinitos ---------------------------------------

@pytest.mark.parametrize("T", [0.0, -0.1])
def test_expired_option_is_intrinsic(T):
    assert crr_price("call", 110, 100, 0.04, 0.0, 0.2, T) == pytest.approx(10.0)
    assert crr_price("put", 110, 100, 0.04, 0.0, 0.2, T) == pytest.approx(0.0)
    np.testing.assert_allclose(crr_price_grid("put", [90, 110], 100, 0.04, 0.0, 0.2, T), [10.0, 0.0])


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("S", [80.0, 100.0, 120.0])
def test_zero_volatility_is_deterministic_limit(kind, S):
    K, r, q, T = 100.0, 0.05, 0.02, 0.5
    forward = S * math.exp(-q * T) - K * math.exp(-r * T)
    forward = max(forward, 0.0) if kind == "call" else max(-forward, 0.0)
    expected = max(forward, intrinsic(kind, S, K))
    assert crr_price(kind, S, K, r, q, 0.0, T) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("kind, r, q", [("put", 0.04, 0.5), ("call", 0.5, 0.0), ("put", -0.3, 0.2)])
def test_tiny_volatility_with_large_drift_has_no_nan(kind, r, q):
    # sigma = 1e-6 con |r − q| grande: p saldría de [0, 1]. Debe dar el
    # límite sin volatilidad (finito y razonable), no NaN.
    S, K, T = 100.0, 100.0, 0.5
    value = crr_price(kind, S, K, r, q, 1e-6, T)
    assert math.isfinite(value)
    assert value == pytest.approx(crr_price(kind, S, K, r, q, 0.0, T), abs=1e-6)


@pytest.mark.parametrize("kind", ["call", "put"])
def test_extreme_volatility_and_long_maturity_stay_finite_and_bounded(kind):
    value = crr_price(kind, 100, 100, 0.04, 0.0, 10.0, 10.0)
    grid = crr_price_grid(kind, [1.0, 100.0, 1e6], 100, 0.04, 0.0, 10.0, 10.0)
    upper = 100.0  # call <= S (=100), put <= K (=100)
    assert math.isfinite(value) and 0.0 <= value <= upper + 1e-9
    assert np.all(np.isfinite(grid))


def test_short_maturity_caps_steps():
    assert _effective_steps(500, 1 / 365) == 50
    assert _effective_steps(500, 1.0) == 500
    assert _effective_steps(500, 1e-9) == 2
    value = crr_price("put", 100, 100, 0.04, 0.0, 0.2, 1 / 365)
    assert math.isfinite(value) and value > 0


def test_invalid_kind_raises():
    with pytest.raises(ValueError):
        crr_price("stock", 100, 100, 0.04, 0.0, 0.2, 0.5)


# --- AC-B8: griegas del árbol (bloque 3) -----------------------------------

GREEK_NAMES = ("delta", "gamma", "theta", "vega", "rho")

# Put de referencia del SPEC: S = K = 100, r 4 %, q 1 %, σ 25 %, T = 182,5 días.
REF_PUT = ("put", 100.0, 100.0, 0.04, 0.01, 0.25, 182.5 / 365)


def test_crr_greeks_returns_the_five_greeks():
    greeks = crr_greeks(*REF_PUT)
    assert set(greeks) == set(GREEK_NAMES)
    assert all(isinstance(value, float) and math.isfinite(value) for value in greeks.values())


def test_crr_greeks_reference_put():
    # Cifras recalculadas con estas entradas exactas (N = 500/501 promediados):
    # delta −0,44217, gamma 0,023314, theta −0,015628/día,
    # vega 0,27639 y rho −0,19487 por punto (desplazamientos centrales ±0,01).
    greeks = crr_greeks(*REF_PUT)
    assert greeks["delta"] == pytest.approx(-0.44217, abs=5e-4)
    assert greeks["gamma"] == pytest.approx(0.023314, abs=2e-4)
    assert greeks["theta"] == pytest.approx(-0.015628, abs=5e-4)
    assert greeks["vega"] == pytest.approx(0.27639, abs=5e-3)
    assert greeks["rho"] == pytest.approx(-0.19487, abs=1e-3)


def test_crr_rho_is_close_to_spec_value():
    # El SPEC cita −0,1897 (probablemente con un desplazamiento unilateral);
    # el central da −0,1949. La diferencia cabe en 1e-2.
    assert crr_greeks(*REF_PUT)["rho"] == pytest.approx(-0.1897, abs=1e-2)


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("K", [80.0, 100.0, 120.0])
@pytest.mark.parametrize("sigma, T", [(0.15, 30 / 365), (0.30, 0.5), (0.50, 2.0)])
def test_crr_greeks_signs_and_ranges(kind, K, sigma, T):
    greeks = crr_greeks(kind, 100.0, K, 0.04, 0.01, sigma, T)
    if kind == "call":
        assert -1e-9 <= greeks["delta"] <= 1 + 1e-9
        assert greeks["rho"] >= -1e-9
    else:
        assert -1 - 1e-9 <= greeks["delta"] <= 1e-9
        assert greeks["rho"] <= 1e-9
    assert greeks["gamma"] >= -1e-9
    assert greeks["vega"] >= -1e-9
    assert all(math.isfinite(value) for value in greeks.values())


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("K, sigma, T, r, q", [
    (100.0, 0.25, 0.5, 0.04, 0.01),
    (90.0, 0.20, 1.0, 0.05, 0.0),
    (110.0, 0.35, 0.25, 0.03, 0.02),
])
def test_european_tree_greeks_match_black_scholes(kind, K, sigma, T, r, q):
    # Con american=False el árbol debe dar casi las griegas de Black-Scholes:
    # así comprobamos las fórmulas de nodos, unidades y desplazamientos.
    tree = _crr_greeks(kind, 100.0, K, r, q, sigma, T, CRR_PRICE_STEPS, False)
    exact = bs_greeks(kind, 100.0, K, r, q, sigma, T)
    for name in GREEK_NAMES:
        assert tree[name] == pytest.approx(exact[name], rel=1e-2, abs=1e-5), name


def test_vega_is_one_sided_when_sigma_is_tiny():
    # σ − 0,01 < MIN_VOL: no se puede bajar la volatilidad 1 punto,
    # así que vega = P(σ + 0,01) − P(σ).
    sigma = 0.005
    assert sigma - 0.01 < MIN_VOL
    args = ("call", 100.0, 100.0, 0.04, 0.01)
    greeks = crr_greeks(*args, sigma, 0.5)
    expected = crr_price(*args, sigma + 0.01, 0.5) - crr_price(*args, sigma, 0.5)
    assert greeks["vega"] == pytest.approx(expected, abs=1e-12)
    assert all(math.isfinite(value) for value in greeks.values())


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("r, q", [(0.30, 0.0), (-0.05, 0.20)])
def test_crr_greeks_with_minimum_volatility_are_finite(kind, r, q):
    greeks = crr_greeks(kind, 100.0, 100.0, r, q, MIN_VOL, 0.5)
    assert all(math.isfinite(value) for value in greeks.values())


@pytest.mark.parametrize("T, sigma", [(0.0, 0.25), (-0.1, 0.25), (0.5, 0.0), (0.5, -0.2)])
def test_crr_greeks_undefined_raise_value_error(T, sigma):
    with pytest.raises(ValueError):
        crr_greeks("put", 100.0, 100.0, 0.04, 0.01, sigma, T)


def test_crr_greeks_invalid_kind_raises():
    with pytest.raises(ValueError):
        crr_greeks("stock", 100.0, 100.0, 0.04, 0.01, 0.25, 0.5)


# --- AC-B15 (parte): módulo puro ----------------------------------------------

def test_binomial_module_does_not_import_pricing_or_streamlit():
    tree = ast.parse(BINOMIAL_SOURCE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported <= {"math", "numpy", "opciones.models"}


def test_binomial_imports_without_streamlit():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import opciones.binomial; "
            "assert 'streamlit' not in sys.modules",
        ],
        check=True,
        cwd=BINOMIAL_SOURCE.parent.parent,
    )
