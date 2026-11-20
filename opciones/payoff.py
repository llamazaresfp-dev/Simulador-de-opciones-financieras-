"""P&L (ganancia o pérdida) de cada pata y de la estrategia completa.

Fórmula de una pata (AC5):
    P&L = side × quantity × multiplier × (valor − price) − comisiones

- "Al vencimiento": el valor de la opción es su valor intrínseco.
- "Hoy": el valor de la opción es su precio Black-Scholes.
La estrategia es simplemente la suma de sus patas.

Todas las funciones de P&L aceptan S como número o como array de numpy
(así calculamos la curva entera de una vez).
"""

import numpy as np

from opciones.commissions import close_fee_expiry, close_fee_today, open_fee
from opciones.models import CommissionSettings, Leg, Market
from opciones.pricing import bs_greeks, bs_price

GREEK_NAMES = ("delta", "gamma", "theta", "vega", "rho")

# Puntos de la parte uniforme de la rejilla de precios.
GRID_POINTS = 401

# Distancia minúscula a cada lado del strike: ahí la comisión de cierre
# "salta", y queremos que el gráfico dibuje el escalón casi vertical.
STRIKE_EPS = 1e-9


def _to_output(values: np.ndarray, S):
    """Si S era un número, devolvemos un float; si era un array, un array."""
    if np.ndim(S) == 0:
        return float(values)
    return values


def _gross_pnl(leg: Leg, value) -> np.ndarray:
    """P&L sin comisiones: lado × cantidad × multiplicador × (valor − precio)."""
    return leg.side * leg.quantity * leg.multiplier * (value - leg.price)


def leg_pnl_expiry(leg: Leg, market: Market, settings: CommissionSettings, S):
    """P&L de una pata al vencimiento, con comisiones restadas."""
    S_arr = np.asarray(S, dtype=float)
    if leg.kind == "stock":
        value = S_arr
    else:
        # T = 0: bs_price devuelve el valor intrínseco.
        value = bs_price(leg.kind, S_arr, leg.strike, market.rate, market.q, market.vol, 0.0)
    fees = open_fee(leg, market, settings) + close_fee_expiry(leg, S_arr, market, settings)
    return _to_output(_gross_pnl(leg, value) - fees, S)


def leg_pnl_today(leg: Leg, market: Market, settings: CommissionSettings, S):
    """P&L de una pata si cerramos hoy, con comisiones de apertura y cierre.

    Con días = 0, bs_price devuelve el valor intrínseco (decisión 13).
    """
    S_arr = np.asarray(S, dtype=float)
    if leg.kind == "stock":
        value = S_arr
    else:
        value = bs_price(leg.kind, S_arr, leg.strike, market.rate, market.q, market.vol, market.T)
    fees = open_fee(leg, market, settings) + close_fee_today(leg, market, settings)
    return _to_output(_gross_pnl(leg, value) - fees, S)


def pnl_expiry(legs: list[Leg], market: Market, settings: CommissionSettings, S):
    """P&L de la estrategia al vencimiento: suma de las patas."""
    total = np.zeros_like(np.asarray(S, dtype=float))
    for leg in legs:
        total = total + leg_pnl_expiry(leg, market, settings, S)
    return _to_output(total, S)


def pnl_today(legs: list[Leg], market: Market, settings: CommissionSettings, S):
    """P&L de la estrategia si cerramos hoy: suma de las patas."""
    total = np.zeros_like(np.asarray(S, dtype=float))
    for leg in legs:
        total = total + leg_pnl_today(leg, market, settings, S)
    return _to_output(total, S)


def position_greeks(legs: list[Leg], market: Market) -> dict:
    """Griegas de la posición completa al precio spot actual.

    Griega de una pata = griega por acción × multiplicador × cantidad × lado.
    Una acción solo tiene delta (±cantidad); el resto de griegas es 0.
    Con días = 0 (o vol <= 0) las griegas no existen: devolvemos None
    en cada una y la interfaz muestra "—".
    """
    if market.T <= 0 or market.vol <= 0:
        return {name: None for name in GREEK_NAMES}

    totals = {name: 0.0 for name in GREEK_NAMES}
    for leg in legs:
        if leg.kind == "stock":
            totals["delta"] += leg.side * leg.quantity
            continue
        greeks = bs_greeks(
            leg.kind, market.spot, leg.strike, market.rate, market.q, market.vol, market.T
        )
        size = leg.side * leg.quantity * leg.multiplier
        for name in GREEK_NAMES:
            totals[name] += greeks[name] * size
    return totals


def price_grid(market: Market, legs: list[Leg]) -> np.ndarray:
    """Precios del subyacente donde dibujamos las curvas de P&L.

    - Base: de −30 % a +30 % del spot.
    - Si algún strike queda fuera, ampliamos el rango con un margen
      del 10 % para que se vean todos los strikes.
    - Añadimos cada strike y strike ± 1e-9: al vencimiento la comisión de
      cierre crea un salto justo en el strike, y estos puntos permiten
      dibujarlo como un escalón en vez de una rampa.
    """
    low = 0.7 * market.spot
    high = 1.3 * market.spot
    strikes = [leg.strike for leg in legs if leg.kind != "stock"]
    if strikes:
        low = min(low, 0.9 * min(strikes))
        high = max(high, 1.1 * max(strikes))
    low = max(low, 0.0)  # un precio nunca es negativo

    points = [np.linspace(low, high, GRID_POINTS)]
    for K in strikes:
        points.append(np.array([K - STRIKE_EPS, K, K + STRIKE_EPS]))
    grid = np.unique(np.concatenate(points))  # ordena y quita duplicados
    return grid[grid >= 0.0]
