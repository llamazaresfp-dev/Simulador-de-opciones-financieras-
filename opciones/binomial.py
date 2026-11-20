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
from functools import lru_cache

import numpy as np

from opciones.models import DAYS_PER_YEAR, MIN_VOL

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

# Desplazamiento para vega y rho: 1 punto porcentual (0,01 como fracción).
GREEK_BUMP = 0.01

# Tamaño máximo de las cachés (ver "Cachés" más abajo). Acotadas para que
# la memoria no crezca sin límite: al llenarse se olvida lo más antiguo.
PRICE_CACHE_SIZE = 512
GREEKS_CACHE_SIZE = 256
GRID_CACHE_SIZE = 256

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


def _tree_parameters(r: float, q: float, sigma: float, T: float, N: int):
    """Parámetros de un árbol CRR de N pasos: (p, disc, powers).

    - p: probabilidad neutral al riesgo de subir (con dividendo q).
    - disc: descuento de un paso, e^(−r·dt).
    - powers: potencias de u precalculadas una sola vez: powers[k + N] = u^k,
      para k = −N..N (recortando el exponente para no desbordar).
    Devuelve None si el árbol no sirve (sin anchura, o p fuera de [0, 1]):
    entonces se usa el límite determinista.
    """
    dt = T / N
    log_u = sigma * math.sqrt(dt)
    u = math.exp(min(log_u, _MAX_EXPONENT))
    d = 1.0 / u
    if u - d < _MIN_SPREAD:
        return None

    p = (math.exp((r - q) * dt) - d) / (u - d)
    if p < 0.0 or p > 1.0:
        # Volatilidad tan baja frente a r − q que el árbol no puede seguir
        # la deriva (p no sería una probabilidad). Recortar p daría precios
        # muy erróneos, así que usamos el límite sin volatilidad, que es
        # justo el caso al que nos acercamos.
        return None
    disc = math.exp(-r * dt)

    exponents = np.arange(-N, N + 1) * log_u
    powers = np.exp(np.clip(exponents, -_MAX_EXPONENT, _MAX_EXPONENT))
    return p, disc, powers


def _leaf_values(kind: str, S: np.ndarray, K: float, N: int,
                 powers: np.ndarray) -> np.ndarray:
    """Valores al vencimiento: el nodo j tiene precio S·u^(2j − N), j = 0..N."""
    with np.errstate(over="ignore", invalid="ignore"):
        leaf_prices = S[:, None] * powers[0::2][None, :]
        return _intrinsic(kind, leaf_prices, K)


def _roll_back(kind: str, S: np.ndarray, K: float, values: np.ndarray,
               start: int, stop: int, p: float, disc: float,
               powers: np.ndarray, american: bool) -> np.ndarray:
    """Inducción hacia atrás desde el paso `start` hasta el paso `stop`.

    `values` tiene los valores del paso `start` (columna j = nodo j) y se
    devuelven los del paso `stop` (stop + 1 columnas). N, el número total
    de pasos del árbol, se deduce de powers (tiene 2N + 1 elementos).
    """
    N = (len(powers) - 1) // 2
    with np.errstate(over="ignore", invalid="ignore"):
        for i in range(start - 1, stop - 1, -1):
            # Columna j: hijo "baja" = j, hijo "sube" = j + 1.
            values = disc * (p * values[:, 1:i + 2] + (1.0 - p) * values[:, 0:i + 1])
            if american:
                # Precios del paso i: S·u^(2j − i), j = 0..i.
                node_prices = S[:, None] * powers[N - i:N + i + 1:2][None, :]
                values = np.maximum(values, _intrinsic(kind, node_prices, K))
    return values


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
    tree = _tree_parameters(r, q, sigma, T, N)
    if tree is None:
        return _deterministic_value(kind, S, K, r, q, T, american)
    p, disc, powers = tree

    values = _leaf_values(kind, S, K, N, powers)
    values = _roll_back(kind, S, K, values, N, 0, p, disc, powers, american)

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


# --- Cachés (memoización) ------------------------------------------------------
#
# ¿Por qué? Streamlit vuelve a ejecutar todo el script en cada clic, y el
# árbol es caro (cientos de pasos). Si los datos no han cambiado, el
# resultado tampoco: lo guardamos y la próxima vez lo devolvemos al momento.
#
# ¿Cómo? `functools.lru_cache` guarda los últimos resultados en un
# diccionario cuya CLAVE son los argumentos de la función. Por eso:
# - Todos los argumentos deben ser "hashables" (números, textos, bytes).
#   Un array de numpy no lo es, así que en la malla usamos sus bytes
#   (`S.tobytes()`): dos arrays con los mismos números dan la misma clave.
# - La caché es "pura": no depende de Streamlit; mismos datos, mismo número.
# - Está acotada (maxsize): al llenarse se descarta lo menos usado.
#
# Cuidado con los arrays: si devolviéramos el array guardado en la caché y
# alguien lo modificara, la caché quedaría "envenenada" para las siguientes
# llamadas. Por eso el array guardado es de solo lectura y `crr_price_grid`
# devuelve siempre una COPIA. Las griegas se guardan como tupla (inmutable)
# y se devuelve un diccionario nuevo en cada llamada.


