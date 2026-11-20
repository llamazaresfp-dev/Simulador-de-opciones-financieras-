"""Tests de la volatilidad implícita americana (Etapa B1, bloque 4: AC-B9, AC-B10).

La IV debe usar el MISMO modelo que la prima: en Acción/ETF con el
modelo binomial, el árbol americano (500/501 pasos promediados).

Idea de los tests:
- Ida y vuelta: prima del árbol con σ -> IV -> prima del árbol con la IV.
  El precio debe reproducirse SIEMPRE que haya IV.
- La σ solo se recupera donde el precio depende de verdad de σ
  (vega > 0,01 y prima claramente por encima del intrínseco). En una
  opción americana muy dentro del dinero, lo óptimo es ejercer ya: el
  precio es el intrínseco para muchas σ distintas, así que la IV no se
  puede identificar y la función debe decirlo con un mensaje.
- La rama europea (Índice, o Acción con "black_scholes") no cambia.
"""

import math

import pytest

from opciones import IVResult, Leg, Market, bs_price, implied_vol
from opciones.binomial import crr_price
from opciones.implied_vol import (
    AMERICAN_MIN_VEGA,
    MAX_SIGMA_UNCERTAINTY,
    MSG_ABOVE_UPPER_BOUND,
    MSG_AMERICAN_BELOW_INTRINSIC,
    MSG_AMERICAN_NOT_IDENTIFIABLE,
    MSG_BELOW_LOWER_BOUND,
    MSG_INVALID_DATA,
    MSG_NO_TIME,
    MSG_PREMIUM_NOT_POSITIVE,
    MSG_SOLVER_FAILED,
    MSG_STOCK_LEG,
    PREMIUM_PRECISION,
    VOL_LOW,
)
from opciones.pricing import option_greeks

SPOT = 100.0
RATE = 0.04
Q = 0.01

KINDS = ("call", "put")
STRIKES = (90.0, 100.0, 110.0)
SIGMAS = (0.10, 0.25, 0.60)
DAYS = (1, 45, 365)

PRICE_TOL = 1e-6
SIGMA_TOL = 1e-4


def make_market(days=45, vol=0.25, rate=RATE, q=Q, spot=SPOT, underlying="Acción",
                pricing_model="binomial"):
    return Market(underlying=underlying, spot=spot, vol=vol, days=days, rate=rate, q=q,
                  pricing_model=pricing_model)


def option_leg(kind, strike, premium):
    return Leg(kind=kind, side=1, quantity=1, strike=strike, price=premium)


def tree_price(kind, market, strike, sigma):
    """Prima americana del árbol (la misma que usa la app)."""
    return crr_price(kind, market.spot, strike, market.rate, market.q, sigma, market.T)


def intrinsic(kind, spot, strike):
    return max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)


def above_intrinsic(premium, value):
    """Prima claramente por encima del intrínseco (misma tolerancia que el motor)."""
    return premium > value * (1 + 1e-6) + 1e-9


def check_result_shape(result):
    """`vol` y `message`: siempre exactamente uno de los dos es None."""
    assert isinstance(result, IVResult)
    assert (result.vol is None) != (result.message is None)
    if result.vol is not None:
        assert math.isfinite(result.vol)


# --- Ida y vuelta (matriz C4) -------------------------------------------------


ROUND_TRIP_CASES = [
    (kind, strike, sigma, days)
    for kind in KINDS for strike in STRIKES for sigma in SIGMAS for days in DAYS
]


