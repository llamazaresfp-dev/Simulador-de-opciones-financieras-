"""Precio de opciones con el árbol binomial de Cox-Ross-Rubinstein (CRR).

Idea del árbol (en palabras sencillas):
- Partimos el tiempo hasta el vencimiento T en N pasos de duración dt = T/N.
- En cada paso el precio de la acción solo puede subir (multiplicar por u)
  o bajar (multiplicar por d = 1/u), con u = e^(sigma·raíz(dt)).
- p = (e^((r − q)·dt) − d) / (u − d) es la probabilidad "neutral al riesgo"
  de subir: la que hace que el precio esperado crezca al tipo r − q.
- En el último paso (vencimiento) la opción vale su valor intrínseco.
- Inducción hacia atrás: vamos del vencimiento hacia hoy; el valor de un
  nodo es el valor esperado de sus dos hijos, descontado un paso:
      V = e^(−r·dt) · (p·V_sube + (1 − p)·V_baja)
- Ejercicio anticipado (opción americana): en cada nodo comparamos
  "esperar" (la fórmula anterior) con "ejercer ya" (el intrínseco del nodo)
  y nos quedamos con el mayor.

Por qué promediamos N y N+1 pasos: el precio del árbol oscila alrededor del
valor verdadero según N sea par o impar (el strike cae en sitios distintos
de la malla). La media de dos árboles consecutivos cancela gran parte de
esa oscilación y da un precio más estable con el mismo coste.

Este módulo es puro: solo usa numpy y math, no importa `opciones.pricing`
(así no hay importaciones circulares) ni Streamlit.
"""

import math

import numpy as np

from opciones.models import DAYS_PER_YEAR

OPTION_KINDS = ("call", "put")

# Pasos del árbol para una prima (se promedian N y N+1).
CRR_PRICE_STEPS = 500

# Pasos del árbol para la curva "hoy" (muchos spots a la vez; más barato).
CRR_GRID_STEPS = 200

# Con vencimientos muy cortos no hacen falta tantos pasos:
# como máximo 50 pasos por día, y nunca menos de 2.
STEPS_PER_DAY = 50
MIN_STEPS = 2

# Tope del exponente en e^x para que u^N no se desborde (e^709 ≈ máximo float).
_MAX_EXPONENT = 600.0

# Si u − d es menor que esto, el árbol no tiene "anchura" (sigma·raíz(dt) es
# prácticamente 0) y usamos el límite determinista.
_MIN_SPREAD = 1e-12


def _check_kind(kind: str) -> None:
    """Solo sabemos valorar calls y puts."""
    if kind not in OPTION_KINDS:
        raise ValueError(f"Tipo de opción no válido: {kind!r}")


def _intrinsic(kind: str, S, K: float) -> np.ndarray:
    """Valor intrínseco (lo que vale ejercer ahora mismo)."""
    if kind == "call":
        return np.maximum(S - K, 0.0)
    return np.maximum(K - S, 0.0)


def _deterministic_value(kind: str, S: np.ndarray, K: float, r: float,
                         q: float, T: float, american: bool) -> np.ndarray:
    """Valor sin volatilidad: límite "forward" descontado.

    Sin incertidumbre la call vale max(S·e^(−qT) − K·e^(−rT), 0) y la put
    max(K·e^(−rT) − S·e^(−qT), 0). Si es americana, además puede ejercerse
    hoy, así que nunca vale menos que el intrínseco.
    """
    stock_pv = S * math.exp(-q * T)
    strike_pv = K * math.exp(-r * T)
    if kind == "call":
        forward = np.maximum(stock_pv - strike_pv, 0.0)
    else:
        forward = np.maximum(strike_pv - stock_pv, 0.0)
    if american:
        return np.maximum(forward, _intrinsic(kind, S, K))
    return forward


def _upper_bound(kind: str, S: np.ndarray, K: float) -> np.ndarray:
    """Cota superior de seguridad: una call nunca vale más que S; una put, más que K."""
    if kind == "call":
        return S
    return np.full_like(S, K)


def _effective_steps(N: int, T: float) -> int:
    """Pasos a usar: N, salvo vencimientos muy cortos (máximo 50 por día).

    Con 1 día, 500 pasos no aportan precisión y solo cuestan tiempo.
    """
    days = T * DAYS_PER_YEAR
    cap = max(MIN_STEPS, math.ceil(days * STEPS_PER_DAY))
    return max(MIN_STEPS, min(int(N), cap))


