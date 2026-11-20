"""Validación de entradas y avisos informativos (AC1, AC17, decisión 13).

Antes de calcular nada comprobamos que los datos tienen sentido.
Las funciones devuelven listas de mensajes en español:

- validate_market / validate_legs: ERRORES. Si la lista está vacía, los
  datos son válidos y se puede llamar a analyze().
- market_warnings: AVISOS informativos. No impiden calcular; solo
  ayudan a interpretar los resultados.

Nunca lanzan excepciones: con datos raros (None, texto, NaN...)
simplemente devuelven un mensaje de error.
"""

import math

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