@pytest.mark.parametrize("kind,strike,sigma,days", ROUND_TRIP_CASES)
def test_round_trip_tree_premium(kind, strike, sigma, days):
    """Prima del árbol con σ -> IV -> prima del árbol (AC-B9)."""
    market = make_market(days=days, vol=sigma)
    premium = tree_price(kind, market, strike, sigma)
    value = intrinsic(kind, SPOT, strike)
    result = implied_vol(option_leg(kind, strike, premium), market)
    check_result_shape(result)

    if premium <= 0:
        # OTM a 1 día con σ baja: el árbol da 0 y manda la comprobación común.
        assert result.message == MSG_PREMIUM_NOT_POSITIVE
        return

    if not above_intrinsic(premium, value):
        # Precio plano en σ (ejercicio anticipado óptimo): no hay IV.
        assert result.vol is None
        assert result.message == MSG_AMERICAN_NOT_IDENTIFIABLE
        return

    if result.vol is None:
        # Solo se acepta si (a) el precio con σ mínima ya alcanza la prima
        # (región plana en σ, p. ej. call ITM con forward > intrínseco), o
        # (b) la regla de precisión (20-11-26): medio céntimo de prima movería
        # σ más de 5 puntos (vega < 0,1 por unidad de σ). Casos (b) de esta
        # matriz, todos a 1 día con σ = 60 %: call K=90, call K=110, put K=90
        # (vega ≈ 0,007–0,02 por unidad de σ: incertidumbre de σ 0,25–0,73).
        assert result.message == MSG_AMERICAN_NOT_IDENTIFIABLE
        flat = tree_price(kind, market, strike, VOL_LOW) >= premium - PRICE_TOL
        vega_per_unit = option_greeks(kind, market, strike)["vega"] * 100
        imprecise = vega_per_unit * MAX_SIGMA_UNCERTAINTY < PREMIUM_PRECISION
        assert flat or imprecise
        return

    # El precio se reproduce siempre que hay IV.
    assert tree_price(kind, market, strike, result.vol) == pytest.approx(premium, abs=PRICE_TOL)

    # La σ solo se exige donde la vega no es casi 0 (si no, está mal condicionada).
    vega = option_greeks(kind, market, strike)["vega"]
    if vega > 0.01:
        assert result.vol == pytest.approx(sigma, abs=SIGMA_TOL)


def test_round_trip_sigma_recovered_in_most_cases():
    """La comprobación de σ no queda vacía: se aplica en la mayoría de casos."""
    checked = 0
    for kind, strike, sigma, days in ROUND_TRIP_CASES:
        market = make_market(days=days, vol=sigma)
        premium = tree_price(kind, market, strike, sigma)
        if not above_intrinsic(premium, intrinsic(kind, SPOT, strike)):
            continue
        if option_greeks(kind, market, strike)["vega"] > 0.01:
            checked += 1
    assert checked >= 30


def test_premium_from_market_vol_gives_market_vol():
    """Prima = precio del modelo con `market.vol` -> IV ≈ `market.vol`."""
    market = make_market(days=182.5, vol=0.25)
    premium = tree_price("put", market, 100.0, market.vol)
    result = implied_vol(option_leg("put", 100.0, premium), market)
    assert result.message is None
    assert result.vol == pytest.approx(0.25, abs=SIGMA_TOL)


def test_itm_call_one_day_is_ill_conditioned():
    """Call ITM a 1 día (K=90, σ=25 %): región mal condicionada esperada.

    La vega es casi 0: el precio apenas cambia con σ, así que la IV que
    reproduce la prima puede estar lejos de 25 % (≈ 0,15 de diferencia) o
    no ser identificable. Lo que sí se exige: si hay IV, reproduce el precio.
    """
    market = make_market(days=1, vol=0.25)
    premium = tree_price("call", market, 90.0, 0.25)
    assert option_greeks("call", market, 90.0)["vega"] < 0.01
    result = implied_vol(option_leg("call", 90.0, premium), market)
    check_result_shape(result)
    if result.vol is None:
        assert result.message == MSG_AMERICAN_NOT_IDENTIFIABLE
    else:
        assert tree_price("call", market, 90.0, result.vol) == pytest.approx(
            premium, abs=PRICE_TOL)
        assert abs(result.vol - 0.25) <= 0.2


# --- Prima en el intrínseco o fuera de límites (AC-B10) -----------------------


def test_deep_itm_put_at_intrinsic_is_not_identifiable():
    """Put S=100, K=140, T=1 año, σ=20 %: el árbol vale 40 = intrínseco."""
    market = make_market(days=365, vol=0.20)
    premium = tree_price("put", market, 140.0, 0.20)
    assert premium == pytest.approx(40.0, abs=1e-9)
    for price in (premium, 40.0):
        result = implied_vol(option_leg("put", 140.0, price), market)
        assert result.vol is None
        assert result.message == MSG_AMERICAN_NOT_IDENTIFIABLE


def test_itm_put_at_intrinsic_is_not_identifiable():
    """Put S=100, K=110 con prima = intrínseco (10): precio plano en σ."""
    market = make_market(days=45, vol=0.25)
    result = implied_vol(option_leg("put", 110.0, 10.0), market)
    assert result.vol is None
    assert result.message == MSG_AMERICAN_NOT_IDENTIFIABLE


def test_itm_call_below_forward_value_is_not_identifiable():
    """Call S=100, K=50, q=0, T=1 año: incluso con σ mínima vale S − K·e^(−rT) ≈ 51,96.

    Una prima de 51 supera el intrínseco (50) pero ninguna σ la alcanza
    por abajo: el precio del modelo no baja de ≈ 51,96.
    """
    market = make_market(days=365, vol=0.25, q=0.0)
    result = implied_vol(option_leg("call", 50.0, 51.0), market)
    assert result.vol is None
    assert result.message == MSG_AMERICAN_NOT_IDENTIFIABLE


