"""Catálogo de 8 estrategias clásicas (AC15, AC16).

Cada estrategia es una "plantilla" (Template): textos explicativos en
español y una lista de patas descritas de forma RELATIVA al spot
(por ejemplo, "call vendida con strike un 5 % por encima del spot").

build_legs() convierte una plantilla en patas reales (Leg) para el
mercado actual:

1. calcula cada strike como spot × (1 + desplazamiento),
2. lo redondea a un "paso" razonable según el precio (0,5 / 1 / 2,5 / 5 / 10),
3. pone como prima el precio Black-Scholes (default_premium),
4. las patas de acción son 100 acciones compradas al precio spot.

Los textos describen cómo funciona cada estrategia; no son
recomendaciones de inversión.
"""

import math
from dataclasses import dataclass

from opciones.models import Leg, Market
from opciones.pricing import default_premium

# Número de acciones de una pata de acción (las que cubre 1 contrato).
STOCK_SHARES = 100


@dataclass
class LegSpec:
    """Descripción relativa de una pata dentro de una plantilla.

    - kind: "call", "put" o "stock".
    - side: +1 compra (largo), -1 venta (corto).
    - strike_offset_pct: desplazamiento del strike respecto al spot, como
      fracción (0.05 = 5 % por encima; -0.05 = 5 % por debajo).
      En las acciones no se usa (pon 0.0).
    - quantity: contratos (opciones). En acciones se usa STOCK_SHARES.
    """

    kind: str
    side: int
    strike_offset_pct: float
    quantity: float = 1


@dataclass
class Template:
    """Una estrategia del catálogo: textos en español + patas relativas."""

    key: str
    name: str
    market_view: str
    bet: str
    max_profit: str
    max_loss: str
    when_to_use: str
    risks: str
    legs: list[LegSpec]


TEMPLATES = [
    Template(
        key="long_call",
        name="Long call (compra de call)",
        market_view="Alcista.",
        bet="Apuesta a que el precio suba por encima del strike más la prima antes del vencimiento.",
        max_profit="Ilimitado: cuanto más suba el precio, más se gana.",
        max_loss="Limitada a la prima pagada (más comisiones).",
        when_to_use="Cuando se espera una subida clara y se quiere arriesgar solo la prima.",
        risks="Si el precio no sube lo suficiente, la call vence sin valor y se pierde la prima. "
        "El paso del tiempo (theta) resta valor cada día.",
        legs=[LegSpec("call", 1, 0.0)],
    ),
    Template(
        key="long_put",
        name="Long put (compra de put)",
        market_view="Bajista.",
        bet="Apuesta a que el precio baje por debajo del strike menos la prima antes del vencimiento.",
        max_profit="Limitado pero grande: el strike menos la prima, si el precio cae hasta 0.",
        max_loss="Limitada a la prima pagada (más comisiones).",
        when_to_use="Cuando se espera una bajada clara y se quiere arriesgar solo la prima.",
        risks="Si el precio no baja lo suficiente, la put vence sin valor y se pierde la prima. "
        "El paso del tiempo (theta) resta valor cada día.",
        legs=[LegSpec("put", 1, 0.0)],
    ),
    Template(
        key="covered_call",
        name="Covered call (acción + call vendida)",
        market_view="Neutral o ligeramente alcista.",
        bet="Se tienen 100 acciones y se vende una call por encima del spot para cobrar la prima.",
        max_profit="Limitado: (strike − precio de compra + prima) × 100. "
        "Por encima del strike la ganancia ya no crece.",
        max_loss="Grande: si la acción cae a 0, se pierde el precio de compra menos la prima cobrada.",
        when_to_use="Cuando ya se tienen acciones y no se espera una subida fuerte a corto plazo.",
        risks="La prima solo amortigua un poco las caídas de la acción. "
        "Si la acción sube mucho, se renuncia a esa subida por encima del strike.",
        legs=[LegSpec("stock", 1, 0.0, STOCK_SHARES), LegSpec("call", -1, 0.05)],
    ),
    Template(
        key="protective_put",
        name="Protective put (acción + put comprada)",
        market_view="Alcista, pero con miedo a una caída.",
        bet="Se tienen 100 acciones y se compra una put por debajo del spot como seguro.",
        max_profit="Ilimitado: la acción puede seguir subiendo (menos el coste de la put).",
        max_loss="Limitada: (precio de compra − strike + prima) × 100, más comisiones.",
        when_to_use="Cuando se quiere conservar la acción pero limitar la pérdida si cae.",
        risks="El seguro cuesta dinero: si la acción no cae, la prima de la put se pierde "
        "y reduce la ganancia.",
        legs=[LegSpec("stock", 1, 0.0, STOCK_SHARES), LegSpec("put", 1, -0.05)],
    ),
    Template(
        key="bull_call_spread",
        name="Bull call spread (call comprada + call vendida más alta)",
        market_view="Moderadamente alcista.",
        bet="Apuesta a una subida moderada: se compra una call y se vende otra con strike más alto "
        "para abaratar la compra.",
        max_profit="Limitado: diferencia entre strikes menos el coste neto, × 100.",
        max_loss="Limitada al coste neto pagado (más comisiones).",
        when_to_use="Cuando se espera una subida, pero no enorme, y se quiere pagar menos que por una call sola.",
        risks="Si el precio queda por debajo del strike bajo, se pierde el coste neto. "
        "Por encima del strike alto la ganancia no crece.",
        legs=[LegSpec("call", 1, 0.0), LegSpec("call", -1, 0.05)],
    ),
    Template(
        key="bear_put_spread",
        name="Bear put spread (put comprada + put vendida más baja)",
        market_view="Moderadamente bajista.",
        bet="Apuesta a una bajada moderada: se compra una put y se vende otra con strike más bajo "
        "para abaratar la compra.",
        max_profit="Limitado: diferencia entre strikes menos el coste neto, × 100.",
        max_loss="Limitada al coste neto pagado (más comisiones).",
        when_to_use="Cuando se espera una bajada, pero no enorme, y se quiere pagar menos que por una put sola.",
        risks="Si el precio queda por encima del strike alto, se pierde el coste neto. "
        "Por debajo del strike bajo la ganancia no crece.",
        legs=[LegSpec("put", 1, 0.0), LegSpec("put", -1, -0.05)],
    ),
    Template(
        key="long_straddle",
        name="Long straddle (call + put al mismo strike)",
        market_view="Movimiento fuerte, sin saber en qué dirección.",
        bet="Apuesta a que el precio se mueva mucho (arriba o abajo); hay dos breakevens.",
        max_profit="Ilimitado si el precio sube mucho; grande si cae mucho.",
        max_loss="Limitada a las dos primas pagadas (más comisiones), si el precio acaba en el strike.",
        when_to_use="Antes de un evento que puede mover mucho el precio (por ejemplo, resultados).",
        risks="Es cara: se pagan dos primas. Si el precio se mueve poco, se pierde casi todo. "
        "La volatilidad puede bajar tras el evento y el tiempo resta valor cada día.",
        legs=[LegSpec("call", 1, 0.0), LegSpec("put", 1, 0.0)],
    ),
    Template(
        key="iron_condor",
        name="Iron condor (dos spreads vendidos)",
        market_view="Neutral: el precio se queda en un rango.",
        bet="Se venden una put y una call fuera del dinero y se compran otras más lejanas como protección; "
        "se cobra una prima neta.",
        max_profit="Limitado a la prima neta cobrada (menos comisiones), si el precio acaba entre los strikes vendidos.",
        max_loss="Limitada: ancho del spread menos la prima neta, × 100 (más comisiones).",
        when_to_use="Cuando se espera poco movimiento y volatilidad estable o a la baja.",
        risks="Un movimiento fuerte hacia cualquier lado lleva a la pérdida máxima, que suele ser "
        "mayor que la ganancia máxima. Tiene cuatro patas: más comisiones.",
        legs=[
            LegSpec("put", 1, -0.10),
            LegSpec("put", -1, -0.05),
            LegSpec("call", -1, 0.05),
            LegSpec("call", 1, 0.10),
        ],
    ),
]


