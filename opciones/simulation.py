"""Escenarios de precio al vencimiento (Etapa A).

Bloque 2: probabilidad de beneficio (PoP) EXACTA, sin simular nada.

Idea clave: al vencimiento el P&L es "lineal a tramos" (ver metrics.py).
Solo puede cambiar de signo en un breakeven (donde una recta cruza el
cero) o en un strike (donde la comisión de cierre da un pequeño salto).
Así que si partimos el eje de precios usando 0, los strikes y los
breakevens, DENTRO de cada intervalo el signo del P&L es constante:
basta con mirar un punto (el punto medio) para saber si ese intervalo
gana o pierde.

Después sumamos la probabilidad de que el precio final caiga en cada
intervalo ganador. Suponemos que el precio final es lognormal:

    ln(S_T) = ln(S) + (drift − σ²/2)·T + σ·√T·Z,   Z ~ Normal(0, 1)

y por tanto su función de distribución (CDF) es

    CDF(x) = Φ((ln(x/S) − (drift − σ²/2)·T) / (σ·√T)),   CDF(0) = 0.

¿Qué crecimiento (drift) usamos?
- Por defecto, el "neutral al riesgo": r − q. Es el mismo que usa
  Black-Scholes para poner precio a las opciones; NO es una predicción.
- Si el usuario escribe μ (crecimiento esperado del precio, % anual),
  usamos μ para explorar un escenario propio.
"""

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from opciones.metrics import ZERO_TOL, compute_metrics
from opciones.models import CommissionSettings, Leg, Market
from opciones.payoff import pnl_expiry


@dataclass
class SimulationSettings:
    """Ajustes de la simulación de escenarios.

    - n_paths: número de trayectorias de Monte Carlo (bloque 3).
    - seed: semilla del generador aleatorio (mismo valor = mismo resultado).
    - mu: crecimiento esperado anual del precio como fracción (0.05 = 5 %),
      o None para usar el escenario neutral al riesgo (r − q).
    """

    n_paths: int = 100_000
    seed: int = 42
    mu: float | None = None


def _drift(market: Market, sim: SimulationSettings) -> float:
    """Crecimiento anual usado: μ si el usuario lo dio; si no, r − q."""
    if sim.mu is not None:
        return sim.mu
    return market.rate - market.q


def _lognormal_cdf(x: np.ndarray, market: Market, drift: float) -> np.ndarray:
    """Probabilidad de que el precio final sea <= x (x >= 0).

    En x = 0 devolvemos 0 directamente (el logaritmo de 0 no existe:
    un precio lognormal nunca llega a 0).
    """
    x = np.asarray(x, dtype=float)
    sigma_t = market.vol * np.sqrt(market.T)
    shift = (drift - market.vol**2 / 2) * market.T
    result = np.zeros_like(x)
    positive = x > 0
    result[positive] = norm.cdf((np.log(x[positive] / market.spot) - shift) / sigma_t)
    return result


def _boundaries(legs: list[Leg], market: Market, settings: CommissionSettings) -> list[float]:
    """Fronteras entre tramos: 0, strikes y breakevens (únicos y ordenados).

    Entre dos fronteras consecutivas el signo del P&L no cambia.
    """
    strikes = [float(leg.strike) for leg in legs if leg.kind != "stock" and leg.strike > 0]
    breakevens = compute_metrics(legs, market, settings).breakevens
    return sorted({0.0, *strikes, *breakevens})


def exact_pop(
    market: Market,
    legs: list[Leg],
    settings: CommissionSettings,
    sim: SimulationSettings,
) -> float:
    """Probabilidad exacta de que el P&L al vencimiento sea > 0.

    Precondición: el mercado y las patas son válidos, con días > 0 y
    volatilidad > 0 (si no, no hay distribución de precios).

    "Beneficio" significa P&L > ZERO_TOL (el mismo umbral que las métricas),
    así un tramo plano en cero no cuenta como ganador.
    """
    drift = _drift(market, sim)
    edges = _boundaries(legs, market, settings)

    # Un punto de sondeo por intervalo: el punto medio de cada [a, b] y,
    # para la cola derecha (de la última frontera hasta el infinito),
    # un punto claramente a la derecha de la última frontera.
    last = edges[-1]
    midpoints = [(a + b) / 2 for a, b in zip(edges[:-1], edges[1:])]
    probes = np.array(midpoints + [last + max(last, 1.0)])
    wins = np.asarray(pnl_expiry(legs, market, settings, probes)) > ZERO_TOL

    # Probabilidad de cada intervalo = CDF(b) − CDF(a); la cola llega hasta 1.
    cdf = _lognormal_cdf(np.array(edges), market, drift)
    interval_probs = np.append(np.diff(cdf), 1.0 - cdf[-1])

    pop = float(np.sum(interval_probs[wins]))
    return min(max(pop, 0.0), 1.0)
