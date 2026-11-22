"""Calculadoras de la comparación de estrategias (Etapa D, bloque 3).

- net_premium: cuánto se cobra (crédito, > 0) o se paga (débito, < 0)
  al abrir, solo por las primas de las opciones.
- common_grid: una malla de precios común para dibujar todas las curvas
  al vencimiento sobre el mismo eje.
- revalue_legs: patas guardadas -> patas del motor con el mercado actual.
- market_difference_notice: aviso si una estrategia se guardó con otro
  mercado.
- compare_strategies: las curvas y la fila de números de cada estrategia.

No usa analyze(): así la curva «hoy» y las griegas (lentas con el árbol
binomial) solo se calculan si se piden (with_heavy=True). Nada visual
aquí: los colores y el gráfico viven en la interfaz.
"""

import math
from dataclasses import dataclass

import numpy as np

from opciones.commissions import close_fee_today, open_fee
from opciones.metrics import compute_metrics
from opciones.models import OPTION_MULTIPLIER, Leg, Market
from opciones.payoff import pnl_expiry, pnl_today, position_greeks, price_grid
from opciones.pricing import default_premium
from opciones.simulation import exact_pop
from opciones.validation import validate_legs, validate_market

# Como máximo 4 estrategias: la del Constructor + 3 guardadas.
MAX_STRATEGIES = 4

# Tolerancia para decidir si dos mercados son "iguales".
MARKET_TOL = 1e-9

MSG_MAX = "Máximo 4 estrategias en la comparación (la del Constructor + 3 guardadas)."
MSG_CALC_FAILED = "No se pudo calcular «{name}»."
MSG_MARKET_DIFFERENT = (
    "«{name}» se guardó con spot {spot} / vol {vol} % / {days} días; "
    "aquí se usa el mercado actual (spot {cur_spot} / vol {cur_vol} % / {cur_days} días)."
)


@dataclass
class ComparisonRow:
    """Fila de la tabla comparativa de una estrategia.

    - best_pnl / worst_pnl: None si es ilimitado (como en Metrics).
    - net_premium: crédito (> 0) o débito (< 0) de las primas, en USD.
    - pop: probabilidad exacta de beneficio; None con 0 días o vol <= 0.
    - greeks: griegas de la posición, solo si se pidieron (si no, None).
    """

    label: str
    best_pnl: float | None
    worst_pnl: float | None
    profit_unlimited: bool
    loss_unlimited: bool
    breakevens: list[float]
    commission_total: float
    net_premium: float
    pop: float | None
    greeks: dict | None


@dataclass
class ComparisonResult:
    """Resultado de compare_strategies.

    - grid: malla común de precios.
    - expiry_curves: una curva de P&L al vencimiento por fila, sobre `grid`.
    - today_curves: None, o una lista de (malla_propia, curva «hoy») por
      fila; cada estrategia usa su PROPIA malla (DD-23).
    - rows: filas de la tabla, en el orden de entrada.
    - errors: mensajes en español de las entradas que se omitieron.
    """

    grid: np.ndarray
    expiry_curves: list
    today_curves: list | None
    rows: list
    errors: list


def net_premium(legs: list[Leg]) -> float:
    """Flujo de caja de las primas al abrir: Σ −lado × prima × cantidad × 100.

    Crédito > 0 (vendemos opciones), débito < 0 (compramos). Las acciones
    no cuentan: su precio de entrada no es una prima.
    """
    total = 0.0
    for leg in legs:
        if leg.kind == "stock":
            continue
        total += -leg.side * leg.price * leg.quantity * OPTION_MULTIPLIER
    return total


def common_grid(grids) -> np.ndarray:
    """Une varias mallas en una sola, ordenada y sin duplicados."""
    if not grids:
        return np.array([])
    return np.unique(np.concatenate(grids))


def revalue_legs(saved_legs, market: Market) -> list[Leg]:
    """Patas guardadas -> patas del motor con el mercado actual (DD-13).

    - Prima manual, o pata de mercado/editada: se conserva la prima guardada.
    - Pata automática: acción -> spot actual; opción -> prima del modelo
      activo (misma regla que refresh_auto_prices de la app).
    """
    legs = []
    for saved in saved_legs:
        if saved.premium_manual or saved.premium_source in ("mercado", "manual"):
            price = saved.price
        elif saved.kind == "stock":
            price = float(market.spot)
        else:
            price = float(default_premium(saved.kind, market, saved.strike))
        strike = None if saved.kind == "stock" else saved.strike
        legs.append(Leg(saved.kind, saved.side, saved.quantity, strike, price))
    return legs


def _format_number(value) -> str:
    """Número corto en formato español: 25.0 -> "25", 0.3912 -> "0,3912"."""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _differs(a, b) -> bool:
    return abs(a - b) > MARKET_TOL


