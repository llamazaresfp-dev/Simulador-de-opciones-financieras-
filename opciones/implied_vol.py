"""Volatilidad implícita (IV) de una pata de opción.

¿Qué es la IV? Es la volatilidad que habría que poner en Black-Scholes
para que el modelo dé EXACTAMENTE la prima que escribiste. Es decir,
resolvemos la ecuación bs_price(σ) = prima buscando σ.

¿Por qué comprobar antes los límites sin arbitraje? Porque el precio
Black-Scholes siempre está entre dos límites (por ejemplo, una call
vale al menos su valor intrínseco descontado y como mucho el precio
descontado de la acción). Si la prima está fuera de esos límites no
existe ninguna σ que la explique. Y hay una trampa: con prima 0 muy
fuera del dinero, el buscador de raíces devolvería en silencio el
mínimo del intervalo (1e-6) como si fuera una IV real. Por eso
comprobamos primero y solo después llamamos al buscador.

La función nunca lanza excepciones: devuelve un número o un mensaje.
"""

import math
from dataclasses import dataclass

from scipy.optimize import brentq

from opciones.models import Leg, Market
from opciones.pricing import OPTION_KINDS, bs_price

# Intervalo de búsqueda de σ: de 0,0001 % a 1000 % anual.
VOL_LOW = 1e-6
VOL_HIGH = 10.0

# Mensajes en español (uno distinto para cada caso sin IV).
MSG_STOCK_LEG = "Las acciones no tienen volatilidad implícita (solo las opciones)."
MSG_NO_TIME = "Con 0 días hasta el vencimiento no se puede calcular la volatilidad implícita."
MSG_PREMIUM_NOT_POSITIVE = (
    "Con una prima de 0 o negativa no existe volatilidad implícita."
)
MSG_BELOW_LOWER_BOUND = (
    "La prima está en el límite inferior sin arbitraje o por debajo "
    "(no supera el valor intrínseco descontado): no existe volatilidad implícita."
)
MSG_ABOVE_UPPER_BOUND = (
    "La prima está en el límite superior sin arbitraje o por encima "
    "(la opción no puede valer tanto): no existe volatilidad implícita."
)
MSG_SOLVER_FAILED = (
    "No se encontró una volatilidad implícita entre 0,0001 % y 1000 % para esta prima."
)
MSG_INVALID_DATA = "Faltan datos o no son válidos para calcular la volatilidad implícita."


@dataclass
class IVResult:
    """Resultado del cálculo de la IV.

    - vol: la IV como fracción (0.25 = 25 %), o None si no existe.
    - message: explicación en español si no hay IV, o None si la hay.
    Siempre uno de los dos es None.
    """

    vol: float | None
    message: str | None


def _is_number(value) -> bool:
    """True si es un número real finito (no None, ni NaN, ni infinito, ni bool)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _no_arbitrage_bounds(kind: str, market: Market, strike: float) -> tuple[float, float]:
    """Límites (inferior, superior) que cualquier prima razonable debe cumplir.

    - call: máx(S·e^(−qT) − K·e^(−rT), 0) < C < S·e^(−qT)
    - put:  máx(K·e^(−rT) − S·e^(−qT), 0) < P < K·e^(−rT)
    """
    stock_pv = market.spot * math.exp(-market.q * market.T)
    strike_pv = strike * math.exp(-market.rate * market.T)
    if kind == "call":
        return max(stock_pv - strike_pv, 0.0), stock_pv
    return max(strike_pv - stock_pv, 0.0), strike_pv


def implied_vol(leg: Leg, market: Market) -> IVResult:
    """Calcula la volatilidad implícita de la prima de una pata de opción.

    Orden de las comprobaciones: acción -> días = 0 -> prima <= 0 ->
    límites sin arbitraje -> buscador de raíces (brentq).
    """
    if leg.kind == "stock":
        return IVResult(None, MSG_STOCK_LEG)
    if leg.kind not in OPTION_KINDS:
        return IVResult(None, MSG_INVALID_DATA)

    data = (market.days, leg.price, leg.strike, market.spot, market.rate, market.q)
    if not all(_is_number(x) for x in data):
        return IVResult(None, MSG_INVALID_DATA)

    if market.days <= 0:
        return IVResult(None, MSG_NO_TIME)
    premium = leg.price
    if premium <= 0:
        return IVResult(None, MSG_PREMIUM_NOT_POSITIVE)
    if leg.strike <= 0 or market.spot <= 0:
        return IVResult(None, MSG_INVALID_DATA)

    # Primero los límites: si la prima está fuera, no hay σ posible.
    lower, upper = _no_arbitrage_bounds(leg.kind, market, leg.strike)
    if premium <= lower:
        return IVResult(None, MSG_BELOW_LOWER_BOUND)
    if premium >= upper:
        return IVResult(None, MSG_ABOVE_UPPER_BOUND)

    def gap(sigma: float) -> float:
        """Diferencia entre el precio del modelo con σ y la prima: buscamos el 0."""
        price = bs_price(
            leg.kind, market.spot, leg.strike, market.rate, market.q, sigma, market.T
        )
        return price - premium

    # brentq busca σ en [VOL_LOW, VOL_HIGH] donde gap(σ) cambia de signo.
    try:
        vol = brentq(gap, VOL_LOW, VOL_HIGH, xtol=1e-14, rtol=1e-14)
    except (ValueError, RuntimeError):
        return IVResult(None, MSG_SOLVER_FAILED)
    return IVResult(float(vol), None)
