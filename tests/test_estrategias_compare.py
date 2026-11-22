"""Tests de estrategias/compare.py (Etapa D, bloque 3; AC-D-8, AC-D-9).

Todo se contrasta con lo que el motor calcula para cada estrategia sola
(compute_metrics, pnl_expiry, pnl_today, exact_pop, position_greeks,
analyze). Las primas netas se comprueban con oráculos escritos a mano.
"""

import time

import numpy as np
import pytest

from estrategias import compare
from estrategias.compare import (
    MAX_STRATEGIES,
    ComparisonResult,
    ComparisonRow,
    common_grid,
    compare_strategies,
    market_difference_notice,
    net_premium,
    revalue_legs,
)
from estrategias.serialize import SavedLeg
from opciones import (
    TEMPLATES,
    CommissionSettings,
    Leg,
    Market,
    SimulationSettings,
    analyze,
    build_legs,
    compute_metrics,
    default_premium,
    pnl_expiry,
    pnl_today,
    position_greeks,
    price_grid,
)
from opciones.simulation import exact_pop

BS = "black_scholes"
MARKET_BS = Market("Acción", 100.0, 0.25, 45, 0.04, 0.01, BS)
SETTINGS = CommissionSettings()
SIM = SimulationSettings()


def template(key):
    return next(t for t in TEMPLATES if t.key == key)


def iron_condor(market=MARKET_BS):
    return build_legs(template("iron_condor"), market)


def long_call(strike=100.0, price=2.5, quantity=1.0):
    return [Leg("call", 1, quantity, strike, price)]


def bull_spread():
    return [Leg("call", 1, 1.0, 90.0, 12.0), Leg("call", -1, 1.0, 110.0, 3.0)]


def strangle():
    return [Leg("put", -1, 2.0, 80.0, 1.0), Leg("call", -1, 2.0, 125.0, 0.8)]


# --- net_premium (DD-12) ---


def test_prima_neta_oraculos_simples():
    assert net_premium(long_call(price=2.5)) == pytest.approx(-250.0)
    assert net_premium([Leg("call", -1, 1.0, 100.0, 3.0)]) == pytest.approx(300.0)
    assert net_premium(long_call(price=2.5, quantity=2.0)) == pytest.approx(-500.0)
    assert net_premium([]) == 0.0


def test_prima_neta_excluye_acciones():
    covered_call = [Leg("stock", 1, 100.0, None, 100.0), Leg("call", -1, 1.0, 110.0, 1.2)]
    assert net_premium(covered_call) == pytest.approx(120.0)


def test_prima_neta_iron_condor_a_mano():
    long_put, short_put, short_call, long_call_leg = iron_condor()
    # Crédito = (primas vendidas − primas compradas) × 100.
    expected = (short_put.price + short_call.price - long_put.price - long_call_leg.price) * 100
    assert expected > 0  # un iron condor cobra crédito
    assert net_premium(iron_condor()) == pytest.approx(expected)


# --- common_grid ---


def test_malla_comun():
    strategies = [iron_condor(), long_call(130.0), bull_spread()]
    grids = [price_grid(MARKET_BS, legs) for legs in strategies]
    grid = common_grid(grids)
    assert np.all(np.diff(grid) > 0)  # ordenada y sin duplicados
    assert len(grid) <= sum(len(g) for g in grids)
    for legs, own in zip(strategies, grids):
        assert np.all(np.isin(own, grid))
        for leg in legs:
            for point in (leg.strike - 1e-9, leg.strike, leg.strike + 1e-9):
                assert np.any(np.isclose(grid, point, rtol=0, atol=1e-12))


def test_malla_comun_una_sola_y_vacia():
    own = price_grid(MARKET_BS, iron_condor())
    assert np.array_equal(common_grid([own]), own)
    assert len(common_grid([])) == 0


# --- revalue_legs (DD-13) ---


def saved(kind="call", side=1, quantity=1.0, strike=105.0, price=3.33,
          premium_manual=False, premium_source=None, bid=None, ask=None, expiry=None):
    return SavedLeg(kind, side, quantity, strike, price, premium_manual,
                    premium_source, bid, ask, expiry)