def test_premium_below_intrinsic():
    market = make_market(days=365, vol=0.20)
    result = implied_vol(option_leg("put", 140.0, 39.0), market)
    assert result.vol is None
    assert result.message == MSG_AMERICAN_BELOW_INTRINSIC

    result = implied_vol(option_leg("call", 80.0, 19.5), market)
    assert result.message == MSG_AMERICAN_BELOW_INTRINSIC


def test_american_lower_bound_is_undiscounted_intrinsic():
    """Una prima entre el intrínseco descontado y el intrínseco no tiene IV americana.

    Put K=140, T=1 año: K·e^(−rT) − S·e^(−qT) ≈ 35,5 < 38 < 40 = intrínseco.
    En europeo 38 sería una prima posible; en americano no (se ejerce hoy y
    se cobran 40).
    """
    market = make_market(days=365, vol=0.20)
    result = implied_vol(option_leg("put", 140.0, 38.0), market)
    assert result.message == MSG_AMERICAN_BELOW_INTRINSIC
    european = make_market(days=365, vol=0.20, pricing_model="black_scholes")
    assert implied_vol(option_leg("put", 140.0, 38.0), european).vol is not None


@pytest.mark.parametrize("kind,strike,premium", [
    ("call", 100.0, 100.0),
    ("call", 100.0, 150.0),
    ("put", 110.0, 110.0),
    ("put", 110.0, 200.0),
])
def test_premium_at_or_above_upper_bound(kind, strike, premium):
    """Límite superior americano: call < S, put < K (sin descontar)."""
    result = implied_vol(option_leg(kind, strike, premium), make_market())
    assert result.vol is None
    assert result.message == MSG_ABOVE_UPPER_BOUND


def test_call_premium_near_spot_never_raises():
    """Prima de call entre S·e^(−qT) y S: en americano no se rechaza por límites."""
    market = make_market(days=365)
    result = implied_vol(option_leg("call", 100.0, 99.9), market)
    check_result_shape(result)
    assert result.message in (None, MSG_SOLVER_FAILED)


# --- Mensajes comunes con el modelo binomial ----------------------------------


def test_common_messages_with_binomial():
    market = make_market()
    assert implied_vol(Leg("stock", 1, 1, 0.0, 100.0), market).message == MSG_STOCK_LEG
    assert implied_vol(option_leg("call", 100.0, 3.0), make_market(days=0)).message == MSG_NO_TIME
    assert implied_vol(option_leg("call", 100.0, 0.0), market).message == MSG_PREMIUM_NOT_POSITIVE
    assert implied_vol(option_leg("put", 100.0, -1.0), market).message == MSG_PREMIUM_NOT_POSITIVE
    assert implied_vol(option_leg("call", None, 3.0), market).message == MSG_INVALID_DATA
    assert implied_vol(option_leg("call", 0.0, 3.0), market).message == MSG_INVALID_DATA


def test_all_messages_are_distinct():
    messages = [
        MSG_STOCK_LEG, MSG_NO_TIME, MSG_PREMIUM_NOT_POSITIVE, MSG_BELOW_LOWER_BOUND,
        MSG_ABOVE_UPPER_BOUND, MSG_SOLVER_FAILED, MSG_INVALID_DATA,
        MSG_AMERICAN_NOT_IDENTIFIABLE, MSG_AMERICAN_BELOW_INTRINSIC,
    ]
    assert len(set(messages)) == len(messages)


def test_not_identifiable_message_text():
    assert MSG_AMERICAN_NOT_IDENTIFIABLE == (
        "No se puede identificar la IV: con esta prima el precio del modelo no "
        "depende de la volatilidad (ejercicio anticipado óptimo)."
    )


@pytest.mark.parametrize("premium", [math.nan, math.inf, -math.inf, None, "3", 1e-300, 1e300])
@pytest.mark.parametrize("kind", KINDS)
def test_never_raises_on_odd_premiums(kind, premium):
    result = implied_vol(option_leg(kind, 100.0, premium), make_market())
    check_result_shape(result)


@pytest.mark.parametrize("market_kwargs", [
    {"vol": 1e-6}, {"vol": 10.0}, {"spot": 0.0}, {"spot": math.nan}, {"rate": 0.5},
    {"rate": -0.05, "q": 0.20}, {"days": 3650}, {"days": 0.01}, {"rate": None},
])
@pytest.mark.parametrize("kind", KINDS)
def test_never_raises_on_odd_markets(kind, market_kwargs):
    for strike in (1.0, 100.0, 10_000.0):
        result = implied_vol(option_leg(kind, strike, 5.0), make_market(**market_kwargs))
        check_result_shape(result)


