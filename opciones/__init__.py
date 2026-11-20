"""Motor de cálculo del Laboratorio de Opciones.

Aquí se reúne la API pública del motor: lo que la interfaz (app.py)
y los tests pueden importar directamente con `from opciones import ...`.
"""

from opciones.models import (
    DAYS_PER_YEAR,
    MIN_VOL,
    OPTION_MULTIPLIER,
    CommissionSettings,
    Leg,
    Market,
)
from opciones.payoff import pnl_expiry, pnl_today, position_greeks, price_grid
from opciones.pricing import bs_greeks, bs_price, default_premium

__all__ = [
    "DAYS_PER_YEAR",
    "MIN_VOL",
    "OPTION_MULTIPLIER",
    "CommissionSettings",
    "Leg",
    "Market",
    "bs_greeks",
    "bs_price",
    "default_premium",
    "pnl_expiry",
    "pnl_today",
    "position_greeks",
    "price_grid",
]
