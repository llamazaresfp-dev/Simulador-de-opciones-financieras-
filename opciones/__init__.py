"""Motor de cálculo del Laboratorio de Opciones.

Aquí se reúne la API pública del motor: lo que la interfaz (app.py)
y los tests pueden importar directamente con `from opciones import ...`.

La función principal es analyze(): recibe el mercado, las patas y los
ajustes de comisiones, y devuelve de una vez todo lo que la interfaz
necesita dibujar (curvas, métricas, griegas y comisiones).
"""

from dataclasses import dataclass

import numpy as np

from opciones.catalog import TEMPLATES, LegSpec, Template, build_legs
from opciones.commissions import close_fee_today, open_fee
from opciones.implied_vol import IVResult, implied_vol
from opciones.metrics import Metrics, compute_metrics
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
from opciones.simulation import ScenarioResult, SimulationSettings, simulate_scenario
from opciones.validation import (
    market_warnings,
    scenario_warnings,
    validate_legs,
    validate_market,
    validate_simulation,
)


@dataclass
class Analysis:
    """Resultado completo de analyze().

    - grid: precios del subyacente donde se evalúan las curvas.
    - expiry_curve: P&L al vencimiento en cada precio del grid (USD).
    - today_curve: P&L si cerramos hoy en cada precio del grid (USD).
    - metrics: beneficio máx., pérdida máx. y breakevens al vencimiento.
    - greeks: griegas de la posición (None en cada una si días = 0).
    - commission_total: comisiones de abrir y, si está activo, cerrar
      todas las patas de opción (USD).
    """

    grid: np.ndarray
    expiry_curve: np.ndarray
    today_curve: np.ndarray
    metrics: Metrics
    greeks: dict
    commission_total: float


def analyze(market: Market, legs: list[Leg], settings: CommissionSettings) -> Analysis:
    """Calcula todo lo que muestra la interfaz para una estrategia.

    Precondición: validate_market(market) y validate_legs(legs) ya
    devolvieron listas vacías (la interfaz no llama aquí con datos
    inválidos).
    """
    grid = price_grid(market, legs)
    expiry_curve = pnl_expiry(legs, market, settings, grid)
    today_curve = pnl_today(legs, market, settings, grid)
    metrics = compute_metrics(legs, market, settings)
    greeks = position_greeks(legs, market)

    # Total de comisiones: apertura + cierre (si "incluir cierre" está activo).
    commission_total = 0.0
    for leg in legs:
        commission_total += open_fee(leg, market, settings)
        commission_total += close_fee_today(leg, market, settings)

    return Analysis(
        grid=grid,
        expiry_curve=expiry_curve,
        today_curve=today_curve,
        metrics=metrics,
        greeks=greeks,
        commission_total=commission_total,
    )


__all__ = [
    "DAYS_PER_YEAR",
    "MIN_VOL",
    "OPTION_MULTIPLIER",
    "TEMPLATES",
    "Analysis",
    "CommissionSettings",
    "IVResult",
    "Leg",
    "LegSpec",
    "Market",
    "Metrics",
    "ScenarioResult",
    "SimulationSettings",
    "Template",
    "analyze",
    "build_legs",
    "bs_greeks",
    "bs_price",
    "compute_metrics",
    "default_premium",
    "implied_vol",
    "market_warnings",
    "pnl_expiry",
    "pnl_today",
    "position_greeks",
    "price_grid",
    "scenario_warnings",
    "simulate_scenario",
    "validate_legs",
    "validate_market",
    "validate_simulation",
]