def test_etf_uses_american_branch():
    market = make_market(days=365, vol=0.20, underlying="ETF")
    result = implied_vol(option_leg("put", 140.0, 40.0), market)
    assert result.message == MSG_AMERICAN_NOT_IDENTIFIABLE


# --- La rama europea no cambia (Índice / Black-Scholes fijado) ----------------


EUROPEAN_CASES = [
    (kind, strike, sigma, days)
    for kind in KINDS for strike in (85.0, 100.0, 115.0) for sigma in (0.10, 0.25, 0.60)
    for days in (1, 45, 365)
]


def stage_a_reference(kind, market, strike, premium):
    """Algoritmo de la Etapa A reescrito aquí: límites europeos + brentq sobre BS."""
    from scipy.optimize import brentq

    stock_pv = market.spot * math.exp(-market.q * market.T)
    strike_pv = strike * math.exp(-market.rate * market.T)
    if kind == "call":
        lower, upper = max(stock_pv - strike_pv, 0.0), stock_pv
    else:
        lower, upper = max(strike_pv - stock_pv, 0.0), strike_pv
    if premium <= lower:
        return None, MSG_BELOW_LOWER_BOUND
    if premium >= upper:
        return None, MSG_ABOVE_UPPER_BOUND

    def gap(sigma):
        return bs_price(kind, market.spot, strike, market.rate, market.q, sigma,
                        market.T) - premium

    try:
        return float(brentq(gap, 1e-6, 10.0, xtol=1e-14, rtol=1e-14)), None
    except (ValueError, RuntimeError):
        return None, MSG_SOLVER_FAILED


@pytest.mark.parametrize("kind,strike,sigma,days", EUROPEAN_CASES)
def test_european_branch_equals_stage_a(kind, strike, sigma, days):
    """Índice (con cualquier selector) y Acción fijada a BS = Etapa A, número a número."""
    markets = [
        make_market(days=days, vol=sigma, underlying="Índice"),
        make_market(days=days, vol=sigma, underlying="Índice", pricing_model="black_scholes"),
        make_market(days=days, vol=sigma, pricing_model="black_scholes"),
        make_market(days=days, vol=sigma, underlying="ETF", pricing_model="black_scholes"),
    ]
    premium = bs_price(kind, SPOT, strike, RATE, Q, sigma, days / 365)
    expected = stage_a_reference(kind, markets[0], strike, premium)
    for market in markets:
        result = implied_vol(option_leg(kind, strike, premium), market)
        assert (result.vol, result.message) == expected


@pytest.mark.parametrize("premium", [35.0, 38.0, 40.0, 150.0])
def test_european_bounds_unchanged(premium):
    """Put K=140, T=1 año: los límites europeos (descontados) siguen igual."""
    market = make_market(days=365, vol=0.20, underlying="Índice")
    result = implied_vol(option_leg("put", 140.0, premium), market)
    expected = stage_a_reference("put", market, 140.0, premium)
    assert (result.vol, result.message) == expected



# --- Guarda de vega casi nula (añadido aprobado por el usuario, 20-11-26) -----
#
# Cuando el precio del árbol casi no cambia con σ alrededor de la solución
# (vega < AMERICAN_MIN_VEGA por unidad de σ), brentq encuentra "una" σ que
# reproduce la prima, pero podría ser casi cualquier otra: la IV no es
# identificable y se devuelve el mensaje en lugar del número.

# Casos hallados con un barrido (S=100, r=4 %, q=1 %): calls muy ITM a 1 día,
# vega en la solución ≈ 1e-10 (la σ que encontraba brentq estaba muy lejos
# de la σ usada para la prima: 0,31 / 0,47 / 0,66 en lugar de 0,25).
NEAR_ZERO_VEGA_CASES = [
    ("call", 90.0, 0.25, 1),
    ("call", 85.0, 0.25, 1),
    ("call", 80.0, 0.25, 1),
]


@pytest.mark.parametrize("kind,strike,sigma,days", NEAR_ZERO_VEGA_CASES)
def test_near_zero_vega_is_not_identifiable(kind, strike, sigma, days):
    market = make_market(days=days, vol=sigma)
    premium = tree_price(kind, market, strike, sigma)
    # La prima sí está (por poco) por encima del intrínseco: no la atrapa la
    # comprobación de límites, solo la guarda de vega.
    assert above_intrinsic(premium, intrinsic(kind, SPOT, strike))
    result = implied_vol(option_leg(kind, strike, premium), market)
    check_result_shape(result)
    assert result.vol is None
    assert result.message == MSG_AMERICAN_NOT_IDENTIFIABLE


