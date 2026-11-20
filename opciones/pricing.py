"""Precios y griegas de opciones europeas con Black-Scholes (con dividendo q).

Notación:
- S: precio del subyacente (número o array de numpy).
- K: strike (precio de ejercicio).
- r: tipo de interés libre de riesgo anual (fracción).
- q: rentabilidad por dividendo anual (fracción).
- sigma: volatilidad anual (fracción).
- T: tiempo hasta el vencimiento en años.

Black-Scholes es exacto para opciones europeas (índices). Para acciones
y ETF (americanas) es solo una aproximación; por eso este módulo también
tiene el "despachador" (`uses_binomial`, `option_price`), que elige entre
Black-Scholes y el árbol binomial americano de `opciones.binomial`.
"""

import math

import numpy as np
from scipy.stats import norm

from opciones.binomial import crr_greeks, crr_price, crr_price_grid
from opciones.models import DAYS_PER_YEAR, PRICING_BINOMIAL, Market

# Subyacentes cuyas opciones son americanas (se pueden ejercer antes).
AMERICAN_UNDERLYINGS = ("Acción", "ETF")

OPTION_KINDS = ("call", "put")


def _check_kind(kind: str) -> None:
    """Solo sabemos valorar calls y puts."""
    if kind not in OPTION_KINDS:
        raise ValueError(f"Tipo de opción no válido: {kind!r}")


def _to_output(values: np.ndarray, S):
    """Si S era un número, devolvemos un float; si era un array, un array."""
    if np.ndim(S) == 0:
        return float(values)
    return values