def _crr_values(kind: str, S_array, K: float, r: float, q: float,
                sigma: float, T: float, N: int, american: bool) -> np.ndarray:
    """Valor de la opción con un solo árbol CRR de N pasos (sin promediar).

    Vectorizado: S_array puede tener muchos spots y se calculan todos a la
    vez (una fila de la matriz por spot, una columna por nodo del árbol).
    Devuelve siempre un array de numpy del mismo tamaño que S_array.

    Guardas para no devolver nunca NaN ni infinitos:
    - T <= 0: la opción ya vence, vale su intrínseco.
    - sigma <= 0 (o árbol sin anchura): límite determinista.
    - p fuera de [0, 1] (volatilidad muy baja frente a r − q): límite determinista.
    - exponentes enormes: se recortan para que u^N no se desborde.
    """
    _check_kind(kind)
    S = np.atleast_1d(np.asarray(S_array, dtype=float))

    if T <= 0:
        return _intrinsic(kind, S, K)
    if sigma <= 0:
        return _deterministic_value(kind, S, K, r, q, T, american)

    N = max(1, int(N))
    dt = T / N
    log_u = sigma * math.sqrt(dt)
    u = math.exp(min(log_u, _MAX_EXPONENT))
    d = 1.0 / u
    if u - d < _MIN_SPREAD:
        return _deterministic_value(kind, S, K, r, q, T, american)

    # Probabilidad neutral al riesgo de subir (con dividendo q).
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if p < 0.0 or p > 1.0:
        # Volatilidad tan baja frente a r − q que el árbol no puede seguir
        # la deriva (p no sería una probabilidad). Recortar p daría precios
        # muy erróneos, así que usamos el límite sin volatilidad, que es
        # justo el caso al que nos acercamos.
        return _deterministic_value(kind, S, K, r, q, T, american)
    disc = math.exp(-r * dt)

    # Potencias de u precalculadas una sola vez: powers[k + N] = u^k,
    # para k = −N..N (recortando el exponente para no desbordar).
    exponents = np.arange(-N, N + 1) * log_u
    powers = np.exp(np.clip(exponents, -_MAX_EXPONENT, _MAX_EXPONENT))

    with np.errstate(over="ignore", invalid="ignore"):
        # Hojas (vencimiento): el nodo j tiene precio S·u^(2j − N), j = 0..N.
        leaf_prices = S[:, None] * powers[0::2][None, :]
        values = _intrinsic(kind, leaf_prices, K)

        # Inducción hacia atrás: del paso N−1 hasta hoy (paso 0).
        for i in range(N - 1, -1, -1):
            # Columna j: hijo "baja" = j, hijo "sube" = j + 1.
            values = disc * (p * values[:, 1:i + 2] + (1.0 - p) * values[:, 0:i + 1])
            if american:
                # Precios del paso i: S·u^(2j − i), j = 0..i.
                node_prices = S[:, None] * powers[N - i:N + i + 1:2][None, :]
                values = np.maximum(values, _intrinsic(kind, node_prices, K))

    result = values[:, 0]
    # Red de seguridad: siempre finito y dentro de [0, cota superior].
    result = np.nan_to_num(result, nan=0.0)
    return np.clip(result, 0.0, _upper_bound(kind, S, K))


def _averaged_values(kind: str, S, K: float, r: float, q: float,
                     sigma: float, T: float, steps: int, american: bool) -> np.ndarray:
    """Media de los árboles de N y N+1 pasos (amortigua la oscilación par/impar)."""
    N = _effective_steps(steps, T)
    first = _crr_values(kind, S, K, r, q, sigma, T, N, american)
    second = _crr_values(kind, S, K, r, q, sigma, T, N + 1, american)
    return 0.5 * (first + second)


def crr_price(kind: str, S: float, K: float, r: float, q: float, sigma: float,
              T: float, steps: int = CRR_PRICE_STEPS, american: bool = True) -> float:
    """Prima por acción con el árbol CRR (media de 500 y 501 pasos por defecto).

    - kind: "call" o "put"; S: spot (un número).
    - american=True permite el ejercicio anticipado en cada nodo.
    Nunca devuelve NaN: ver las guardas de `_crr_values`.
    """
    values = _averaged_values(kind, [S], K, r, q, sigma, T, steps, american)
    return float(values[0])


def crr_price_grid(kind: str, S_array, K: float, r: float, q: float, sigma: float,
                   T: float, steps: int = CRR_GRID_STEPS, american: bool = True) -> np.ndarray:
    """Precios CRR para muchos spots a la vez (curva "hoy").

    Media de 200 y 201 pasos por defecto: suficiente para dibujar la curva
    y unas 2-3 veces más rápido que 500/501. Si es americana, el resultado
    nunca baja del intrínseco (se puede ejercer hoy). Devuelve un array.
    """
    S = np.atleast_1d(np.asarray(S_array, dtype=float))
    values = _averaged_values(kind, S, K, r, q, sigma, T, steps, american)
    if american:
        values = np.maximum(values, _intrinsic(kind, S, K))
    return values
