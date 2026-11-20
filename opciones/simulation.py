"""Escenarios de precio al vencimiento (Etapa A).

Bloque 2: probabilidad de beneficio (PoP) EXACTA, sin simular nada.
Bloque 3a: simulación de Monte Carlo (histograma, media, percentiles),
ver simulate_scenario al final del módulo.

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


# --- Bloque 3a: Monte Carlo ---------------------------------------------

# Número de barras (bins) del histograma del P&L.
HIST_BINS = 50

# El histograma se dibuja entre estos percentiles del P&L (0,5 % y 99,5 %).
HIST_CLIP_PERCENTILES = (0.5, 99.5)


@dataclass
class ScenarioResult:
    """Resumen de los escenarios al vencimiento (todo en USD salvo PoP y μ).

    - pop_exact: PoP exacta (bloque 2).
    - pop_mc: PoP simulada = fracción de trayectorias con P&L > ZERO_TOL.
    - mean_pnl: media del P&L simulado = "valor esperado" NO descontado
      (es una media de resultados futuros; no se trae a valor de hoy).
    - pnl_std: desviación típica del P&L simulado.
    - p5, p50, p95: percentiles 5 %, 50 % (mediana) y 95 % del P&L.
    - hist_counts, hist_edges: histograma del P&L (len(edges) = len(counts) + 1;
      la suma de counts es n_paths).
    - n_paths: número de trayectorias simuladas.
    - mu_used: crecimiento anual realmente usado (μ del usuario o r − q).
    """

    pop_exact: float
    pop_mc: float
    mean_pnl: float
    pnl_std: float
    p5: float
    p50: float
    p95: float
    hist_counts: np.ndarray
    hist_edges: np.ndarray
    n_paths: int
    mu_used: float


def _sample_terminal(market: Market, sim: SimulationSettings, drift: float) -> np.ndarray:
    """Genera n_paths precios finales posibles S_T (uno por trayectoria).

    Una sola fórmula por escenario (la misma lognormal que la PoP exacta):

        S_T = S · exp((drift − σ²/2)·T + σ·√T·Z),   Z ~ Normal(0, 1)

    ¿Por qué una semilla? Un ordenador genera números "aleatorios" a
    partir de una semilla: con la misma semilla salen siempre los mismos
    números, así el resultado es reproducible (no cambia en cada recálculo).
    """
    rng = np.random.default_rng(sim.seed)
    z = rng.standard_normal(sim.n_paths)
    sigma_t = market.vol * np.sqrt(market.T)
    shift = (drift - market.vol**2 / 2) * market.T
    return market.spot * np.exp(shift + sigma_t * z)


def _histogram(pnl: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Histograma del P&L recortado a sus percentiles 0,5 % – 99,5 %.

    Si una estrategia tiene ganancia (o pérdida) muy grande pero rara,
    unas pocas trayectorias extremas estirarían el eje y todas las barras
    quedarían apretadas. Por eso "recortamos": cualquier valor por debajo
    del percentil 0,5 % se cuenta en la primera barra y cualquier valor por
    encima del 99,5 % en la última. Así no se pierde ninguna trayectoria
    (la suma de las barras sigue siendo n_paths). Solo afecta al dibujo:
    la media y los percentiles se calculan con todos los datos.
    """
    low, high = np.percentile(pnl, HIST_CLIP_PERCENTILES)
    # P&L (casi) constante: si el rango es solo ruido de redondeo (más
    # estrecho que una millonésima de su tamaño), no se pueden hacer 50
    # barras distintas; abrimos un rango de 1 USD alrededor del valor.
    if high - low < 1e-6 * max(1.0, abs(low), abs(high)):
        low, high = low - 0.5, high + 0.5
    clipped = np.clip(pnl, low, high)
    counts, edges = np.histogram(clipped, bins=HIST_BINS, range=(low, high))
    return counts, edges


def simulate_scenario(
    market: Market,
    legs: list[Leg],
    settings: CommissionSettings,
    sim: SimulationSettings,
) -> ScenarioResult:
    """PoP exacta + simulación de Monte Carlo del P&L al vencimiento.

    Precondición: validate_market y validate_legs (y, en el bloque 3b,
    validate_simulation) no devolvieron errores; días > 0 y volatilidad > 0.

    Pasos:
    1. Elegimos el crecimiento (μ del usuario o r − q).
    2. Generamos n_paths precios finales con una semilla fija.
    3. Calculamos el P&L de la estrategia en todos a la vez (numpy).
    4. Resumimos: PoP simulada, media, desviación, percentiles e histograma.
    Sin caché ni trucos de reducción de varianza: el código queda simple.
    """
    drift = _drift(market, sim)
    prices = _sample_terminal(market, sim, drift)
    pnl = np.asarray(pnl_expiry(legs, market, settings, prices), dtype=float)

    p5, p50, p95 = np.percentile(pnl, [5, 50, 95])
    counts, edges = _histogram(pnl)

    return ScenarioResult(
        pop_exact=exact_pop(market, legs, settings, sim),
        # Mismo umbral que la PoP exacta: un P&L plano en cero no es "ganar".
        pop_mc=float(np.mean(pnl > ZERO_TOL)),
        mean_pnl=float(np.mean(pnl)),
        pnl_std=float(np.std(pnl)),
        p5=float(p5),
        p50=float(p50),
        p95=float(p95),
        hist_counts=counts,
        hist_edges=edges,
        n_paths=int(sim.n_paths),
        mu_used=float(drift),
    )
