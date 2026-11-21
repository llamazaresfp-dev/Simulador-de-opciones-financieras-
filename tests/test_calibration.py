"""Tests de opciones/calibration.py (Etapa C2, bloque 1).

Cubre AC-C2-9 (deciles fijos, Wilson con valores conocidos, tramos vacíos
y con pocos casos), y las partes de AC-C2-10, AC-C2-11 y AC-C2-12 que son
matemática pura: Brier, Brier climatológico, habilidad, desviación
máxima, N efectivo y diagnóstico de colas.

Las cifras de referencia se recalcularon a mano con las entradas exactas
de cada test (se anotan en los comentarios).
"""

import math

import numpy as np
import pytest
from scipy.stats import norm

from opciones.calibration import (
    EXPECTED_GT2,
    EXPECTED_LT_M2,
    MIN_CASES,
    QUANTILE_LEVELS,
    BinRow,
    TailResult,
    brier_score,
    brier_skill,
    calibration_bins,
    climatological_brier,
    effective_n,
    max_deviation,
    tail_diagnostics,
    wilson_interval,
)


def _no_nan(value) -> bool:
    """True si 'value' no es un float NaN ni infinito (None vale)."""
    if value is None:
        return True
    return math.isfinite(value)


# --- Wilson ---------------------------------------------------------------


def test_wilson_k5_n10_valor_conocido():
    # A mano: p = 0,5; z² = 3,8416; denominador 1,38416;
    # semiancho = 1,96·√(0,025 + 0,009604)/1,38416 = 0,26340.
    lo, hi = wilson_interval(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4)
    assert hi == pytest.approx(0.7634, abs=1e-4)


def test_wilson_k0_empieza_en_cero():
    # k = 0, n = 10: centro = semiancho = 0,19208/1,38416 → [0, 0,2775].
    lo, hi = wilson_interval(0, 10)
    assert lo == pytest.approx(0.0, abs=1e-12)
    assert hi == pytest.approx(0.2775, abs=1e-4)


def test_wilson_k_igual_n_termina_en_uno():
    lo, hi = wilson_interval(10, 10)
    assert lo == pytest.approx(0.7225, abs=1e-4)
    assert hi == pytest.approx(1.0, abs=1e-12)


def test_wilson_n0_devuelve_none():
    assert wilson_interval(0, 0) is None


def test_wilson_deff_menor_que_uno_ensancha():
    lo1, hi1 = wilson_interval(30, 60)
    lo2, hi2 = wilson_interval(30, 60, deff=0.5)
    assert (hi2 - lo2) > (hi1 - lo1)
    # deff = 0,5 con k=30, n=60 equivale a Wilson con k=15, n=30.
    lo3, hi3 = wilson_interval(15, 30)
    assert lo2 == pytest.approx(lo3, abs=1e-12)
    assert hi2 == pytest.approx(hi3, abs=1e-12)


def test_wilson_deff_uno_es_el_ingenuo():
    assert wilson_interval(7, 20, deff=1.0) == wilson_interval(7, 20)


def test_wilson_deff_cero_devuelve_none():
    assert wilson_interval(3, 10, deff=0.0) is None


# --- Brier ------------------------------------------------------------------


def test_brier_casos_pequenos():
    assert brier_score([0.5, 0.5], [1, 0]) == pytest.approx(0.25)
    assert brier_score([1.0, 0.0], [1, 0]) == pytest.approx(0.0)
    assert brier_score([0.0, 1.0], [1, 0]) == pytest.approx(1.0)


def test_brier_vacio_devuelve_none():
    assert brier_score([], []) is None
    assert climatological_brier([]) is None
    assert brier_skill([], []) is None


def test_brier_climatologico():
    # Tasa = 0,75 → 0,75·0,25 = 0,1875.
    assert climatological_brier([1, 1, 1, 0]) == pytest.approx(0.1875)


def test_habilidad_cero_si_pop_es_la_tasa():
    win = [1, 1, 1, 0]
    assert brier_skill([0.75] * 4, win) == pytest.approx(0.0, abs=1e-12)


def test_habilidad_perfecta_es_uno():
    assert brier_skill([1.0, 0.0, 1.0], [1, 0, 1]) == pytest.approx(1.0)


def test_habilidad_none_si_climatologico_cero():
    # Todos ganan: Brier climatológico 0 → habilidad no definida.
    assert brier_skill([0.9, 0.8], [1, 1]) is None


def test_brier_acepta_arrays_y_booleanos():
    pop = np.array([0.2, 0.8])
    win = np.array([False, True])
    assert brier_score(pop, win) == pytest.approx(0.04)


# --- Deciles ----------------------------------------------------------------


def test_deciles_siempre_diez_filas():
    rows = calibration_bins([], [])
    assert len(rows) == 10
    assert all(isinstance(row, BinRow) for row in rows)
    assert all(row.empty for row in rows)
    assert all(row.observed is None and row.mean_pop is None for row in rows)
    assert all(row.ci_low is None and row.ci_high is None for row in rows)
    assert rows[0].lo == pytest.approx(0.0) and rows[9].hi == pytest.approx(1.0)


def test_deciles_bordes():
    pops = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.0999]
    rows = calibration_bins(pops, [0] * len(pops))
    counts = [row.n for row in rows]
    # 0,0 y 0,0999 en el primero; 1,0 va al último junto con 0,9.
    assert counts == [2, 1, 1, 1, 1, 1, 1, 1, 1, 2]


def test_deciles_media_y_observado():
    pops = [0.31, 0.33, 0.35, 0.37]
    wins = [1, 0, 0, 1]
    row = calibration_bins(pops, wins)[3]
    assert row.n == 4
    assert row.mean_pop == pytest.approx(0.34)
    assert row.observed == pytest.approx(0.5)
    lo, hi = wilson_interval(2, 4)
    assert row.ci_low == pytest.approx(lo) and row.ci_high == pytest.approx(hi)