@lru_cache(maxsize=PRICE_CACHE_SIZE)
def _cached_price(kind: str, S: float, K: float, r: float, q: float, sigma: float,
                  T: float, steps: int, american: bool) -> float:
    """Prima promediada (N y N+1 pasos) guardada en caché. Clave: todos los argumentos."""
    values = _averaged_values(kind, [S], K, r, q, sigma, T, steps, american)
    return float(values[0])


@lru_cache(maxsize=GRID_CACHE_SIZE)
def _cached_grid(kind: str, K: float, r: float, q: float, sigma: float, T: float,
                 steps: int, american: bool, S_bytes: bytes) -> np.ndarray:
    """Curva de precios guardada en caché (array de SOLO LECTURA).

    Clave: (kind, K, r, q, sigma, T, steps, american, bytes de los spots).
    """
    S = np.frombuffer(S_bytes, dtype=float)
    values = _averaged_values(kind, S, K, r, q, sigma, T, steps, american)
    if american:
        values = np.maximum(values, _intrinsic(kind, S, K))
    values.setflags(write=False)
    return values


def crr_price(kind: str, S: float, K: float, r: float, q: float, sigma: float,
              T: float, steps: int = CRR_PRICE_STEPS, american: bool = True) -> float:
    """Prima por acción con el árbol CRR (media de 500 y 501 pasos por defecto).

    - kind: "call" o "put"; S: spot (un número).
    - american=True permite el ejercicio anticipado en cada nodo.
    Nunca devuelve NaN: ver las guardas de `_crr_values`.
    El resultado se guarda en caché (ver "Cachés"): repetir la llamada con
    los mismos datos es instantáneo.
    """
    _check_kind(kind)
    return _cached_price(kind, float(S), float(K), float(r), float(q), float(sigma),
                         float(T), int(steps), bool(american))


def crr_price_grid(kind: str, S_array, K: float, r: float, q: float, sigma: float,
                   T: float, steps: int = CRR_GRID_STEPS, american: bool = True) -> np.ndarray:
    """Precios CRR para muchos spots a la vez (curva "hoy").

    Media de 200 y 201 pasos por defecto: suficiente para dibujar la curva
    y unas 2-3 veces más rápido que 500/501. Si es americana, el resultado
    nunca baja del intrínseco (se puede ejercer hoy). Devuelve un array
    nuevo (copia del guardado en caché, así puedes modificarlo sin riesgo).
    """
    _check_kind(kind)
    S = np.ascontiguousarray(np.atleast_1d(np.asarray(S_array, dtype=float)))
    values = _cached_grid(kind, float(K), float(r), float(q), float(sigma), float(T),
                          int(steps), bool(american), S.tobytes())
    return values.copy()


# --- Griegas del árbol -------------------------------------------------------


def _tree_greeks(kind: str, S: float, K: float, r: float, q: float,
                 sigma: float, T: float, N: int, american: bool):
    """Delta, gamma y theta (por año) leídos de los primeros nodos de UN árbol.

    El árbol ya calcula los valores de la opción en los pasos 1 y 2, así
    que delta, gamma y theta salen "gratis", sin volver a calcular nada:

    - Paso 1 (dos nodos): V(1,0) con precio S·d y V(1,1) con precio S·u.
      delta = (V(1,1) − V(1,0)) / (S·u − S·d): cuánto cambia el valor
      entre el nodo de arriba y el de abajo, por cada USD de diferencia.
    - Paso 2 (tres nodos): precios S·d², S (porque u·d = 1) y S·u².
      Con ellos hay dos deltas (abajo y arriba); gamma es cuánto cambia la
      delta, dividido entre la distancia media entre esos dos tramos:
      gamma = (delta_arriba − delta_abajo) / ((S·u² − S·d²) / 2).
    - Theta: el nodo central del paso 2, V(2,1), tiene el MISMO precio S
      que hoy pero 2·dt años después. Por eso
      theta = (V(2,1) − V(0,0)) / (2·dt) es la pérdida de valor por el
      paso del tiempo, por año (luego se pasa a días).

    Devuelve (delta, gamma, theta_por_año), o None si el árbol no sirve
    (p fuera de [0, 1] o sin anchura), y entonces se usan desplazamientos.
    """
    tree = _tree_parameters(r, q, sigma, T, N)
    if tree is None:
        return None
    p, disc, powers = tree
    spot = np.array([float(S)])

    values = _leaf_values(kind, spot, K, N, powers)
    level2 = _roll_back(kind, spot, K, values, N, 2, p, disc, powers, american)[0]
    level1 = _roll_back(kind, spot, K, level2[None, :], 2, 1, p, disc, powers, american)[0]
    level0 = _roll_back(kind, spot, K, level1[None, :], 1, 0, p, disc, powers, american)[0]

    u = powers[N + 1]
    d = powers[N - 1]
    u2 = powers[N + 2]
    d2 = powers[N - 2]

    delta = (level1[1] - level1[0]) / (S * u - S * d)

    delta_up = (level2[2] - level2[1]) / (S * u2 - S)
    delta_down = (level2[1] - level2[0]) / (S - S * d2)
    gamma = (delta_up - delta_down) / (0.5 * (S * u2 - S * d2))

    dt = T / N
    theta_year = (level2[1] - level0[0]) / (2.0 * dt)
    return float(delta), float(gamma), float(theta_year)


