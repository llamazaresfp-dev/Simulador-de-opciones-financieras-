"""Validación de entradas y avisos informativos (AC1, AC17, decisión 13).

Antes de calcular nada comprobamos que los datos tienen sentido.
Las funciones devuelven listas de mensajes en español:

- validate_market / validate_legs: ERRORES. Si la lista está vacía, los
  datos son válidos y se puede llamar a analyze().
- market_warnings: AVISOS informativos. No impiden calcular; solo
  ayudan a interpretar los resultados.
- validate_simulation / scenario_warnings (Etapa A): lo mismo para los
  escenarios de Monte Carlo.

Nunca lanzan excepciones: con datos raros (None, texto, NaN...)
simplemente devuelven un mensaje de error.
"""

import math

import numpy as np

from opciones.models import MIN_VOL

VALID_UNDERLYINGS = ("Acción", "ETF", "Índice")
VALID_KINDS = ("call", "put", "stock")
VALID_SIDES = (1, -1)

MSG_NOT_ADVICE = "Herramienta de estudio, no asesoría de inversión."
MSG_AMERICAN = (
    "Las opciones sobre acciones y ETF son americanas (se pueden ejercer antes "
    "del vencimiento). Black-Scholes es solo una aproximación: puede "
    "infravalorarlas, sobre todo los puts (hasta ~7 % medido)."
)
MSG_EUROPEAN = (
    "Las opciones sobre índices son europeas (solo se ejercen al vencimiento): "
    "Black-Scholes es el modelo adecuado."
)
MSG_ZERO_DAYS = (
    "Días al vencimiento = 0: la curva «hoy» coincide con el valor intrínseco "
    "y las griegas no se pueden calcular (se muestran como «—»)."
)
MSG_CLOSE_FEE = (
    "Comisión de cierre al vencimiento: solo se cobra si la opción vence con "
    "valor; si vence sin valor, expira sola y no paga cierre."
)


