"""Tests del catálogo de estrategias (bloque 5: AC15, AC16 motor, AC10).

Comprobamos que hay exactamente 8 plantillas con todos sus textos, que
build_legs produce patas válidas para spots muy distintos, que los
strikes se redondean por tramos y que cada plantilla da las métricas
"de libro" que describe su texto.
"""

import pytest

from opciones import (
    TEMPLATES,
    CommissionSettings,
    Market,
    Template,
    analyze,
    build_legs,
    default_premium,
    validate_legs,
)
from opciones.catalog import STOCK_SHARES, round_strike, strike_step

FEES = CommissionSettings()  # valores por defecto: 0,65 USD por contrato, cierre incluido
NO_FEES = CommissionSettings(per_contract=0.0, index_surcharge=0.0, include_close=False)

EXPECTED_KEYS = {
    "long_call",
    "long_put",
    "covered_call",
    "protective_put",
    "bull_call_spread",
    "bear_put_spread",
    "long_straddle",
    "iron_condor",
}
TEXT_FIELDS = ("key", "name", "market_view", "bet", "max_profit", "max_loss", "when_to_use", "risks")
SPOTS = (20.0, 99.0, 100.0, 250.0, 1000.0, 4500.0)
UNDERLYINGS = ("Acción", "Índice")


def market(spot=100.0, underlying="Acción", **changes):
    data = dict(underlying=underlying, spot=spot, vol=0.20, days=30, rate=0.05, q=0.0)
    data.update(changes)
    return Market(**data)


def template(key: str) -> Template:
    return next(t for t in TEMPLATES if t.key == key)


def strikes(legs):
    return [leg.strike for leg in legs if leg.kind != "stock"]


# ---------------------------------------------------------------- AC15


def test_exactly_eight_templates_with_expected_keys():
    assert len(TEMPLATES) == 8
    assert {t.key for t in TEMPLATES} == EXPECTED_KEYS


@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda t: t.key)
def test_all_text_fields_present_and_not_empty(tpl):
    for name in TEXT_FIELDS:
        value = getattr(tpl, name)
        assert isinstance(value, str) and value.strip(), f"{tpl.key}.{name} vacío"
    assert tpl.legs, f"{tpl.key} sin patas"


# ---------------------------------------------------------------- redondeo


@pytest.mark.parametrize(
    "spot, step",
    [(24.9, 0.5), (25, 1.0), (99.9, 1.0), (100, 2.5), (249, 2.5), (250, 5.0), (999, 5.0), (1000, 10.0)],
)
def test_strike_step_boundaries(spot, step):
    assert strike_step(spot) == step


@pytest.mark.parametrize(
    "value, step, expected",
    [(20.24, 0.5, 20.0), (20.25, 0.5, 20.5), (104.9, 1.0, 105.0), (103.7, 2.5, 102.5), (4725.0, 10.0, 4730.0)],
)
def test_round_strike(value, step, expected):
    assert round_strike(value, step) == pytest.approx(expected)


@pytest.mark.parametrize("spot", SPOTS)
@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda t: t.key)
def test_strikes_are_multiples_of_step(tpl, spot):
    step = strike_step(spot)
    for strike in strikes(build_legs(tpl, market(spot))):
        ratio = strike / step
        assert ratio == pytest.approx(round(ratio))


# ---------------------------------------------------------------- AC16 (motor)


@pytest.mark.parametrize("underlying", UNDERLYINGS)
@pytest.mark.parametrize("spot", SPOTS)
@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda t: t.key)
def test_build_legs_are_valid(tpl, spot, underlying):
    legs = build_legs(tpl, market(spot, underlying))
    assert validate_legs(legs) == []
    assert len(legs) == len(tpl.legs)


@pytest.mark.parametrize("spot", SPOTS)
@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda t: t.key)
def test_premiums_are_black_scholes_and_stock_at_spot(tpl, spot):
    m = market(spot)
    for leg, spec in zip(build_legs(tpl, m), tpl.legs):
        assert leg.kind == spec.kind and leg.side == spec.side
        if leg.kind == "stock":
            assert leg.quantity == STOCK_SHARES
            assert leg.strike is None
            assert leg.price == spot
        else:
            assert leg.price == default_premium(leg.kind, m, leg.strike)
            assert leg.price > 0