def test_deciles_pocos_casos():
    rows = calibration_bins([0.55] * 9 + [0.75] * 10, [1] * 19)
    assert rows[5].n == 9 and rows[5].few
    assert rows[7].n == 10 and not rows[7].few
    assert not rows[0].few and rows[0].empty


def test_deciles_deff_reduce_n_eff_y_ensancha():
    pops = [0.65] * 40
    wins = [1] * 20 + [0] * 20
    naive = calibration_bins(pops, wins)[6]
    shrunk = calibration_bins(pops, wins, deff=0.25)[6]
    assert naive.n_eff == pytest.approx(40)
    assert shrunk.n_eff == pytest.approx(10)
    assert (shrunk.ci_high - shrunk.ci_low) > (naive.ci_high - naive.ci_low)


def test_max_deviation_ignora_pocos_y_vacios():
    pops = [0.15] * 10 + [0.85] * 5
    wins = [1] * 10 + [0] * 5
    rows = calibration_bins(pops, wins)
    # Tramo 1: media 0,15, observado 1,0 → 0,85. El tramo 8 (n=5) se ignora.
    assert max_deviation(rows) == pytest.approx(0.85)


def test_max_deviation_none_si_no_queda_ninguna():
    rows = calibration_bins([0.5] * 3, [1] * 3)
    assert max_deviation(rows) is None


def test_deciles_min_cases_configurable():
    rows = calibration_bins([0.5] * 3, [1] * 3, min_cases=3)
    assert not rows[5].few
    assert MIN_CASES == 10


# --- N efectivo -------------------------------------------------------------


def test_effective_n_limitado_por_solapamiento():
    # 10 años, H = 30 → 3650/30 = 121,67.
    assert effective_n(500, 10.0, 30) == pytest.approx(3650 / 30)


def test_effective_n_limitado_por_n():
    assert effective_n(50, 10.0, 30) == pytest.approx(50)


def test_effective_n_cero():
    assert effective_n(0, 10.0, 30) == 0
    assert effective_n(10, 0.0, 30) == 0


# --- Colas ------------------------------------------------------------------


def test_colas_muestra_normal_sembrada():
    z = np.random.default_rng(7).standard_normal(20_000)
    tail = tail_diagnostics(z)
    assert isinstance(tail, TailResult)
    assert tail.n == 20_000
    # Errores estándar con n = 20 000: media 0,007, std ≈ 0,005,
    # curtosis ≈ 0,035, excedencia |z|>2 ≈ 0,0015.
    assert tail.mean == pytest.approx(0.0, abs=0.03)
    assert tail.std == pytest.approx(1.0, abs=0.03)
    assert abs(tail.excess_kurtosis) < 0.15
    assert abs(tail.skew) < 0.1
    assert tail.frac_gt2 == pytest.approx(EXPECTED_GT2, abs=0.008)
    assert tail.frac_lt_m2 == pytest.approx(EXPECTED_LT_M2, abs=0.006)
    assert set(tail.quantiles) == set(QUANTILE_LEVELS)
    for level in QUANTILE_LEVELS:
        empirical, normal = tail.quantiles[level]
        assert normal == pytest.approx(norm.ppf(level))
        assert empirical == pytest.approx(normal, abs=0.08)


def test_colas_muestra_hecha_a_mano():
    # z = [-3, -1, 0, 0, 1, 3]: media 0, m2 = 20/6, m4 = 164/6,
    # curtosis en exceso = m4/m2² − 3 = −0,54; |z|>2 → 2/6; z<−2 → 1/6.
    tail = tail_diagnostics([-3.0, -1.0, 0.0, 0.0, 1.0, 3.0])
    assert tail.n == 6
    assert tail.mean == pytest.approx(0.0)
    assert tail.excess_kurtosis == pytest.approx(-0.54, abs=1e-12)
    assert tail.skew == pytest.approx(0.0, abs=1e-12)
    assert tail.frac_gt2 == pytest.approx(2 / 6)
    assert tail.frac_lt_m2 == pytest.approx(1 / 6)
    assert tail.std == pytest.approx(math.sqrt(20 / 5))  # ddof = 1


def test_colas_vacia_sin_nan():
    tail = tail_diagnostics([])
    assert tail.n == 0
    assert tail.mean is None and tail.std is None
    assert tail.skew is None and tail.excess_kurtosis is None
    assert tail.frac_gt2 is None and tail.frac_lt_m2 is None
    assert tail.quantiles == {}


def test_colas_ignora_nan_e_infinitos():
    tail = tail_diagnostics([float("nan"), 1.0, float("inf"), -1.0])
    assert tail.n == 2
    assert tail.mean == pytest.approx(0.0)


def test_colas_constante_sin_nan():
    tail = tail_diagnostics([0.5, 0.5, 0.5])
    for value in (tail.mean, tail.std, tail.skew, tail.excess_kurtosis, tail.frac_gt2):
        assert _no_nan(value)


def test_constantes_esperadas():
    assert EXPECTED_GT2 == pytest.approx(2 * norm.cdf(-2), abs=1e-4)
    assert EXPECTED_LT_M2 == pytest.approx(norm.cdf(-2), abs=1e-4)
    assert QUANTILE_LEVELS == (0.01, 0.05, 0.5, 0.95, 0.99)


def test_salidas_sin_nan_en_deciles():
    rows = calibration_bins(np.linspace(0, 1, 101), np.arange(101) % 2)
    for row in rows:
        for value in (row.mean_pop, row.observed, row.ci_low, row.ci_high, row.n_eff):
            assert _no_nan(value)