def strike_step(spot: float) -> float:
    """Paso de redondeo de strikes según el precio del subyacente."""
    if spot < 25:
        return 0.5
    if spot < 100:
        return 1.0
    if spot < 250:
        return 2.5
    if spot < 1000:
        return 5.0
    return 10.0


def round_strike(value: float, step: float) -> float:
    """Redondea 'value' al múltiplo de 'step' más cercano (mitades hacia arriba)."""
    rounded = math.floor(value / step + 0.5) * step
    # round(..., 10) quita restos de coma flotante (p. ej. 20.500000000000004).
    return round(rounded, 10)


def _strikes_for(template: Template, spot: float) -> dict[float, float]:
    """Strike redondeado para cada desplazamiento distinto de la plantilla.

    Recorremos los desplazamientos de menor a mayor. Si el redondeo deja
    un strike igual o por debajo del anterior (pasa con spot bajo), lo
    subimos un paso: así los strikes siempre quedan ordenados y distintos
    (p. ej. en un bull spread, strike comprado < strike vendido).
    Las patas con el MISMO desplazamiento (straddle) comparten strike.
    """
    step = strike_step(spot)
    offsets = sorted({spec.strike_offset_pct for spec in template.legs if spec.kind != "stock"})
    strikes = {}
    previous = None
    for offset in offsets:
        strike = max(round_strike(spot * (1 + offset), step), step)
        if previous is not None and strike <= previous:
            strike = round(previous + step, 10)
        strikes[offset] = strike
        previous = strike
    return strikes


def build_legs(template: Template, market: Market) -> list[Leg]:
    """Convierte una plantilla en patas reales para el mercado actual.

    - Opciones: strike redondeado y prima Black-Scholes (default_premium).
    - Acciones: STOCK_SHARES acciones compradas al precio spot.
    """
    strikes = _strikes_for(template, market.spot)
    legs = []
    for spec in template.legs:
        if spec.kind == "stock":
            legs.append(Leg("stock", spec.side, STOCK_SHARES, None, market.spot))
        else:
            strike = strikes[spec.strike_offset_pct]
            premium = default_premium(spec.kind, market, strike)
            legs.append(Leg(spec.kind, spec.side, spec.quantity, strike, premium))
    return legs
