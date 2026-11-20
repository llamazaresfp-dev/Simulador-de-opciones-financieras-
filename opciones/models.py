"""Modelos de datos del motor: patas, mercado y ajustes de comisiones.

Son clases muy simples (dataclasses): solo guardan datos, no calculan
precios. Los cálculos viven en otros módulos (pricing, payoff, ...).
"""

from dataclasses import dataclass

# Volatilidad mínima permitida (0,01 % expresado como fracción).
# Por debajo de este valor la validación muestra un error.
MIN_VOL = 0.0001

# Usamos días naturales: un año = 365 días.
DAYS_PER_YEAR = 365

# Un contrato de opción en EE. UU. controla 100 acciones.
OPTION_MULTIPLIER = 100

# Modelos de valoración antes del vencimiento (campo Market.pricing_model).
# - "binomial": árbol CRR con ejercicio anticipado (americano) para Acción/ETF.
# - "black_scholes": fórmula europea (la de la Etapa A).
# Índice siempre se valora con Black-Scholes (es europeo).
PRICING_BINOMIAL = "binomial"
PRICING_BLACK_SCHOLES = "black_scholes"
PRICING_MODELS = (PRICING_BINOMIAL, PRICING_BLACK_SCHOLES)


@dataclass
class Leg:
    """Una pata de la estrategia: una opción (call/put) o acciones.

    - kind: "call", "put" o "stock".
    - side: +1 si compramos (largo), -1 si vendemos (corto).
    - quantity: número de contratos (opciones) o de acciones (stock).
    - strike: precio de ejercicio; None para acciones.
    - price: prima pagada/cobrada por acción (opciones)
      o precio de entrada (acciones).
    """

    kind: str
    side: int
    quantity: float
    strike: float | None
    price: float

    @property
    def multiplier(self) -> int:
        """Cuántas acciones representa cada unidad de 'quantity'."""
        if self.kind == "stock":
            return 1
        return OPTION_MULTIPLIER


@dataclass
class Market:
    """Datos globales del mercado, comunes a todas las patas.

    - underlying: "Acción", "ETF" o "Índice".
    - spot: precio actual del subyacente.
    - vol: volatilidad anual como fracción (0.20 = 20 %).
    - days: días naturales hasta el vencimiento (común a todas las patas).
    - rate: tipo de interés libre de riesgo anual como fracción.
    - q: rentabilidad por dividendo anual como fracción (0 por defecto).
    - pricing_model: modelo para valorar antes del vencimiento,
      "binomial" (por defecto) o "black_scholes". Es el último campo para
      que los Market(...) existentes, posicionales o por nombre, sigan valiendo.
    """

    underlying: str
    spot: float
    vol: float
    days: float
    rate: float
    q: float = 0.0
    pricing_model: str = PRICING_BINOMIAL

    @property
    def T(self) -> float:
        """Tiempo hasta el vencimiento en años (lo que usa Black-Scholes)."""
        return self.days / DAYS_PER_YEAR


@dataclass
class CommissionSettings:
    """Ajustes de comisiones (en USD por contrato de opción).

    - per_contract: comisión por contrato en cada operación.
    - index_surcharge: recargo extra por contrato en opciones sobre índices.
    - include_close: si True, también se cobra la comisión al cerrar.
    """

    per_contract: float = 0.65
    index_surcharge: float = 0.60
    include_close: bool = True
