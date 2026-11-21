"""Tests de los ayudantes de opciones/backtest.py (Etapa C2, bloque 2).

Cubre las partes de AC-C2-5 (volatilidad realizada con datos ≤ t),
AC-C2-6 (vencimiento = último día ≤ t+H con fines de semana y festivos),
AC-C2-8 (q de 12 meses previos, índice → 0, tasa ^IRX del día) y
AC-C2-12 (μ histórico de 252 sesiones sin mirar el futuro), más el
recorte por años y el aviso de histórico corto (IP-3).

Cada valor esperado se calcula a mano en el propio test con numpy, sobre
series cortas.
"""

import math

import numpy as np
import pytest

from opciones.backtest import (
    MU_LOOKBACK,
    TRADING_DAYS,
    expiry_index,
    first_analyzed_index,
    rate_at,
    realized_vol,
    to_day_numbers,
    trailing_dividend_yield,
    trailing_mu,
)


def _business_days(start: str, count: int) -> list[str]:
    """Lista de 'count' días hábiles (lunes a viernes) desde 'start', en ISO."""
    first = np.datetime64(start, "D")
    days = np.arange(first, first + np.timedelta64(count * 2, "D"), dtype="datetime64[D]")
    days = days[np.is_busday(days)][:count]
    return [str(day) for day in days]


def _random_prices(count: int, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, 0.01, count)))


# --- Fechas -----------------------------------------------------------------


def test_to_day_numbers():
    days = to_day_numbers(["1970-01-01", "1970-01-02", "2000-01-01"])
    assert days.tolist() == [0, 1, 10957]


# --- Volatilidad realizada --------------------------------------------------


def test_realized_vol_a_mano_w5():
    adj = np.array([100.0, 101.0, 99.5, 102.0, 103.0, 101.5, 104.0])
    i = 6
    returns = np.log(adj[2:7] / adj[1:6])  # las 5 sesiones que terminan en i
    expected = np.std(returns, ddof=1) * math.sqrt(252)
    assert realized_vol(adj, i, 5) == pytest.approx(expected, rel=1e-12)


def test_realized_vol_exige_i_mayor_o_igual_w():
    adj = np.array([100.0, 101.0, 99.5, 102.0, 103.0, 101.5])
    assert realized_vol(adj, 4, 5) is None
    assert realized_vol(adj, 5, 5) is not None


def test_realized_vol_no_mira_el_futuro():
    adj = _random_prices(50)
    before = realized_vol(adj, 30, 20)
    changed = adj.copy()
    changed[31:] *= 3.0
    assert realized_vol(changed, 30, 20) == before


def test_realized_vol_precio_no_positivo_none():
    adj = np.array([100.0, 0.0, 101.0, 102.0])
    assert realized_vol(adj, 3, 3) is None


def test_trading_days_constante():
    assert TRADING_DAYS == 252 and MU_LOOKBACK == 252


# --- μ histórico ------------------------------------------------------------


def test_trailing_mu_a_mano():
    adj = _random_prices(300)
    i = 280
    vol = 0.2
    returns = np.log(adj[i - 251 : i + 1] / adj[i - 252 : i])
    expected = np.mean(returns) * 252 + vol**2 / 2
    assert len(returns) == 252
    assert trailing_mu(adj, i, vol) == pytest.approx(expected, rel=1e-12)


def test_trailing_mu_exige_252_sesiones():
    adj = _random_prices(300)
    assert trailing_mu(adj, 251, 0.2) is None
    assert trailing_mu(adj, 252, 0.2) is not None


def test_trailing_mu_no_mira_el_futuro():
    adj = _random_prices(300)
    before = trailing_mu(adj, 260, 0.25)
    changed = adj.copy()
    changed[261:] = 1.0
    assert trailing_mu(changed, 260, 0.25) == before


# --- Dividendo histórico ----------------------------------------------------


def test_dividend_yield_bordes_de_la_ventana():
    t = to_day_numbers(["2024-06-30"])[0]
    div_days = to_day_numbers(["2023-06-30", "2023-07-01", "2024-01-15", "2024-06-30", "2024-07-01"])
    amounts = np.array([10.0, 1.0, 2.0, 0.5, 7.0])
    # 2023-06-30 = t − 366 días (bisiesto 2024): fuera; 2023-07-01 = t − 365: fuera
    # (la ventana es (t − 365, t]); 2024-01-15 y 2024-06-30 dentro; 2024-07-01 futuro.
    assert trailing_dividend_yield(div_days, amounts, t, 50.0) == pytest.approx(2.5 / 50.0)


def test_dividend_yield_dia_t_menos_364_dentro():
    t = to_day_numbers(["2025-06-30"])[0]
    div_days = np.array([t - 365, t - 364])
    amounts = np.array([4.0, 1.0])
    assert trailing_dividend_yield(div_days, amounts, t, 100.0) == pytest.approx(0.01)


def test_dividend_yield_sin_dividendos():
    t = to_day_numbers(["2025-06-30"])[0]
    empty = np.array([], dtype=np.int64)
    assert trailing_dividend_yield(empty, np.array([]), t, 100.0) == 0.0


def test_dividend_yield_indice_cero():
    t = to_day_numbers(["2025-06-30"])[0]
    div_days = np.array([t - 10])
    assert trailing_dividend_yield(div_days, np.array([3.0]), t, 100.0, underlying="Índice") == 0.0


