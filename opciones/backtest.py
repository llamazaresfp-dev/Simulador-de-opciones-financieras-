"""Backtest de calibración de la PoP con el histórico del subyacente (Etapa C2).

Idea: recorrer fechas pasadas t y, usando SOLO datos con fecha ≤ t,
calcular la PoP exacta (Black-Scholes, lognormal) que la app habría dado
ese día para una plantilla; después mirar el cierre en t + H días y ver
si de verdad se ganó. No es rentabilidad real: no hay precios históricos
de opciones, solo se mide si las probabilidades están bien calibradas.

Este módulo es puro: numpy y el motor (opciones.*). No importa pandas,
Streamlit ni datos/, y no lee ni escribe archivos.

Convención de fechas: internamente cada fecha es un número entero de
días desde 1970-01-01 ("número de día"), así restar fechas es restar
enteros. `to_day_numbers` convierte una lista de fechas ISO.
"""

import math

import numpy as np

# Sesiones de mercado por año (para anualizar la volatilidad y el μ).
TRADING_DAYS = 252

# Sesiones usadas para el μ histórico (un año de mercado).
MU_LOOKBACK = 252

# Ventana del dividendo: los 365 días naturales anteriores a t.
DIVIDEND_WINDOW_DAYS = 365

# Duración media de un año natural en días (para contar años analizados).
DAYS_PER_YEAR_AVG = 365.25

# Si faltan menos de 0,25 años respecto a lo pedido, no se avisa (IP-3).
YEARS_TOLERANCE = 0.25


def to_day_numbers(dates) -> np.ndarray:
    """Convierte fechas ISO ("2025-06-30") en números de día (enteros)."""
    return np.array(dates, dtype="datetime64[D]").astype(np.int64)


def _format_decimal(value: float) -> str:
    """Número con 1 decimal y coma decimal (estilo español): 4.8 → "4,8"."""
    return f"{value:.1f}".replace(".", ",")


def realized_vol(adj_close, i: int, window: int) -> float | None:
    """Volatilidad realizada anual en la sesión i.

    Desviación típica (ddof = 1) de los log-rendimientos del cierre
    ajustado de las 'window' sesiones que terminan en i, × √252.
    Solo usa datos ≤ i. None si aún no hay 'window' rendimientos
    (i < window) o si algún precio de la ventana no es positivo.
    """
    if i < window or window < 2:
        return None
    prices = np.asarray(adj_close[i - window : i + 1], dtype=float)
    if np.any(prices <= 0):
        return None
    returns = np.log(prices[1:] / prices[:-1])
    return float(np.std(returns, ddof=1) * math.sqrt(TRADING_DAYS))


def trailing_mu(adj_close, i: int, vol: float, lookback: int = MU_LOOKBACK) -> float | None:
    """Crecimiento esperado anual del precio (μ) con el último año de datos.

    μ = media de los log-rendimientos de 'lookback' sesiones × 252 + vol²/2.
    Se suma vol²/2 porque SimulationSettings.mu es el crecimiento del
    PRECIO (no de su logaritmo): así el modelo reproduce el crecimiento
    logarítmico observado. Solo usa datos ≤ i; None si i < lookback.
    """
    if i < lookback:
        return None
    prices = np.asarray(adj_close[i - lookback : i + 1], dtype=float)
    if np.any(prices <= 0):
        return None
    returns = np.log(prices[1:] / prices[:-1])
    return float(np.mean(returns) * TRADING_DAYS + vol**2 / 2)


def trailing_dividend_yield(div_days, div_amounts, t_day: int, spot: float, underlying: str = "Acción") -> float:
    """Rentabilidad por dividendo q en el día t.

    Suma de los dividendos con fecha en (t − 365 días, t] dividida por el
    cierre de t. Para un índice devuelve 0 (no se modelan sus dividendos).
    'div_days' debe estar ordenado de menor a mayor.
    """
    if underlying == "Índice" or spot <= 0 or len(div_days) == 0:
        return 0.0
    div_days = np.asarray(div_days)
    amounts = np.asarray(div_amounts, dtype=float)
    # Posiciones de los bordes con búsqueda binaria (side="right": un
    # dividendo justo en t − 365 queda fuera, uno justo en t queda dentro).
    first = np.searchsorted(div_days, t_day - DIVIDEND_WINDOW_DAYS, side="right")
    last = np.searchsorted(div_days, t_day, side="right")
    return float(np.sum(amounts[first:last]) / spot)


def rate_at(rate_days, rate_values, t_day: int) -> float | None:
    """Tasa libre de riesgo (fracción) vigente en el día t.

    Es el último valor con fecha ≤ t (un sábado usa el del viernes).
    None si t es anterior al primer dato o si no hay datos.
    """
    if rate_days is None or len(rate_days) == 0:
        return None
    position = np.searchsorted(np.asarray(rate_days), t_day, side="right") - 1
    if position < 0:
        return None
    return float(rate_values[position])


def expiry_index(day_numbers, i: int, horizon_days: int) -> int | None:
    """Índice de la sesión de vencimiento para una entrada en la sesión i.

    Es el último día de negociación con fecha ≤ t + H (si t + H cae en
    fin de semana o festivo, el día hábil anterior). None si el último
    dato disponible es anterior a t + H (aún no ha vencido) o si no hay
    ninguna sesión después de t hasta t + H.
    """
    day_numbers = np.asarray(day_numbers)
    target = day_numbers[i] + horizon_days
    if day_numbers[-1] < target:
        return None
    j = int(np.searchsorted(day_numbers, target, side="right") - 1)
    if j <= i:
        return None
    return j


def first_analyzed_index(day_numbers, vol_window: int, years: float) -> tuple[int, float, str | None]:
    """Primera sesión que se analiza, años realmente disponibles y aviso.

    - Calentamiento: hace falta i ≥ max(W, 252) (ventana de volatilidad y
      año del μ), haya o no línea μ, para comparar las mismas fechas (IP-2).
    - Recorte por años: se empieza en la primera sesión con fecha
      ≥ última fecha − años·365,25 días (IP-3).
    - Aviso: si los años disponibles tras el calentamiento son menos que
      los pedidos − 0,25, se devuelve un texto con los años reales.

    Devuelve (índice, años disponibles, aviso o None). Si no hay sesiones
    suficientes el índice es len(day_numbers) (nada que analizar).
    """
    day_numbers = np.asarray(day_numbers)
    count = len(day_numbers)
    warm = max(vol_window, MU_LOOKBACK)

    if warm >= count:
        warning = (
            f"El histórico es demasiado corto: no queda ninguna fecha para analizar "
            f"(se pidieron {years} años)."
        )
        return count, 0.0, warning

    cut_day = day_numbers[-1] - years * DAYS_PER_YEAR_AVG
    cut_index = int(np.searchsorted(day_numbers, cut_day, side="left"))
    start = max(warm, cut_index)

    years_available = float((day_numbers[-1] - day_numbers[warm]) / DAYS_PER_YEAR_AVG)
    warning = None
    if years_available < years - YEARS_TOLERANCE:
        warning = (
            f"El histórico disponible solo permite analizar {_format_decimal(years_available)} "
            f"años (se pidieron {years}); se usa lo que hay."
        )
    return start, years_available, warning