@pytest.mark.parametrize("spot", (1.0, 2.0, 5.0) + SPOTS)
def test_strikes_ordered_and_distinct_even_with_low_spot(spot):
    """Sin patas degeneradas: strikes distintos y en el orden de la plantilla."""
    m = market(spot)
    bull = strikes(build_legs(template("bull_call_spread"), m))
    assert bull[0] < bull[1]
    bear = strikes(build_legs(template("bear_put_spread"), m))
    assert bear[0] > bear[1]
    condor = strikes(build_legs(template("iron_condor"), m))
    assert condor[0] < condor[1] < condor[2] < condor[3]
    straddle = strikes(build_legs(template("long_straddle"), m))
    assert straddle[0] == straddle[1]
    covered = strikes(build_legs(template("covered_call"), m))
    assert covered[0] > 0
    for leg_list in (bull, bear, condor, straddle, covered):
        assert all(k > 0 for k in leg_list)


def test_example_strikes_spot_100():
    m = market(100.0)
    assert strikes(build_legs(template("iron_condor"), m)) == [90.0, 95.0, 105.0, 110.0]
    assert strikes(build_legs(template("bull_call_spread"), m)) == [100.0, 105.0]
    assert strikes(build_legs(template("protective_put"), m)) == [95.0]


# ---------------------------------------------------------------- AC10: métricas de libro

METRIC_CASES = [(100.0, "Acción"), (20.0, "Acción"), (4500.0, "Índice")]


def run(key, spot, underlying, settings):
    legs = build_legs(template(key), market(spot, underlying))
    return legs, analyze(market(spot, underlying), legs, settings).metrics


@pytest.mark.parametrize("spot, underlying", METRIC_CASES)
def test_long_call_book_metrics(spot, underlying):
    legs, mt = run("long_call", spot, underlying, NO_FEES)
    (call,) = legs
    assert mt.profit_unlimited and not mt.loss_unlimited and mt.best_pnl is None
    assert mt.worst_pnl == pytest.approx(-call.price * 100, abs=1e-6)
    assert mt.breakevens == pytest.approx([call.strike + call.price], abs=1e-3)


@pytest.mark.parametrize("spot, underlying", METRIC_CASES)
def test_long_put_book_metrics(spot, underlying):
    legs, mt = run("long_put", spot, underlying, NO_FEES)
    (put,) = legs
    assert not mt.profit_unlimited and not mt.loss_unlimited
    assert mt.best_pnl == pytest.approx((put.strike - put.price) * 100, abs=1e-6)
    assert mt.worst_pnl == pytest.approx(-put.price * 100, abs=1e-6)
    assert mt.breakevens == pytest.approx([put.strike - put.price], abs=1e-3)


@pytest.mark.parametrize("spot, underlying", METRIC_CASES)
def test_covered_call_book_metrics(spot, underlying):
    legs, mt = run("covered_call", spot, underlying, NO_FEES)
    stock, call = legs
    assert not mt.profit_unlimited and not mt.loss_unlimited
    assert mt.best_pnl == pytest.approx((call.strike - stock.price + call.price) * 100, abs=1e-6)
    # Pérdida muy grande pero acotada: la acción cae a 0.
    assert mt.worst_pnl == pytest.approx((-stock.price + call.price) * 100, abs=1e-6)
    assert mt.breakevens == pytest.approx([stock.price - call.price], abs=1e-3)


@pytest.mark.parametrize("spot, underlying", METRIC_CASES)
def test_protective_put_book_metrics(spot, underlying):
    legs, mt = run("protective_put", spot, underlying, NO_FEES)
    stock, put = legs
    assert mt.profit_unlimited and not mt.loss_unlimited
    assert mt.worst_pnl == pytest.approx((put.strike - stock.price - put.price) * 100, abs=1e-6)
    assert mt.breakevens == pytest.approx([stock.price + put.price], abs=1e-3)


@pytest.mark.parametrize("spot, underlying", METRIC_CASES)
def test_bull_call_spread_book_metrics(spot, underlying):
    legs, mt = run("bull_call_spread", spot, underlying, NO_FEES)
    long_call, short_call = legs
    debit = long_call.price - short_call.price
    assert not mt.profit_unlimited and not mt.loss_unlimited
    assert mt.worst_pnl == pytest.approx(-debit * 100, abs=1e-6)
    assert mt.best_pnl == pytest.approx((short_call.strike - long_call.strike - debit) * 100, abs=1e-6)
    assert mt.breakevens == pytest.approx([long_call.strike + debit], abs=1e-3)