@pytest.mark.parametrize("pricing_model", [BS, "binomial"])
def test_revaloracion(pricing_model):
    market = Market("Acción", 120.0, 0.3, 30, 0.05, 0.0, pricing_model)
    legs = revalue_legs(
        [
            saved(premium_manual=True, price=3.33),
            saved(premium_source="mercado", price=1.9, bid=1.8, ask=2.0, expiry="2026-12-18"),
            saved(premium_source="manual", price=4.44),
            saved(kind="put", side=-1, strike=110.0, price=0.5),
            saved(kind="stock", quantity=100.0, strike=None, price=80.0),
        ],
        market,
    )
    assert legs[0] == Leg("call", 1, 1.0, 105.0, 3.33)
    assert legs[1] == Leg("call", 1, 1.0, 105.0, 1.9)
    assert legs[2] == Leg("call", 1, 1.0, 105.0, 4.44)
    assert legs[3].price == pytest.approx(default_premium("put", market, 110.0))
    assert legs[3].price != 0.5
    assert legs[4] == Leg("stock", 1, 100.0, None, 120.0)


# --- market_difference_notice ---


def test_aviso_mercado_igual_es_none():
    assert market_difference_notice("IC", MARKET_BS, Market("Acción", 100.0 + 1e-12, 0.25, 45, 0.04, 0.01, BS)) is None


def test_aviso_spot_distinto():
    saved_market = Market("Acción", 80.0, 0.25, 45, 0.04, 0.01, BS)
    text = market_difference_notice("Mi IC", saved_market, MARKET_BS)
    assert "«Mi IC»" in text
    assert "80" in text and "100" in text
    assert "aquí se usa el mercado actual" in text


def test_aviso_vol_y_dias_distintos():
    saved_market = Market("Acción", 100.0, 0.3, 60, 0.04, 0.01, BS)
    text = market_difference_notice("X", saved_market, MARKET_BS)
    assert "30 %" in text and "60 días" in text


def test_aviso_tolerancia():
    nearly = Market("Acción", 100.0 + 5e-10, 0.25 + 5e-10, 45, 0.04, 0.01, BS)
    assert market_difference_notice("X", nearly, MARKET_BS) is None
    far = Market("Acción", 100.0 + 1e-6, 0.25, 45, 0.04, 0.01, BS)
    assert market_difference_notice("X", far, MARKET_BS) is not None


def test_aviso_subyacente_tasa_dividendo_modelo():
    # E-7: si difieren, se añaden al mismo texto.
    saved_market = Market("Índice", 100.0, 0.25, 45, 0.05, 0.02, "binomial")
    text = market_difference_notice("X", saved_market, MARKET_BS)
    assert text is not None
    assert "Índice" in text
    assert "tasa" in text and "dividendo" in text and "modelo" in text


# --- compare_strategies (AC-D-8, AC-D-9) ---


ENTRIES = [("Iron condor", iron_condor()), ("Call", long_call(105.0, 2.0)), ("Spread", bull_spread())]


@pytest.mark.parametrize("include_close", [True, False])
def test_filas_iguales_al_motor(include_close):
    settings = CommissionSettings(0.65, 0.6, include_close)
    result = compare_strategies(ENTRIES, MARKET_BS, settings, SIM)
    assert isinstance(result, ComparisonResult)
    assert result.errors == []
    assert [row.label for row in result.rows] == ["Iron condor", "Call", "Spread"]
    for row, (_, legs) in zip(result.rows, ENTRIES):
        assert isinstance(row, ComparisonRow)
        metrics = compute_metrics(legs, MARKET_BS, settings)
        assert row.best_pnl == metrics.best_pnl
        assert row.worst_pnl == metrics.worst_pnl
        assert row.profit_unlimited == metrics.profit_unlimited
        assert row.loss_unlimited == metrics.loss_unlimited
        assert row.breakevens == pytest.approx(metrics.breakevens)
        assert row.commission_total == pytest.approx(analyze(MARKET_BS, legs, settings).commission_total)
        assert row.net_premium == pytest.approx(net_premium(legs))
        assert row.pop == pytest.approx(exact_pop(MARKET_BS, legs, settings, SIM))
        assert row.greeks is None


def test_call_larga_ganancia_ilimitada():
    result = compare_strategies([("Call", long_call())], MARKET_BS, SETTINGS, SIM)
    row = result.rows[0]
    assert row.profit_unlimited and row.best_pnl is None
    assert not row.loss_unlimited