def _d1_d2(S, K, r, q, sigma, T):
    """Calcula d1 y d2, las dos cantidades centrales de Black-Scholes.

    - d1 mide (en desviaciones típicas) lo lejos que está el precio
      esperado del strike; N(d1) se usa para la delta.
    - d2 = d1 - sigma*raíz(T); N(d2) es la probabilidad (neutral al
      riesgo) de que la opción call termine dentro del dinero.
    """
    # Con S = 0, log(0) = -infinito: es correcto (d1 = d2 = -inf),
    # así que silenciamos el aviso de numpy.
    with np.errstate(divide="ignore"):
        log_ratio = np.log(S / K)
    sqrt_T = math.sqrt(T)
    d1 = (log_ratio + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2


def bs_price(kind: str, S, K: float, r: float, q: float, sigma: float, T: float):
    """Precio Black-Scholes de una call o put (por acción, sin multiplicar por 100).

    Casos especiales (para no devolver nunca NaN):
    - T <= 0: la opción ya vence, vale su valor intrínseco.
    - sigma <= 0: sin incertidumbre el precio es el valor descontado
      del "forward": max(S·e^(−qT) − K·e^(−rT), 0) para la call.
    """
    _check_kind(kind)
    S_arr = np.asarray(S, dtype=float)

    if T <= 0:
        # Al vencimiento: call = max(S − K, 0); put = max(K − S, 0).
        if kind == "call":
            values = np.maximum(S_arr - K, 0.0)
        else:
            values = np.maximum(K - S_arr, 0.0)
        return _to_output(values, S)

    # Valor actual de la acción (descontando dividendos) y del strike.
    stock_pv = S_arr * math.exp(-q * T)
    strike_pv = K * math.exp(-r * T)

    if sigma <= 0:
        # Límite determinista: no hay valor temporal por volatilidad.
        if kind == "call":
            values = np.maximum(stock_pv - strike_pv, 0.0)
        else:
            values = np.maximum(strike_pv - stock_pv, 0.0)
        return _to_output(values, S)

    d1, d2 = _d1_d2(S_arr, K, r, q, sigma, T)
    if kind == "call":
        values = stock_pv * norm.cdf(d1) - strike_pv * norm.cdf(d2)
    else:
        values = strike_pv * norm.cdf(-d2) - stock_pv * norm.cdf(-d1)
    # Redondeos minúsculos podrían dar -1e-17: el precio nunca es negativo.
    values = np.maximum(values, 0.0)
    return _to_output(values, S)


def bs_greeks(kind: str, S: float, K: float, r: float, q: float, sigma: float, T: float) -> dict:
    """Griegas Black-Scholes de UNA opción (por acción), en unidades prácticas.

    Devuelve un diccionario con:
    - delta: cuánto cambia el precio si S sube 1 USD.
    - gamma: cuánto cambia la delta si S sube 1 USD.
    - theta: cuánto cambia el precio en 1 día natural (normalmente negativo).
    - vega: cuánto cambia el precio si la volatilidad sube 1 punto (1 %).
    - rho: cuánto cambia el precio si el tipo de interés sube 1 punto (1 %).

    Con T <= 0 o sigma <= 0 las griegas no están definidas: lanzamos
    ValueError y la interfaz muestra "—".
    """
    _check_kind(kind)
    if T <= 0:
        raise ValueError("Las griegas no están definidas al vencimiento (T <= 0).")
    if sigma <= 0:
        raise ValueError("Las griegas no están definidas con volatilidad <= 0.")

    d1, d2 = _d1_d2(float(S), K, r, q, sigma, T)
    sqrt_T = math.sqrt(T)
    disc_q = math.exp(-q * T)  # descuento por dividendo
    disc_r = math.exp(-r * T)  # descuento por tipo de interés
    density = norm.pdf(d1)     # campana normal evaluada en d1

    # Gamma y vega son iguales para call y put.
    gamma = disc_q * density / (S * sigma * sqrt_T)
    vega = S * disc_q * density * sqrt_T

    # Parte de theta común a call y put: pérdida de valor temporal.
    theta_common = -S * disc_q * density * sigma / (2 * sqrt_T)

    if kind == "call":
        delta = disc_q * norm.cdf(d1)
        theta = theta_common - r * K * disc_r * norm.cdf(d2) + q * S * disc_q * norm.cdf(d1)
        rho = K * T * disc_r * norm.cdf(d2)
    else:
        delta = disc_q * (norm.cdf(d1) - 1)
        theta = theta_common + r * K * disc_r * norm.cdf(-d2) - q * S * disc_q * norm.cdf(-d1)
        rho = -K * T * disc_r * norm.cdf(-d2)

    # Pasamos a unidades prácticas: theta por día, vega y rho por punto.
    return {
        "delta": float(delta),
        "gamma": float(gamma),
        "theta": float(theta / DAYS_PER_YEAR),
        "vega": float(vega / 100),
        "rho": float(rho / 100),
    }


def uses_binomial(market: Market) -> bool:
    """¿Hay que valorar con el árbol binomial americano?

    Este es el ÚNICO sitio que decide el modelo, para que primas, curva
    "hoy", griegas e IV usen siempre el mismo criterio.
    - Acción/ETF: sus opciones son americanas; usamos el árbol si el
      ajuste `pricing_model` es "binomial" (el valor por defecto).
    - Índice: siempre Black-Scholes. Las opciones sobre índices (SPX,
      NDX, RUT) son europeas, y para ellas Black-Scholes es exacto.
    Cualquier otro valor (p. ej. un modelo desconocido) usa Black-Scholes.
    """
    return (market.underlying in AMERICAN_UNDERLYINGS
            and market.pricing_model == PRICING_BINOMIAL)


def option_price(kind: str, market: Market, strike: float, S=None, sigma=None):
    """Precio por acción de una call o put con el modelo activo del mercado.

    Despachador: en vez de llamar a `bs_price` en cada sitio, todo el motor
    pasa por aquí, y así cambiar de modelo es cambiar un solo ajuste.
    - S: spot (número o array); por defecto `market.spot`.
    - sigma: volatilidad; por defecto `market.vol`.
    - El tiempo es siempre `market.T` (con T = 0 ambos modelos dan el
      valor intrínseco).
    Con binomial: un número usa `crr_price` (500/501 pasos, preciso) y un
    array usa `crr_price_grid` (200/201 pasos, más rápido para la curva).
    Devuelve un float o un array, igual que `bs_price`.
    """
    _check_kind(kind)
    if S is None:
        S = market.spot
    if sigma is None:
        sigma = market.vol
    if not uses_binomial(market):
        return bs_price(kind, S, strike, market.rate, market.q, sigma, market.T)
    if np.ndim(S) == 0:
        return crr_price(kind, float(S), strike, market.rate, market.q, sigma, market.T)
    return crr_price_grid(kind, S, strike, market.rate, market.q, sigma, market.T)


def option_greeks(kind: str, market: Market, strike: float) -> dict:
    """Griegas por acción de una call o put con el modelo activo del mercado.

    Despachador de griegas (como `option_price` para el precio):
    - Acción/ETF con "binomial": griegas del árbol americano (`crr_greeks`).
    - Índice o "black_scholes": `bs_greeks`, idénticas a la Etapa A.
    Mismas claves y unidades en ambos casos (theta por día; vega y rho
    por 1 punto). Con T <= 0 o vol <= 0 lanza ValueError.
    """
    _check_kind(kind)
    if not uses_binomial(market):
        return bs_greeks(kind, market.spot, strike, market.rate, market.q, market.vol, market.T)
    return crr_greeks(kind, market.spot, strike, market.rate, market.q, market.vol, market.T)


def default_premium(kind: str, market: Market, strike) -> float:
    """Prima sugerida para una pata nueva: precio del modelo activo con los datos globales.

    Binomial americano para Acción/ETF por defecto; Black-Scholes para
    Índice o si se elige "black_scholes" (ver `option_price`).

    Devuelve 0.0 si el cálculo no es posible (por ejemplo, acciones,
    strike vacío o no positivo, o datos de mercado no numéricos).
    """
    if kind not in OPTION_KINDS:
        return 0.0
    if strike is None or not strike > 0:
        return 0.0
    try:
        price = option_price(kind, market, strike)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(price):
        return 0.0
    return price