def _bumped_greeks(kind: str, S: float, K: float, r: float, q: float,
                   sigma: float, T: float, steps: int, american: bool):
    """Plan B para delta, gamma y theta si el árbol no sirve.

    Pasa con volatilidades minúsculas frente a r − q, donde el árbol usa el
    límite sin volatilidad. Movemos S un 0,1 % arriba y abajo (diferencias
    centrales) y el tiempo hasta un día hacia el vencimiento.
    """
    def price(spot, maturity):
        return float(_averaged_values(kind, [spot], K, r, q, sigma, maturity,
                                      steps, american)[0])

    h = 1e-3 * S
    up, mid, down = price(S + h, T), price(S, T), price(S - h, T)
    delta = (up - down) / (2.0 * h)
    gamma = (up - 2.0 * mid + down) / (h * h)
    time_step = min(T, 1.0 / DAYS_PER_YEAR)
    theta_year = (price(S, T - time_step) - mid) / time_step
    return delta, gamma, theta_year


def _batched_values(kind: str, S: float, K: float, q: float, T: float, N: int,
                    american: bool, scenarios) -> np.ndarray:
    """Valor de la opción (un solo spot) para VARIOS escenarios (σ, r) a la vez.

    Es el mismo árbol de `_crr_values`, pero cada FILA de la matriz es un
    escenario distinto, con su propia p, su propio descuento y sus propias
    potencias de u. Así recorremos los N pasos UNA vez para todos los
    escenarios, en lugar de una vez por escenario (el bucle de Python es lo
    caro; las cuentas con numpy de varias filas cuestan casi lo mismo).
    Las operaciones son idénticas fila a fila, así que el resultado coincide
    con llamar a `_crr_values` para cada escenario.
    """
    results = np.zeros(len(scenarios))
    rows, probs, discounts, powers_rows = [], [], [], []
    for index, (vol, rate) in enumerate(scenarios):
        tree = _tree_parameters(rate, q, vol, T, N) if vol > 0 else None
        if tree is None:
            # Árbol sin anchura o p fuera de [0, 1]: el camino normal ya
            # aplica el límite determinista.
            results[index] = _crr_values(kind, [S], K, rate, q, vol, T, N, american)[0]
            continue
        p, disc, powers = tree
        rows.append(index)
        probs.append(p)
        discounts.append(disc)
        powers_rows.append(powers)
    if not rows:
        return results

    p = np.array(probs)[:, None]
    disc = np.array(discounts)[:, None]
    powers = np.array(powers_rows)          # una fila de potencias por escenario
    with np.errstate(over="ignore", invalid="ignore"):
        values = _intrinsic(kind, S * powers[:, 0::2], K)
        for i in range(N - 1, -1, -1):
            values = disc * (p * values[:, 1:i + 2] + (1.0 - p) * values[:, 0:i + 1])
            if american:
                node_prices = S * powers[:, N - i:N + i + 1:2]
                values = np.maximum(values, _intrinsic(kind, node_prices, K))
    tree_values = np.nan_to_num(values[:, 0], nan=0.0)
    upper = S if kind == "call" else K
    results[rows] = np.clip(tree_values, 0.0, upper)
    return results


def _batched_prices(kind: str, S: float, K: float, q: float, T: float, steps: int,
                    american: bool, scenarios) -> list:
    """Precio promediado (N y N+1 pasos) de cada escenario (σ, r)."""
    N = _effective_steps(steps, T)
    first = _batched_values(kind, S, K, q, T, N, american, scenarios)
    second = _batched_values(kind, S, K, q, T, N + 1, american, scenarios)
    return [float(value) for value in 0.5 * (first + second)]