def test_curvas_de_vencimiento_iguales_a_las_individuales():
    result = compare_strategies(ENTRIES, MARKET_BS, SETTINGS, SIM)
    expected_grid = common_grid([price_grid(MARKET_BS, legs) for _, legs in ENTRIES])
    assert np.array_equal(result.grid, expected_grid)
    assert len(result.expiry_curves) == 3
    for curve, (_, legs) in zip(result.expiry_curves, ENTRIES):
        assert curve == pytest.approx(pnl_expiry(legs, MARKET_BS, SETTINGS, result.grid))


def test_pop_con_mu():
    sim = SimulationSettings(mu=0.10)
    result = compare_strategies(ENTRIES, MARKET_BS, SETTINGS, sim)
    for row, (_, legs) in zip(result.rows, ENTRIES):
        assert row.pop == pytest.approx(exact_pop(MARKET_BS, legs, SETTINGS, sim))


def test_pop_none_con_cero_dias():
    market = Market("Acción", 100.0, 0.25, 0, 0.04, 0.01, BS)
    result = compare_strategies(ENTRIES, market, SETTINGS, SIM)
    assert result.errors == []
    assert all(row.pop is None for row in result.rows)


def test_sin_casilla_no_se_calcula_hoy_ni_griegas(monkeypatch):
    calls = {"today": 0, "greeks": 0}

    def spy_today(*args, **kwargs):
        calls["today"] += 1
        return pnl_today(*args, **kwargs)

    def spy_greeks(*args, **kwargs):
        calls["greeks"] += 1
        return position_greeks(*args, **kwargs)

    monkeypatch.setattr(compare, "pnl_today", spy_today)
    monkeypatch.setattr(compare, "position_greeks", spy_greeks)
    result = compare_strategies(ENTRIES, MARKET_BS, SETTINGS, SIM)
    assert calls == {"today": 0, "greeks": 0}
    assert result.today_curves is None
    assert all(row.greeks is None for row in result.rows)
    compare_strategies(ENTRIES, MARKET_BS, SETTINGS, SIM, with_heavy=True)
    assert calls == {"today": 3, "greeks": 3}


@pytest.mark.parametrize("pricing_model", [BS, "binomial"])
def test_con_casilla_hoy_en_malla_propia_y_griegas(pricing_model):
    market = Market("Acción", 100.0, 0.25, 45, 0.04, 0.01, pricing_model)
    entries = [("IC", iron_condor(market)), ("Call", long_call(140.0, 0.5))]
    result = compare_strategies(entries, market, SETTINGS, SIM, with_heavy=True)
    assert result.errors == []
    assert len(result.today_curves) == 2
    for (grid_i, curve_i), (_, legs), row in zip(result.today_curves, entries, result.rows):
        own = price_grid(market, legs)
        assert np.array_equal(grid_i, own)  # malla PROPIA (DD-23), no la común
        assert len(grid_i) < len(result.grid)
        assert curve_i == pytest.approx(pnl_today(legs, market, SETTINGS, own))
        expected = position_greeks(legs, market)
        assert row.greeks.keys() == expected.keys()
        for name in expected:
            assert row.greeks[name] == pytest.approx(expected[name])


def test_griegas_none_con_cero_dias():
    market = Market("Acción", 100.0, 0.25, 0, 0.04, 0.01, BS)
    result = compare_strategies(ENTRIES, market, SETTINGS, SIM, with_heavy=True)
    assert result.errors == []
    for row in result.rows:
        assert all(value is None for value in row.greeks.values())


def test_mas_de_cuatro_entradas():
    assert MAX_STRATEGIES == 4
    entries = [(f"E{i}", long_call()) for i in range(5)]
    result = compare_strategies(entries, MARKET_BS, SETTINGS, SIM)
    assert result.rows == []
    assert len(result.errors) == 1 and "Máximo 4" in result.errors[0]


def test_entrada_invalida_se_omite():
    bad = [Leg("call", 1, -1.0, 100.0, 2.0)]
    result = compare_strategies([("Mala", bad), ("Call", long_call())], MARKET_BS, SETTINGS, SIM)
    assert [row.label for row in result.rows] == ["Call"]
    assert len(result.expiry_curves) == 1
    assert len(result.errors) == 1 and result.errors[0].startswith("«Mala»: ")


def test_lista_vacia():
    result = compare_strategies([], MARKET_BS, SETTINGS, SIM)
    assert result.rows == [] and result.expiry_curves == [] and result.errors == []
    assert len(result.grid) == 0 and result.today_curves is None