def test_dividend_yield_no_mira_el_futuro():
    t = to_day_numbers(["2025-06-30"])[0]
    div_days = np.array([t - 100, t + 1])
    before = trailing_dividend_yield(div_days, np.array([2.0, 5.0]), t, 100.0)
    after = trailing_dividend_yield(div_days, np.array([2.0, 50.0]), t, 100.0)
    assert before == after == pytest.approx(0.02)


# --- Tasa del día -----------------------------------------------------------


def test_rate_at_valor_exacto_y_fin_de_semana():
    rate_days = to_day_numbers(["2025-06-05", "2025-06-06", "2025-06-09"])  # jue, vie, lun
    values = np.array([0.041, 0.0412, 0.043])
    assert rate_at(rate_days, values, to_day_numbers(["2025-06-06"])[0]) == pytest.approx(0.0412)
    # Sábado → el último dato ≤ t es el del viernes.
    assert rate_at(rate_days, values, to_day_numbers(["2025-06-07"])[0]) == pytest.approx(0.0412)
    assert rate_at(rate_days, values, to_day_numbers(["2025-06-30"])[0]) == pytest.approx(0.043)


def test_rate_at_antes_del_primer_dato_none():
    rate_days = to_day_numbers(["2025-06-05"])
    assert rate_at(rate_days, np.array([0.04]), to_day_numbers(["2025-06-04"])[0]) is None


def test_rate_at_ya_en_fraccion():
    # La conversión de porcentaje (4,12) a fracción ocurre en datos/; aquí
    # el valor se devuelve tal cual.
    rate_days = to_day_numbers(["2025-06-05"])
    assert rate_at(rate_days, np.array([0.0412]), rate_days[0]) == pytest.approx(0.0412)


def test_rate_at_sin_datos_none():
    assert rate_at(np.array([], dtype=np.int64), np.array([]), 20000) is None


# --- Vencimiento ------------------------------------------------------------

# Calendario pequeño: lunes 2025-06-02 … viernes 2025-06-13, sin el
# miércoles 2025-06-11 (festivo inventado).
CALENDAR = to_day_numbers(
    [
        "2025-06-02", "2025-06-03", "2025-06-04", "2025-06-05", "2025-06-06",
        "2025-06-09", "2025-06-10", "2025-06-12", "2025-06-13",
    ]
)


def test_expiry_cae_en_sabado_toma_el_viernes():
    # t = lunes 02 (i=0), H = 5 → sábado 07 → viernes 06 (i=4).
    assert expiry_index(CALENDAR, 0, 5) == 4


def test_expiry_cae_en_festivo_toma_el_dia_anterior():
    # t = viernes 06 (i=4), H = 5 → miércoles 11 (festivo) → martes 10 (i=6).
    assert expiry_index(CALENDAR, 4, 5) == 6


def test_expiry_dia_habil_exacto():
    # t = lunes 02, H = 3 → jueves 05 (i=3).
    assert expiry_index(CALENDAR, 0, 3) == 3


def test_expiry_t_mas_h_igual_al_ultimo_dato():
    # t = lunes 09 (i=5), H = 4 → viernes 13 = último dato (i=8).
    assert expiry_index(CALENDAR, 5, 4) == 8


def test_expiry_sin_datos_suficientes_none():
    # t = lunes 09, H = 5 → sábado 14, posterior al último dato.
    assert expiry_index(CALENDAR, 5, 5) is None


def test_expiry_sin_sesion_posterior_none():
    # t = viernes 06, H = 1 → sábado 07: el último día ≤ t+H es el propio t.
    assert expiry_index(CALENDAR, 4, 1) is None


# --- Primer índice analizado y aviso de histórico corto ---------------------


def test_first_index_calentamiento_252():
    days = to_day_numbers(_business_days("2010-01-04", 3000))
    start, years_available, warning = first_analyzed_index(days, 30, 5)
    # Recorte por años: primera sesión con fecha ≥ último − 5·365,25 días.
    cut = days[-1] - 5 * 365.25
    expected = int(np.argmax(days >= cut))
    assert start == expected
    assert start > 252
    assert years_available == pytest.approx((days[-1] - days[252]) / 365.25)
    assert warning is None


def test_first_index_ventana_mayor_que_252():
    days = to_day_numbers(_business_days("2010-01-04", 3000))
    start, years_available, _ = first_analyzed_index(days, 300, 50)
    assert start == 300
    assert years_available == pytest.approx((days[-1] - days[300]) / 365.25)


def test_first_index_historico_corto_avisa():
    days = to_day_numbers(_business_days("2020-01-06", 800))
    start, years_available, warning = first_analyzed_index(days, 30, 10)
    assert start == 252
    expected = (days[-1] - days[252]) / 365.25
    assert years_available == pytest.approx(expected)
    assert warning is not None
    assert f"{expected:.1f}".replace(".", ",") in warning
    assert "10" in warning


def test_first_index_tolerancia_025_anos():
    # Disponibles ≈ 4,8 años con 5 pedidos: dentro de la tolerancia, sin aviso.
    days = to_day_numbers(_business_days("2010-01-04", 252 + 1255))
    _, years_available, warning = first_analyzed_index(days, 30, 5)
    assert 4.75 < years_available < 5.0
    assert warning is None


def test_first_index_sin_datos_suficientes():
    days = to_day_numbers(_business_days("2020-01-06", 100))
    start, years_available, warning = first_analyzed_index(days, 30, 1)
    assert start == 100
    assert years_available == 0.0
    assert warning is not None