def _crr_greeks(kind: str, S: float, K: float, r: float, q: float, sigma: float,
                T: float, steps: int, american: bool) -> dict:
    """Griegas del árbol CRR (función interna; `american=False` sirve en los
    tests para comparar el árbol europeo con Black-Scholes).

    - delta, gamma y theta: de los nodos de los pasos 1 y 2 de los árboles
      de N y N+1 pasos, promediados (igual que el precio).
    - vega y rho: no salen del árbol (el árbol se construye con una sola σ
      y una sola r), así que "empujamos" σ o r un punto (0,01) hacia arriba
      y hacia abajo y volvemos a calcular el precio promediado.
      Diferencia CENTRAL: (P(+0,01) − P(−0,01)) / 2. Es más precisa que
      mover en un solo sentido porque los errores de cada lado se compensan.
      Como el desplazamiento es justo 1 punto, el resultado ya está en
      "USD por 1 punto" (las mismas unidades que `bs_greeks`).
      Si σ − 0,01 quedara por debajo de MIN_VOL, vega es unilateral:
      P(σ + 0,01) − P(σ).
    - theta se devuelve por día natural (dividido entre 365).
    """
    _check_kind(kind)
    if T <= 0:
        raise ValueError("Las griegas no están definidas al vencimiento (T <= 0).")
    if sigma <= 0:
        raise ValueError("Las griegas no están definidas con volatilidad <= 0.")

    N = _effective_steps(steps, T)
    first = _tree_greeks(kind, S, K, r, q, sigma, T, N, american)
    second = _tree_greeks(kind, S, K, r, q, sigma, T, N + 1, american)
    if first is None or second is None:
        delta, gamma, theta_year = _bumped_greeks(kind, S, K, r, q, sigma, T, steps, american)
    else:
        delta, gamma, theta_year = (0.5 * (a + b) for a, b in zip(first, second))

    # Vega y rho: los cuatro precios desplazados salen de UN solo bucle de
    # inducción por cada N (ver `_batched_prices`), no de cuatro árboles.
    one_sided = sigma - GREEK_BUMP < MIN_VOL
    vol_down = sigma if one_sided else sigma - GREEK_BUMP
    scenarios = (
        (sigma + GREEK_BUMP, r),   # σ arriba
        (vol_down, r),             # σ abajo (o σ sin mover si no cabe)
        (sigma, r + GREEK_BUMP),   # r arriba
        (sigma, r - GREEK_BUMP),   # r abajo
    )
    vol_up_price, vol_down_price, rate_up_price, rate_down_price = _batched_prices(
        kind, S, K, q, T, steps, american, scenarios)

    if one_sided:
        vega = vol_up_price - vol_down_price
    else:
        vega = (vol_up_price - vol_down_price) / 2.0
    rho = (rate_up_price - rate_down_price) / 2.0

    return {
        "delta": float(delta),
        "gamma": float(gamma),
        "theta": float(theta_year / DAYS_PER_YEAR),
        "vega": float(vega),
        "rho": float(rho),
    }


# Orden de las griegas dentro de la tupla guardada en caché.
GREEK_NAMES = ("delta", "gamma", "theta", "vega", "rho")


@lru_cache(maxsize=GREEKS_CACHE_SIZE)
def _cached_greeks(kind: str, S: float, K: float, r: float, q: float, sigma: float,
                   T: float) -> tuple:
    """Griegas americanas guardadas en caché como TUPLA (inmutable).

    Clave: (kind, S, K, r, q, sigma, T). Las excepciones (T <= 0, sigma <= 0)
    no se guardan: se vuelven a lanzar en cada llamada.
    """
    greeks = _crr_greeks(kind, S, K, r, q, sigma, T, CRR_PRICE_STEPS, True)
    return tuple(greeks[name] for name in GREEK_NAMES)


def crr_greeks(kind: str, S: float, K: float, r: float, q: float, sigma: float,
               T: float) -> dict:
    """Griegas americanas (por acción) con el árbol CRR de 500/501 pasos.

    Mismas claves y unidades que `bs_greeks`: delta, gamma, theta por día
    natural, vega y rho por 1 punto porcentual. Con T <= 0 o sigma <= 0
    lanza ValueError (no están definidas) y la interfaz muestra "—".
    Se guardan en caché; cada llamada devuelve un diccionario NUEVO.
    """
    _check_kind(kind)
    values = _cached_greeks(kind, float(S), float(K), float(r), float(q),
                            float(sigma), float(T))
    return dict(zip(GREEK_NAMES, values))
