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
from opciones.pricing import OPTION_KINDS, bs_price, option_price, uses_binomial

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

# Mensajes propios del modelo americano (árbol binomial, Acción/ETF).
MSG_AMERICAN_NOT_IDENTIFIABLE = (
    "No se puede identificar la IV: con esta prima el precio del modelo no "
    "depende de la volatilidad (ejercicio anticipado óptimo)."
)
MSG_AMERICAN_BELOW_INTRINSIC = (
    "La prima está por debajo del valor intrínseco (lo que se cobra ejerciendo hoy): "
    "una opción americana no puede valer menos, no existe volatilidad implícita."
)

# Precisión del buscador en la rama americana: cada evaluación es un árbol
# de 500/501 pasos (caro), así que no pedimos 1e-14 como con Black-Scholes.
AMERICAN_XTOL = 1e-8

# Vega mínima (por unidad de σ, es decir, por 100 puntos de volatilidad) en
# la σ encontrada para aceptarla. Por debajo, el precio casi no se mueve con
# σ y la σ de brentq es una de muchas posibles (ver _american_vega).
AMERICAN_MIN_VEGA = 1e-6
# Desplazamiento de σ para medir esa vega con una diferencia central.
AMERICAN_VEGA_BUMP = 1e-4


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

    # Acción/ETF con el modelo binomial: la IV se calcula con el árbol americano,
    # el mismo modelo que da la prima. Índice o "black_scholes": sigue igual.
    if uses_binomial(market):
        return _american_implied_vol(leg.kind, leg.strike, premium, market)

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


# --- Rama americana (árbol binomial) ------------------------------------------


def _american_bounds(kind: str, market: Market, strike: float) -> tuple[float, float]:
    """Límites (inferior, superior) de la prima de una opción AMERICANA.

    - Inferior = valor intrínseco SIN descontar: máx(S − K, 0) en la call y
      máx(K − S, 0) en la put. ¿Por qué sin descontar? Porque una opción
      americana se puede ejercer HOY: si valiera menos que el intrínseco,
      comprarla y ejercerla al momento daría dinero gratis. En la europea
      solo se cobra al vencimiento, por eso allí el límite va descontado.
    - Superior = S para la call (nunca vale más que la acción) y K para la
      put (lo máximo que se puede cobrar es el strike). El árbol nunca
      supera esos valores.
    """
    if kind == "call":
        return max(market.spot - strike, 0.0), market.spot
    return max(strike - market.spot, 0.0), strike


def _american_implied_vol(kind: str, strike: float, premium: float,
                          market: Market) -> IVResult:
    """IV con el árbol americano (500/501 pasos promediados, vía `option_price`).

    Orden: límites americanos -> identificabilidad -> buscador (brentq) ->
    guarda de vega casi nula en la σ encontrada.

    ¿Por qué algunas primas no tienen IV identificable? En una opción
    americana muy dentro del dinero lo óptimo es ejercer ya, y entonces su
    precio es exactamente el intrínseco para muchas σ distintas: el precio
    "no se mueve" con σ. Si la prima está en ese tramo plano, cualquier σ
    pequeña la explica igual de bien, así que no hay UNA respuesta: lo
    decimos con un mensaje en vez de inventar un número. Lo mismo pasa si
    ni siquiera con la σ mínima el modelo baja hasta la prima (p. ej. una
    call ITM cuyo valor sin volatilidad, S − K·e^(−rT), ya supera la prima).
    """
    lower, upper = _american_bounds(kind, market, strike)
    # Tolerancia pequeña para no confundir ruido de redondeo con un precio real.
    tolerance = lower * 1e-6 + 1e-9
    if premium < lower - tolerance:
        return IVResult(None, MSG_AMERICAN_BELOW_INTRINSIC)
    if premium >= upper:
        return IVResult(None, MSG_ABOVE_UPPER_BOUND)
    # Prima (casi) igual al intrínseco: precio plano en σ.
    if premium <= lower + tolerance:
        return IVResult(None, MSG_AMERICAN_NOT_IDENTIFIABLE)

    def gap(sigma: float) -> float:
        """Precio del árbol con σ menos la prima: buscamos el 0."""
        return float(option_price(kind, market, strike, sigma=sigma)) - premium

    try:
        gap_low = gap(VOL_LOW)
        gap_high = gap(VOL_HIGH)
        if not (math.isfinite(gap_low) and math.isfinite(gap_high)):
            return IVResult(None, MSG_SOLVER_FAILED)
        # Con la σ mínima el modelo ya vale la prima o más: no hay tramo
        # donde σ explique la prima (precio plano / dominado por el ejercicio).
        if gap_low >= 0:
            return IVResult(None, MSG_AMERICAN_NOT_IDENTIFIABLE)
        # Ni con σ = 1000 % se alcanza la prima: fuera del intervalo de búsqueda.
        if gap_high < 0:
            return IVResult(None, MSG_SOLVER_FAILED)
        vol = brentq(gap, VOL_LOW, VOL_HIGH, xtol=AMERICAN_XTOL)
    except (ValueError, RuntimeError, ArithmeticError):
        return IVResult(None, MSG_SOLVER_FAILED)
    if not math.isfinite(vol):
        return IVResult(None, MSG_SOLVER_FAILED)

    # Guarda de vega casi nula (añadida el 20-11-26, aprobada por el usuario).
    # ¿Por qué? Con una call muy ITM a 1 día, por ejemplo, el precio del árbol
    # casi no depende de σ: brentq encuentra una σ que reproduce la prima, pero
    # cualquier otra σ también lo haría (medido: σ de 0,31 a 0,66 para una
    # prima calculada con 0,25). En las pruebas, todas las σ erróneas tenían
    # vega ≤ 7e-11 y todas las correctas, ≥ 8,6e-9: con vega < 1e-6 decimos
    # que la IV no es identificable en vez de mostrar un número engañoso.
    try:
        vega = _american_vega(kind, strike, vol, market)
    except (ValueError, RuntimeError, ArithmeticError):
        return IVResult(None, MSG_SOLVER_FAILED)
    if not math.isfinite(vega):
        return IVResult(None, MSG_SOLVER_FAILED)
    if vega < AMERICAN_MIN_VEGA:
        return IVResult(None, MSG_AMERICAN_NOT_IDENTIFIABLE)
    return IVResult(float(vol), None)


def _american_vega(kind: str, strike: float, sigma: float, market: Market) -> float:
    """Vega del árbol en σ, por unidad de σ (diferencia central).

    vega ≈ (precio(σ + h) − precio(σ − h)) / (2·h), con el mismo precio
    promediado (500/501 pasos) que usa el buscador. Si σ es muy pequeña,
    h se reduce a σ/2 para no pasar a una volatilidad negativa.
    """
    bump = min(AMERICAN_VEGA_BUMP, sigma / 2)
    price_up = float(option_price(kind, market, strike, sigma=sigma + bump))
    price_down = float(option_price(kind, market, strike, sigma=sigma - bump))
    return (price_up - price_down) / (2 * bump)