@pytest.mark.parametrize("spot, underlying", METRIC_CASES)
def test_bear_put_spread_book_metrics(spot, underlying):
    legs, mt = run("bear_put_spread", spot, underlying, NO_FEES)
    long_put, short_put = legs
    debit = long_put.price - short_put.price
    assert not mt.profit_unlimited and not mt.loss_unlimited
    assert mt.worst_pnl == pytest.approx(-debit * 100, abs=1e-6)
    assert mt.best_pnl == pytest.approx((long_put.strike - short_put.strike - debit) * 100, abs=1e-6)
    assert mt.breakevens == pytest.approx([long_put.strike - debit], abs=1e-3)


@pytest.mark.parametrize("spot, underlying", METRIC_CASES)
def test_long_straddle_book_metrics(spot, underlying):
    legs, mt = run("long_straddle", spot, underlying, NO_FEES)
    call, put = legs
    cost = call.price + put.price
    assert mt.profit_unlimited and not mt.loss_unlimited
    assert mt.worst_pnl == pytest.approx(-cost * 100, abs=1e-6)
    assert mt.breakevens == pytest.approx([call.strike - cost, call.strike + cost], abs=1e-3)


@pytest.mark.parametrize("spot, underlying", METRIC_CASES)
def test_iron_condor_book_metrics(spot, underlying):
    legs, mt = run("iron_condor", spot, underlying, NO_FEES)
    long_put, short_put, short_call, long_call = legs
    credit = short_put.price - long_put.price + short_call.price - long_call.price
    widest = max(short_put.strike - long_put.strike, long_call.strike - short_call.strike)
    assert credit > 0
    assert not mt.profit_unlimited and not mt.loss_unlimited
    assert mt.best_pnl == pytest.approx(credit * 100, abs=1e-6)
    assert mt.worst_pnl == pytest.approx((credit - widest) * 100, abs=1e-6)
    assert mt.breakevens == pytest.approx(
        [short_put.strike - credit, short_call.strike + credit], abs=1e-3
    )


# Forma de libro con comisiones por defecto: banderas y número de breakevens.
SHAPES = {
    "long_call": (True, 1),
    "long_put": (False, 1),
    "covered_call": (False, 1),
    "protective_put": (True, 1),
    "bull_call_spread": (False, 1),
    "bear_put_spread": (False, 1),
    "long_straddle": (True, 2),
    "iron_condor": (False, 2),
}


@pytest.mark.parametrize("settings", [NO_FEES, FEES], ids=["sin_comisiones", "comisiones_defecto"])
@pytest.mark.parametrize("spot, underlying", METRIC_CASES)
@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda t: t.key)
def test_book_shape_per_template(tpl, spot, underlying, settings):
    profit_unlimited, n_breakevens = SHAPES[tpl.key]
    _, mt = run(tpl.key, spot, underlying, settings)
    assert mt.profit_unlimited is profit_unlimited
    assert mt.loss_unlimited is False  # ninguna plantilla tiene pérdida ilimitada
    assert mt.worst_pnl is not None and mt.worst_pnl < 0
    assert len(mt.breakevens) == n_breakevens


@pytest.mark.parametrize("spot, underlying", METRIC_CASES)
def test_spreads_never_lose_more_than_debit_plus_fees(spot, underlying):
    """Un spread comprado nunca pierde más que lo pagado más las comisiones.

    El peor punto es justo al pasar el strike de la pata comprada: ya
    vence con valor (paga cierre) pero aún no compensa. Por eso la
    pérdida máxima = coste neto + 2 aperturas + 1 cierre.
    """
    m = market(spot, underlying)
    fee = FEES.per_contract + (FEES.index_surcharge if underlying == "Índice" else 0.0)
    for key in ("bull_call_spread", "bear_put_spread"):
        legs, mt = run(key, spot, underlying, FEES)
        debit = (legs[0].price - legs[1].price) * 100
        assert mt.worst_pnl == pytest.approx(-(debit + 3 * fee), abs=1e-6), key
        assert analyze(m, legs, FEES).metrics.worst_pnl == mt.worst_pnl


@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda t: t.key)
def test_texts_consistent_with_metrics(tpl):
    """«Ilimitado» aparece en el texto de beneficio/pérdida solo si las métricas lo dicen."""
    _, mt = run(tpl.key, 100.0, "Acción", FEES)
    assert ("ilimitad" in tpl.max_profit.lower()) is mt.profit_unlimited
    assert ("ilimitad" in tpl.max_loss.lower()) is mt.loss_unlimited
