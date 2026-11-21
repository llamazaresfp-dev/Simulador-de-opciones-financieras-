"""Series de precios sintéticas para los tests del backtest (Etapa C2, bloque 3).

Generan mundos cuya "verdad" conocemos, con `numpy.random.default_rng(seed)`
(misma semilla → misma serie):

- gbm_series: movimiento browniano geométrico de volatilidad constante
  (el mundo exacto del modelo: la PoP debería salir calibrada),
- regime_series: GBM cuya volatilidad cambia por bloques (10/20/40 %),
  para repartir las PoP por todos los deciles,
- jump_series: GBM con saltos bruscos ocasionales (colas gordas).

Todas devuelven (fechas ISO de días hábiles, close, adj_close) con
close == adj_close y sin dividendos. El crecimiento esperado del precio
es 0 (drift logarítmico −σ²/2), igual al neutral al riesgo con r = q = 0.
"""

import numpy as np

# Sesiones por año usadas para convertir la volatilidad anual a diaria.
SESSIONS_PER_YEAR = 252

START_DATE = "1980-01-02"


def business_days(count: int, start: str = START_DATE) -> list[str]:
    """Lista de 'count' días hábiles (lunes a viernes) desde 'start', en ISO."""
    first = np.datetime64(start, "D")
    days = np.arange(first, first + np.timedelta64(count * 2 + 7, "D"), dtype="datetime64[D]")
    days = days[np.is_busday(days)][:count]
    return [str(day) for day in days]


def _prices_from_returns(log_returns: np.ndarray, start_price: float) -> np.ndarray:
    """Precios a partir de log-rendimientos diarios (el primero es start_price)."""
    path = np.concatenate([[0.0], np.cumsum(log_returns)])
    return start_price * np.exp(path)


def _series(daily_sigma: np.ndarray, shocks: np.ndarray, start_price: float):
    """Serie GBM con drift de precio nulo y volatilidad diaria dada por sesión."""
    log_returns = -0.5 * daily_sigma**2 + daily_sigma * shocks
    close = _prices_from_returns(log_returns, start_price)
    dates = business_days(len(close))
    return dates, close, close.copy()


def gbm_series(count: int, sigma: float, seed: int, start_price: float = 100.0):
    """GBM de volatilidad anual constante 'sigma' con 'count' sesiones."""
    rng = np.random.default_rng(seed)
    daily_sigma = np.full(count - 1, sigma / np.sqrt(SESSIONS_PER_YEAR))
    return _series(daily_sigma, rng.standard_normal(count - 1), start_price)


def regime_series(
    count: int,
    seed: int,
    sigmas: tuple = (0.10, 0.20, 0.40),
    block: int = 504,
    start_price: float = 100.0,
):
    """GBM cuya volatilidad recorre 'sigmas' en bloques de 'block' sesiones."""
    rng = np.random.default_rng(seed)
    regime = (np.arange(count - 1) // block) % len(sigmas)
    daily_sigma = np.array(sigmas)[regime] / np.sqrt(SESSIONS_PER_YEAR)
    return _series(daily_sigma, rng.standard_normal(count - 1), start_price)


def jump_series(
    count: int,
    seed: int,
    sigma: float = 0.10,
    jump_prob: float = 0.02,
    jump_sd: float = 0.06,
    start_price: float = 100.0,
):
    """GBM de volatilidad 'sigma' más saltos N(0, jump_sd) un 'jump_prob' de los días."""
    rng = np.random.default_rng(seed)
    daily_sigma = np.full(count - 1, sigma / np.sqrt(SESSIONS_PER_YEAR))
    shocks = rng.standard_normal(count - 1)
    jumps = rng.normal(0.0, jump_sd, count - 1) * (rng.random(count - 1) < jump_prob)
    dates, close, _ = _series(daily_sigma, shocks, start_price)
    log_close = np.log(close) + np.concatenate([[0.0], np.cumsum(jumps)])
    close = np.exp(log_close)
    return dates, close, close.copy()