def test_min_vega_threshold_value():
    assert AMERICAN_MIN_VEGA == 1e-6


@pytest.mark.parametrize("kind,strike,sigma,days", [
    ("put", 100.0, 0.25, 182.5),
    ("call", 100.0, 0.25, 45),
    ("put", 110.0, 0.60, 365),
    ("call", 110.0, 0.10, 45),
    ("put", 90.0, 0.25, 45),
])
def test_normal_round_trip_still_returns_sigma(kind, strike, sigma, days):
    market = make_market(days=days, vol=sigma)
    premium = tree_price(kind, market, strike, sigma)
    result = implied_vol(option_leg(kind, strike, premium), market)
    assert result.message is None
    assert result.vol == pytest.approx(sigma, abs=SIGMA_TOL)


@pytest.mark.parametrize("underlying,pricing_model", [
    ("Acción", "black_scholes"),
    ("Índice", "binomial"),
])
def test_european_branch_has_no_vega_guard(underlying, pricing_model):
    """La rama europea no cambia: el mismo caso de vega casi nula da una σ.

    Valor de la Etapa A medido con bs_price: 0,27348052056262784.
    """
    market = make_market(days=1, vol=0.25, underlying=underlying,
                         pricing_model=pricing_model)
    premium = bs_price("call", SPOT, 90.0, RATE, Q, 0.25, market.T)
    result = implied_vol(option_leg("call", 90.0, premium), market)
    assert result.message is None
    assert result.vol == pytest.approx(0.27348052056262784, abs=1e-9)


# --- Regla de precisión (añadido aprobado por el usuario, 20-11-26) -----------
#
# Las primas se cotizan en céntimos: medio céntimo de redondeo no debe poder
# mover la σ más de 5 puntos. Si vega < 0,005 / 0,05 = 0,1 por unidad de σ,
# la IV americana se declara no identificable.


def test_precision_rule_constants():
    assert PREMIUM_PRECISION == 0.005
    assert MAX_SIGMA_UNCERTAINTY == 0.05


def test_cent_rounded_deep_itm_call_is_not_identifiable():
    """Call S=100, K=80, 1 día, prima 20,01 (redondeada al céntimo).

    Antes de la regla daba una σ enorme (≈ 1,4–1,5) con vega ≈ 0,01 por
    unidad de σ: medio céntimo movía σ ≈ 0,5. Ahora devuelve el mensaje.
    """
    market = make_market(days=1, vol=0.25, q=0.0)
    result = implied_vol(option_leg("call", 80.0, 20.01), market)
    check_result_shape(result)
    assert result.vol is None
    assert result.message == MSG_AMERICAN_NOT_IDENTIFIABLE


# Casos de la malla siguiente que la regla marca (medido): σ = 10 % a 30 días
# con strikes a ±10 % del spot. Primas < 0,001 o vega ≈ 0,01 por unidad de σ:
# medio céntimo movería σ entre 0,07 y 0,44. Están mal condicionados de verdad.
PRECISION_FLAGGED = {
    ("call", 90.0, 0.10, 30),
    ("put", 90.0, 0.10, 30),
    ("call", 110.0, 0.10, 30),
}


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("strike", (90.0, 100.0, 110.0))
@pytest.mark.parametrize("sigma", (0.10, 0.25, 0.60))
@pytest.mark.parametrize("days", (30, 90, 365))
def test_precision_rule_keeps_normal_round_trips(kind, strike, sigma, days):
    """ATM/OTM/ITM moderado, 30–365 días, σ 10–60 %: la IV sigue saliendo.

    Excepción medida y explicada: PRECISION_FLAGGED (mal condicionados).
    """
    market = make_market(days=days, vol=sigma)
    premium = tree_price(kind, market, strike, sigma)
    if not above_intrinsic(premium, intrinsic(kind, SPOT, strike)):
        pytest.skip("Prima en el intrínseco: precio plano en σ (otro caso).")
    result = implied_vol(option_leg(kind, strike, premium), market)
    vega_per_unit = option_greeks(kind, market, strike)["vega"] * 100
    if (kind, strike, sigma, days) in PRECISION_FLAGGED:
        assert vega_per_unit * MAX_SIGMA_UNCERTAINTY < PREMIUM_PRECISION
        assert result.vol is None
        assert result.message == MSG_AMERICAN_NOT_IDENTIFIABLE
        return
    assert result.message is None
    assert result.vol == pytest.approx(sigma, abs=SIGMA_TOL)
