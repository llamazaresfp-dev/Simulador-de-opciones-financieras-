"""Precios y griegas de opciones europeas con Black-Scholes (con dividendo q).

Notación:
- S: precio del subyacente (número o array de numpy).
- K: strike (precio de ejercicio).
- r: tipo de interés libre de riesgo anual (fracción).
- q: rentabilidad por dividendo anual (fracción).
- sigma: volatilidad anual (fracción).
- T: tiempo hasta el vencimiento en años.

Black-Scholes es exacto para opciones europeas (índices). Para acciones
y ETF (americanas) es solo una aproximación.
"""

import math

import numpy as np
from scipy.stats import norm

from opciones.models import DAYS_PER_YEAR, Market

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


def default_premium(kind: str, market: Market, strike) -> float:
    """Prima sugerida para una pata nueva: precio Black-Scholes con los datos globales.

    Devuelve 0.0 si el cálculo no es posible (por ejemplo, acciones,
    strike vacío o no positivo, o datos de mercado no numéricos).
    """
    if kind not in OPTION_KINDS:
        return 0.0
    if strike is None or not strike > 0:
        return 0.0
    try:
        price = bs_price(kind, market.spot, strike, market.rate, market.q, market.vol, market.T)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(price):
        return 0.0
    return price