def _is_number(value) -> bool:
    """True si 'value' es un número real usable (no None, texto, NaN ni infinito)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def validate_market(market) -> list[str]:
    """Errores en los datos globales del mercado (lista vacía = válido)."""
    if market is None:
        return ["Faltan los datos del mercado."]

    errors = []

    if market.underlying not in VALID_UNDERLYINGS:
        errors.append("El tipo de subyacente debe ser Acción, ETF o Índice.")

    if not _is_number(market.spot):
        errors.append("El precio del subyacente (spot) está vacío o no es un número.")
    elif market.spot <= 0:
        errors.append("El precio del subyacente (spot) debe ser mayor que 0.")

    if not _is_number(market.vol):
        errors.append("La volatilidad está vacía o no es un número.")
    elif market.vol < MIN_VOL:
        errors.append("La volatilidad debe ser como mínimo 0,01 %.")

    if not _is_number(market.days):
        errors.append("Los días al vencimiento están vacíos o no son un número.")
    elif market.days < 0:
        errors.append(
            "Los días al vencimiento no pueden ser negativos "
            "(usa 0 para el mismo día del vencimiento)."
        )

    if not _is_number(market.rate):
        errors.append("El tipo de interés está vacío o no es un número.")

    if not _is_number(market.q):
        errors.append("El dividendo está vacío o no es un número.")

    return errors


def _validate_leg(leg) -> list[str]:
    """Errores de una sola pata (sin el prefijo «Pata N»)."""
    errors = []

    if leg.kind not in VALID_KINDS:
        errors.append("el tipo debe ser call, put o acción.")
    if leg.side not in VALID_SIDES:
        errors.append("la dirección debe ser compra (+1) o venta (−1).")

    if not _is_number(leg.quantity):
        errors.append("la cantidad está vacía o no es un número.")
    elif leg.quantity <= 0:
        errors.append("la cantidad debe ser mayor que 0.")

    is_option = leg.kind in ("call", "put")
    if is_option:
        if not _is_number(leg.strike):
            errors.append("el strike está vacío o no es un número.")
        elif leg.strike <= 0:
            errors.append("el strike debe ser mayor que 0.")

    # En opciones el precio es la prima; en acciones, el precio de entrada.
    if not _is_number(leg.price):
        if is_option:
            errors.append("la prima está vacía o no es un número.")
        else:
            errors.append("el precio de entrada está vacío o no es un número.")
    elif leg.price < 0:
        if is_option:
            errors.append("la prima no puede ser negativa.")
        else:
            errors.append("el precio de entrada no puede ser negativo.")

    return errors


def validate_legs(legs) -> list[str]:
    """Errores en las patas de la estrategia (lista vacía = válido).

    Cada mensaje empieza por «Pata N:» para saber qué fila corregir.
    """
    if not legs:
        return ["La estrategia no tiene patas: añade al menos una."]

    errors = []
    for number, leg in enumerate(legs, start=1):
        for message in _validate_leg(leg):
            errors.append(f"Pata {number}: {message}")
    return errors


def market_warnings(market) -> list[str]:
    """Avisos informativos para mostrar junto a los resultados.

    - Siempre: es una herramienta de estudio, no asesoría.
    - Acción/ETF: Black-Scholes aproxima opciones americanas (más en puts).
    - Índice: las opciones son europeas.
    - Días = 0: la curva «hoy» es el intrínseco y no hay griegas.
    - Siempre: cuándo se cobra la comisión de cierre al vencimiento.
    """
    warnings = [MSG_NOT_ADVICE]
    if market is None:
        return warnings

    if market.underlying in ("Acción", "ETF"):
        warnings.append(MSG_AMERICAN)
    elif market.underlying == "Índice":
        warnings.append(MSG_EUROPEAN)

    if _is_number(market.days) and market.days == 0:
        warnings.append(MSG_ZERO_DAYS)

    warnings.append(MSG_CLOSE_FEE)
    return warnings


# --- Escenarios de Monte Carlo (Etapa A, decisiones A10 y A11) ---------------

# Rangos de la simulación (decisión A11).
MIN_PATHS = 1_000
MAX_PATHS = 1_000_000
MIN_SEED = 0
MAX_SEED = 2**32 - 1
MIN_MU = -0.50  # −50 % anual
MAX_MU = 1.00  # +100 % anual

MSG_SCENARIO_ZERO_DAYS = (
    "Escenarios: con 0 días al vencimiento no hay tiempo hasta el vencimiento, "
    "así que no hay distribución de precios que simular. Usa al menos 1 día."
)
MSG_MISSING_SIM = "Faltan los ajustes de la simulación."
MSG_BAD_PATHS = (
    "El número de simulaciones debe ser un número entero entre 1 000 y 1 000 000."
)
MSG_BAD_SEED = "La semilla debe ser un número entero entre 0 y 4 294 967 295."
MSG_BAD_MU = (
    "El crecimiento esperado (μ) debe ser un número entre −50 % y +100 % anual, "
    "o quedar vacío para usar el escenario neutral al riesgo."
)

MSG_MODEL = (
    "Los escenarios son el resultado de un modelo (precio final lognormal), "
    "no una predicción de lo que hará el mercado."
)
MSG_FAT_TAILS = (
    "Las distribuciones reales tienen colas más gruesas que la lognormal: los "
    "movimientos extremos son más frecuentes de lo que indica el modelo, así "
    "que la probabilidad de beneficio y los percentiles 5/95 pueden ser "
    "optimistas."
)
MSG_SCENARIO_AMERICAN = (
    "Las opciones sobre acciones y ETF son americanas (se pueden ejercer antes "
    "del vencimiento): la volatilidad implícita y la simulación usan un modelo "
    "europeo y quedan sesgadas."
)


def _is_integer(value) -> bool:
    """True si 'value' es un entero de verdad (int de Python o de numpy, no bool)."""
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, np.integer))


def validate_simulation(market, legs, sim) -> list[str]:
    """Errores para calcular los escenarios (lista vacía = válido).

    Reutiliza validate_market y validate_legs (mismos mensajes del MVP) y
    añade:
    - días = 0: error solo para escenarios (el MVP sí lo admite).
    - n_paths: entero entre 1 000 y 1 000 000.
    - seed: entero entre 0 y 2³² − 1.
    - mu: None (neutral al riesgo) o número entre −0,50 y +1,00 (fracción anual).

    Nunca lanza excepciones.
    """
    errors = validate_market(market) + validate_legs(legs)

    days = getattr(market, "days", None)
    if _is_number(days) and days == 0:
        errors.append(MSG_SCENARIO_ZERO_DAYS)

    if sim is None:
        errors.append(MSG_MISSING_SIM)
        return errors

    n_paths = getattr(sim, "n_paths", None)
    if not _is_integer(n_paths) or not MIN_PATHS <= n_paths <= MAX_PATHS:
        errors.append(MSG_BAD_PATHS)

    seed = getattr(sim, "seed", None)
    if not _is_integer(seed) or not MIN_SEED <= seed <= MAX_SEED:
        errors.append(MSG_BAD_SEED)

    mu = getattr(sim, "mu", None)
    if mu is not None and (not _is_number(mu) or not MIN_MU <= mu <= MAX_MU):
        errors.append(MSG_BAD_MU)

    return errors


def scenario_warnings(market) -> list[str]:
    """Avisos para mostrar junto a los escenarios (AC-A15).

    - Siempre: es un modelo, no una predicción.
    - Siempre: las colas reales son más gruesas que la lognormal.
    - Acción/ETF: las opciones americanas sesgan la IV y la simulación.
    - Índice: las opciones son europeas.
    - Siempre: herramienta de estudio, no asesoría (mismo texto del MVP).
    """
    warnings = [MSG_MODEL, MSG_FAT_TAILS]

    underlying = getattr(market, "underlying", None)
    if underlying in ("Acción", "ETF"):
        warnings.append(MSG_SCENARIO_AMERICAN)
    elif underlying == "Índice":
        warnings.append(MSG_EUROPEAN)

    warnings.append(MSG_NOT_ADVICE)
    return warnings
