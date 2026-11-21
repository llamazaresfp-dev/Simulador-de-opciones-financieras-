"""Filtros de liquidez y limpieza de filas de la cadena de opciones.

Dos pasos separados:
- clean_row: descarta filas ROTAS (calidad del dato): faltan campos,
  NaN, None, números negativos, bid mayor que ask...
- filter_chain: descarta opciones que NO se pueden operar bien
  (liquidez): sin bid/ask, poco interés abierto, spread ancho o strike
  demasiado lejos del spot. También quita strikes repetidos.

Todos los umbrales viven en LiquidityRules (un único lugar). Funciones
puras: no lanzan excepciones ni hacen I/O.
"""

import math
import numbers
from dataclasses import dataclass

from datos.types import OptionQuote

# Tolerancia para comparar decimales. Los float no representan exacto
# muchos decimales: 0.40 - 0.30 da 0.10000000000000003, que es "mayor"
# que 0.10. Sin esta tolerancia, una opción justo en el límite de la
# regla se descartaría por un error de redondeo.
EPS = 1e-9


@dataclass(frozen=True)
class LiquidityRules:
    """Umbrales de liquidez (valores del SPEC). Único lugar donde viven.

    - min_oi: interés abierto mínimo (contratos), incluido.
    - max_rel_spread: spread máximo relativo al mid: (ask - bid) / mid.
    - max_abs_spread: spread máximo absoluto (USD), alternativa para
      opciones baratas (cuando el mid es menor que abs_spread_mid_below).
    - abs_spread_mid_below: por debajo de este mid se admite la regla absoluta.
    - max_strike_distance: distancia máxima del strike al spot, en
      fracción del spot (0.20 = ±20 %), incluida.
    - min_days / max_days: ventana de vencimientos en días naturales,
      ambos bordes incluidos.
    - eps: tolerancia para las comparaciones decimales.
    """

    min_oi: int = 100
    max_rel_spread: float = 0.10
    max_abs_spread: float = 0.10
    abs_spread_mid_below: float = 1.0
    max_strike_distance: float = 0.20
    min_days: int = 7
    max_days: int = 120
    eps: float = EPS


# Reglas por defecto que usa toda la app.
DEFAULT_RULES = LiquidityRules()

# Tipos de opción válidos.
VALID_KINDS = ("call", "put")


# --- Limpieza (calidad del dato) ---


def _to_number(value) -> float | None:
    """Convierte a float un número finito; si no lo es, devuelve None.

    Se rechazan bool (True no es un precio), textos, None, NaN e infinitos.
    """
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _to_non_negative(value) -> float | None:
    """Número finito y no negativo, o None."""
    number = _to_number(value)
    if number is None or number < 0:
        return None
    return number


def _to_count(value) -> int | None:
    """Cantidad entera no negativa (admite 100.0, rechaza 100.5), o None."""
    number = _to_non_negative(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _to_kind(value) -> str | None:
    """Normaliza "Call", " PUT " -> "call", "put"; otro valor -> None."""
    if not isinstance(value, str):
        return None
    kind = value.strip().lower()
    if kind not in VALID_KINDS:
        return None
    return kind


def clean_row(row) -> OptionQuote | None:
    """Convierte una fila cruda (dict) en OptionQuote, o None si está rota.

    Claves obligatorias: kind, strike, bid, ask, oi. Opcionales: last,
    volume, iv_yahoo (si faltan o son inválidas: None, 0 y None).
    Un bid = 0 NO es un dato roto: lo descarta después filter_chain.
    """
    if not isinstance(row, dict):
        return None
    kind = _to_kind(row.get("kind"))
    strike = _to_non_negative(row.get("strike"))
    bid = _to_non_negative(row.get("bid"))
    ask = _to_non_negative(row.get("ask"))
    oi = _to_count(row.get("oi"))
    if None in (kind, strike, bid, ask, oi):
        return None
    # Un strike de 0 no tiene sentido; bid mayor que ask es un dato roto.
    if strike == 0 or bid > ask:
        return None
    return OptionQuote(
        kind=kind,
        strike=strike,
        bid=bid,
        ask=ask,
        last=_to_non_negative(row.get("last")),
        oi=oi,
        volume=_to_count(row.get("volume")) or 0,
        iv_yahoo=_optional_iv(row.get("iv_yahoo")),
    )


def _optional_iv(value) -> float | None:
    """IV de Yahoo solo como referencia: positiva y finita, o None."""
    number = _to_number(value)
    if number is None or number <= 0:
        return None
    return number


# --- Liquidez ---


def _has_bid_and_ask(quote) -> bool:
    """Hay comprador y vendedor: bid y ask mayores que cero."""
    return quote.bid > 0 and quote.ask > 0


def _has_open_interest(quote, rules) -> bool:
    """Suficientes contratos abiertos (entero exacto, sin tolerancia)."""
    return quote.oi >= rules.min_oi


def _spread_is_tight(quote, rules) -> bool:
    """El hueco entre bid y ask es estrecho.

    Pasa si el spread relativo al mid es pequeño, o (solo para opciones
    baratas, mid por debajo del corte) si el spread absoluto es pequeño:
    en una opción de 0,35 USD un hueco de 0,10 ya es un 28 %, pero es
    el mínimo habitual del mercado. Ambas comparaciones usan EPS.
    """
    spread = quote.ask - quote.bid
    mid = quote.mid
    if spread <= rules.max_rel_spread * mid + rules.eps:
        return True
    return mid < rules.abs_spread_mid_below and spread <= rules.max_abs_spread + rules.eps


def _strike_near_spot(quote, spot, rules) -> bool:
    """El strike está dentro de ±max_strike_distance del spot (con EPS)."""
    distance = abs(quote.strike - spot) / spot
    return distance <= rules.max_strike_distance + rules.eps


def _is_liquid(quote, spot, rules) -> bool:
    """La cotización cumple todas las reglas de liquidez."""
    return (
        _has_bid_and_ask(quote)
        and _has_open_interest(quote, rules)
        and _spread_is_tight(quote, rules)
        and _strike_near_spot(quote, spot, rules)
    )


def dedupe(quotes) -> list:
    """Quita strikes repetidos: conserva la primera cotización por (kind, strike)."""
    seen = set()
    unique = []
    for quote in quotes:
        key = (quote.kind, quote.strike)
        if key not in seen:
            seen.add(key)
            unique.append(quote)
    return unique


def filter_chain(quotes, spot, rules=DEFAULT_RULES) -> list:
    """Devuelve solo las cotizaciones líquidas, sin duplicados, en el mismo orden.

    Primero se filtra la liquidez y después se quitan duplicados, para que
    un duplicado ilíquido no tape a uno líquido. Si el spot no es válido
    (no positivo, NaN, None) devuelve una lista vacía sin lanzar.
    """
    spot = _to_number(spot)
    if spot is None or spot <= 0:
        return []
    liquid = [quote for quote in quotes if _is_liquid(quote, spot, rules)]
    return dedupe(liquid)


def is_expiry_in_window(days, rules=DEFAULT_RULES) -> bool:
    """True si un vencimiento a `days` días naturales está en la ventana.

    Días enteros: comparación exacta, ambos bordes incluidos.
    """
    return rules.min_days <= days <= rules.max_days