def test_mercado_invalido_no_lanza():
    market = Market("Acción", 0.0, 0.25, 45, 0.04)
    result = compare_strategies(ENTRIES, market, SETTINGS, SIM)
    assert result.rows == [] and result.errors


# --- Red de seguridad (DD-22) ---


def test_motor_que_lanza_omite_esa_entrada(monkeypatch):
    real = compare.compute_metrics

    def flaky(legs, market, settings):
        if legs[0].strike == 105.0:
            raise ZeroDivisionError("simulado")
        return real(legs, market, settings)

    monkeypatch.setattr(compare, "compute_metrics", flaky)
    result = compare_strategies(ENTRIES, MARKET_BS, SETTINGS, SIM)
    assert [row.label for row in result.rows] == ["Iron condor", "Spread"]
    assert result.errors == ["No se pudo calcular «Call»."]


def assert_all_finite(result):
    assert np.all(np.isfinite(result.grid))
    for curve in result.expiry_curves:
        assert np.all(np.isfinite(curve))
    for grid_i, curve_i in result.today_curves or []:
        assert np.all(np.isfinite(grid_i)) and np.all(np.isfinite(curve_i))
    for row in result.rows:
        values = [row.best_pnl, row.worst_pnl, row.commission_total, row.net_premium, row.pop]
        values += list(row.breakevens) + list((row.greeks or {}).values())
        for value in values:
            assert value is None or np.isfinite(value)


@pytest.mark.parametrize("with_heavy", [False, True])
def test_valores_hostiles_se_omiten(with_heavy):
    huge_quantity = [Leg("call", 1, 1e308, 100.0, 2.0)]
    huge_price = [Leg("put", -1, 1.0, 100.0, 1e308)]
    entries = [("Q", huge_quantity), ("P", huge_price), ("Call", long_call())]
    result = compare_strategies(entries, MARKET_BS, SETTINGS, SIM, with_heavy=with_heavy)
    assert [row.label for row in result.rows] == ["Call"]
    assert result.errors == ["No se pudo calcular «Q».", "No se pudo calcular «P»."]
    assert_all_finite(result)


def test_resultado_normal_es_finito():
    assert_all_finite(compare_strategies(ENTRIES, MARKET_BS, SETTINGS, SIM, with_heavy=True))


# --- Tiempos (cotas holgadas; se imprime lo medido, ver con -s) ---


def test_tiempo_sin_casilla_cuatro_estrategias_binomial():
    # Mercado poco habitual para que la caché del árbol esté fría.
    market = Market("Acción", 123.47, 0.2713, 47, 0.0391, 0.0057, "binomial")
    saved_sets = []
    for key in ("iron_condor", "iron_condor", "iron_condor", "iron_condor"):
        legs = build_legs(template(key), Market("Acción", 100.0, 0.25, 45, 0.04, 0.01, BS))
        saved_sets.append([saved(leg.kind, leg.side, leg.quantity, leg.strike, leg.price) for leg in legs])
    start = time.perf_counter()
    entries = [(f"E{i}", revalue_legs(legs, market)) for i, legs in enumerate(saved_sets)]
    result = compare_strategies(entries, market, SETTINGS, SIM)
    elapsed = time.perf_counter() - start
    print(f"\n[medido] comparación sin casilla, 4 estrategias de 4 patas (binomial en frío): {elapsed:.3f} s")
    assert len(result.rows) == 4
    assert elapsed < 2.0


def test_tiempo_con_casilla_cuatro_iron_condors_binomial_en_frio():
    # Cuatro iron condors distintos con un mercado binomial nuevo (caché fría).
    market = Market("Acción", 101.37, 0.2591, 45, 0.0417, 0.0083, "binomial")
    entries = []
    for i, spot in enumerate((101.37, 96.0, 106.0, 111.0)):
        legs = build_legs(template("iron_condor"), Market("Acción", spot, 0.2591, 45, 0.0417, 0.0083, "binomial"))
        entries.append((f"IC{i}", legs))
    start = time.perf_counter()
    result = compare_strategies(entries, market, SETTINGS, SIM, with_heavy=True)
    elapsed = time.perf_counter() - start
    print(f"\n[medido] comparación con casilla, 4 iron condors (binomial, 45 días, frío): {elapsed:.3f} s")
    assert result.errors == [] and len(result.today_curves) == 4
    assert elapsed < 6.0