def market_difference_notice(name: str, saved_market: Market, current_market: Market) -> str | None:
    """Texto si la estrategia se guardó con otro mercado; None si es el mismo.

    Compara spot, vol y días (tolerancia 1e-9); si además cambian el
    subyacente, la tasa, el dividendo o el modelo, se añaden al texto (E-7).
    """
    extras = []
    if saved_market.underlying != current_market.underlying:
        extras.append(f"subyacente {saved_market.underlying} → {current_market.underlying}")
    if _differs(saved_market.rate, current_market.rate):
        extras.append(
            f"tasa {_format_number(saved_market.rate * 100)} % → {_format_number(current_market.rate * 100)} %"
        )
    if _differs(saved_market.q, current_market.q):
        extras.append(
            f"dividendo {_format_number(saved_market.q * 100)} % → {_format_number(current_market.q * 100)} %"
        )
    if saved_market.pricing_model != current_market.pricing_model:
        extras.append(f"modelo {saved_market.pricing_model} → {current_market.pricing_model}")

    main_differs = (
        _differs(saved_market.spot, current_market.spot)
        or _differs(saved_market.vol, current_market.vol)
        or _differs(saved_market.days, current_market.days)
    )
    if not main_differs and not extras:
        return None

    text = MSG_MARKET_DIFFERENT.format(
        name=name,
        spot=_format_number(saved_market.spot),
        vol=_format_number(saved_market.vol * 100),
        days=_format_number(saved_market.days),
        cur_spot=_format_number(current_market.spot),
        cur_vol=_format_number(current_market.vol * 100),
        cur_days=_format_number(current_market.days),
    )
    if extras:
        text += " También cambia: " + ", ".join(extras) + "."
    return text


def _is_finite(value) -> bool:
    """True si el número (o None) es finito; None cuenta como válido ("—")."""
    return value is None or math.isfinite(value)


def _compute_row(label: str, legs: list[Leg], market: Market, settings, sim, with_heavy: bool):
    """Calcula la fila, la malla propia y (si se pide) la curva «hoy» de una estrategia.

    Devuelve (fila, malla_propia, curva_hoy o None), o None si algún
    número no es finito. Puede lanzar: lo envuelve compare_strategies.
    """
    own_grid = price_grid(market, legs)
    # Comprobación previa: la curva al vencimiento en su propia malla.
    own_expiry = pnl_expiry(legs, market, settings, own_grid)
    metrics = compute_metrics(legs, market, settings)

    commission_total = 0.0
    for leg in legs:
        commission_total += open_fee(leg, market, settings)
        commission_total += close_fee_today(leg, market, settings)

    pop = None
    if market.days > 0 and market.vol > 0:
        pop = exact_pop(market, legs, settings, sim)

    greeks = None
    today_curve = None
    if with_heavy:
        greeks = position_greeks(legs, market)
        today_curve = pnl_today(legs, market, settings, own_grid)

    row = ComparisonRow(
        label=label,
        best_pnl=metrics.best_pnl,
        worst_pnl=metrics.worst_pnl,
        profit_unlimited=metrics.profit_unlimited,
        loss_unlimited=metrics.loss_unlimited,
        breakevens=list(metrics.breakevens),
        commission_total=float(commission_total),
        net_premium=float(net_premium(legs)),
        pop=pop,
        greeks=greeks,
    )

    numbers = [row.best_pnl, row.worst_pnl, row.commission_total, row.net_premium, row.pop]
    numbers += row.breakevens
    numbers += list((greeks or {}).values())
    if not all(_is_finite(value) for value in numbers):
        return None
    arrays = [own_grid, own_expiry] + ([today_curve] if today_curve is not None else [])
    if not all(np.all(np.isfinite(array)) for array in arrays):
        return None
    return row, own_grid, today_curve


def compare_strategies(entries, market: Market, settings, sim, with_heavy: bool = False) -> ComparisonResult:
    """Compara hasta 4 estrategias con el MISMO mercado y comisiones.

    - entries: lista de (etiqueta, patas del motor).
    - with_heavy: si es True, también curvas «hoy» (en la malla propia de
      cada estrategia) y griegas.
    Una entrada inválida, que lanza o que da números no finitos se omite
    con un mensaje en `errors`. Nunca lanza por los datos (DD-22).
    """
    empty = ComparisonResult(np.array([]), [], None, [], [])
    if len(entries) > MAX_STRATEGIES:
        empty.errors.append(MSG_MAX)
        return empty
    market_errors = validate_market(market)
    if market_errors:
        empty.errors.extend(market_errors)
        return empty

    computed = []  # (etiqueta, patas, fila, malla propia, curva «hoy»)
    errors = []
    for label, legs in entries:
        leg_errors = validate_legs(legs)
        if leg_errors:
            errors.append(f"«{label}»: " + " ".join(leg_errors))
            continue
        try:
            with np.errstate(all="ignore"):
                outcome = _compute_row(label, legs, market, settings, sim, with_heavy)
        except Exception:
            outcome = None
        if outcome is None:
            errors.append(MSG_CALC_FAILED.format(name=label))
            continue
        row, own_grid, today_curve = outcome
        computed.append((label, legs, row, own_grid, today_curve))

    grid = common_grid([item[3] for item in computed])
    expiry_curves = []
    today_curves = [] if with_heavy else None
    rows = []
    for label, legs, row, own_grid, today_curve in computed:
        try:
            with np.errstate(all="ignore"):
                curve = pnl_expiry(legs, market, settings, grid)
            finite = bool(np.all(np.isfinite(curve)))
        except Exception:
            finite = False
        if not finite:
            errors.append(MSG_CALC_FAILED.format(name=label))
            continue
        expiry_curves.append(curve)
        rows.append(row)
        if with_heavy:
            today_curves.append((own_grid, today_curve))

    return ComparisonResult(grid, expiry_curves, today_curves, rows, errors)
