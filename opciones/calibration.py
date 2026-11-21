"""Calibración de probabilidades y diagnóstico de colas (Etapa C2).

Es la "calculadora de notas" del backtest. Recibe dos listas alineadas:

- pop: la probabilidad de beneficio (PoP) que la app habría dicho cada día,
- win: si de verdad se ganó (1/True) o no (0/False),

y calcula:

- el intervalo de confianza de Wilson de una proporción,
- el puntaje de Brier (error cuadrático medio de las probabilidades),
  el Brier "climatológico" (el de decir siempre la tasa media) y la
  habilidad 1 − Brier/Brier climatológico,
- la tabla de fiabilidad por deciles fijos [0, 0,1), …, [0,9, 1,0],
- la desviación máxima entre PoP media y tasa observada,
- el N efectivo (las ventanas de H días se solapan),
- el diagnóstico de colas de los movimientos estandarizados z.

Matemática pura: solo numpy y scipy.stats; sin pandas, sin Streamlit
y sin leer ni escribir archivos. Nunca devuelve NaN: si un valor no se
puede calcular, devuelve None.
"""

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import kurtosis, norm, skew

# Fracción esperada con una normal de |z| > 2 (≈ 4,55 %) y de z < −2 (≈ 2,28 %).
EXPECTED_GT2 = 0.0455
EXPECTED_LT_M2 = 0.0228

# Un tramo con menos casos que esto se marca "pocos casos".
MIN_CASES = 10

# Número de tramos fijos de la tabla de fiabilidad (deciles).
N_BINS = 10

# Niveles de los cuantiles que se comparan con la normal.
QUANTILE_LEVELS = (0.01, 0.05, 0.5, 0.95, 0.99)

# Valor z del intervalo de confianza del 95 %.
Z_95 = 1.96

# Margen minúsculo para que 0,3·10 = 2,9999999… caiga en el tramo 3.
BIN_EPS = 1e-9


@dataclass
class BinRow:
    """Una fila de la tabla de fiabilidad (un tramo de PoP).

    - lo, hi: bordes del tramo (el último incluye PoP = 1,0).
    - n: casos en el tramo; n_eff: casos efectivos (n × deff).
    - mean_pop: PoP media del tramo; observed: tasa de acierto real.
    - ci_low, ci_high: intervalo de Wilson de 'observed'.
    - few: tramo con algún caso pero menos de MIN_CASES.
    - empty: tramo sin casos (se muestra "—").
    """

    lo: float
    hi: float
    n: int
    n_eff: float
    mean_pop: float | None
    observed: float | None
    ci_low: float | None
    ci_high: float | None
    few: bool
    empty: bool


@dataclass
class TailResult:
    """Diagnóstico de colas de los movimientos estandarizados z.

    Si el modelo lognormal fuera cierto, z sería una normal estándar:
    media 0, desviación 1, asimetría 0, curtosis en exceso 0, un 4,55 %
    de casos con |z| > 2 y un 2,28 % con z < −2.
    'quantiles' es un diccionario nivel → (cuantil empírico, cuantil normal).
    """

    n: int
    mean: float | None
    std: float | None
    skew: float | None
    excess_kurtosis: float | None
    frac_gt2: float | None
    frac_lt_m2: float | None
    quantiles: dict = field(default_factory=dict)


def _finite_or_none(value) -> float | None:
    """Convierte a float; si es NaN o infinito devuelve None."""
    value = float(value)
    if math.isfinite(value):
        return value
    return None


def wilson_interval(k, n, z: float = Z_95, deff: float = 1.0):
    """Intervalo de confianza de Wilson para la proporción k/n.

    'deff' (efecto de diseño, ≤ 1) multiplica la muestra: se calcula con
    n' = n·deff y la misma proporción. Así un tramo con casos solapados
    (menos información) tiene un intervalo más ancho. deff = 1 es el
    Wilson de siempre. Devuelve (bajo, alto) o None si no hay casos.
    """
    n_used = n * deff
    if n <= 0 or n_used <= 0:
        return None
    p = k / n
    z2 = z * z
    denominator = 1 + z2 / n_used
    center = (p + z2 / (2 * n_used)) / denominator
    half = z * math.sqrt(p * (1 - p) / n_used + z2 / (4 * n_used * n_used)) / denominator
    low = max(center - half, 0.0)
    high = min(center + half, 1.0)
    return low, high


def brier_score(pop, win) -> float | None:
    """Puntaje de Brier: media de (PoP − resultado)². 0 es perfecto."""
    pop = np.asarray(pop, dtype=float)
    win = np.asarray(win, dtype=float)
    if pop.size == 0:
        return None
    return float(np.mean((pop - win) ** 2))


def climatological_brier(win) -> float | None:
    """Brier de decir siempre la tasa media de acierto (referencia)."""
    win = np.asarray(win, dtype=float)
    if win.size == 0:
        return None
    rate = float(np.mean(win))
    return float(np.mean((rate - win) ** 2))


def brier_skill(pop, win) -> float | None:
    """Habilidad: 1 − Brier / Brier climatológico (> 0 = mejor que la media).

    None si no hay datos o si el Brier climatológico es 0 (todos ganan o
    todos pierden: no hay nada que distinguir).
    """
    score = brier_score(pop, win)
    reference = climatological_brier(win)
    if score is None or reference is None or reference <= 0:
        return None
    return 1.0 - score / reference


def calibration_bins(pop, win, deff: float = 1.0, min_cases: int = MIN_CASES) -> list[BinRow]:
    """Tabla de fiabilidad con 10 tramos fijos de PoP (siempre 10 filas).

    El tramo i cubre [i/10, (i+1)/10); PoP = 1,0 va al último tramo.
    Los tramos vacíos tienen media, observado e intervalo en None.
    """
    pop = np.asarray(pop, dtype=float)
    win = np.asarray(win, dtype=float)
    # Índice de tramo de cada caso (0..9).
    bins = np.floor(pop * N_BINS + BIN_EPS).astype(int)
    bins = np.clip(bins, 0, N_BINS - 1)

    rows = []
    for i in range(N_BINS):
        in_bin = bins == i
        n = int(np.sum(in_bin))
        lo = i / N_BINS
        hi = (i + 1) / N_BINS
        if n == 0:
            rows.append(BinRow(lo, hi, 0, 0.0, None, None, None, None, few=False, empty=True))
            continue
        wins = float(np.sum(win[in_bin]))
        interval = wilson_interval(wins, n, deff=deff)
        ci_low, ci_high = interval if interval is not None else (None, None)
        rows.append(
            BinRow(
                lo=lo,
                hi=hi,
                n=n,
                n_eff=n * deff,
                mean_pop=float(np.mean(pop[in_bin])),
                observed=wins / n,
                ci_low=ci_low,
                ci_high=ci_high,
                few=n < min_cases,
                empty=False,
            )
        )
    return rows


def max_deviation(rows: list[BinRow]) -> float | None:
    """Mayor |observado − PoP media| entre los tramos con casos suficientes.

    Ignora los tramos vacíos y los de pocos casos. None si no queda ninguno.
    """
    deviations = [
        abs(row.observed - row.mean_pop) for row in rows if not row.empty and not row.few
    ]
    if not deviations:
        return None
    return max(deviations)


def effective_n(n: int, years_analyzed: float, horizon_days: float) -> float:
    """N efectivo: como mucho, una ventana de H días que no se solape por vez.

    effective_n = min(N, años·365/H). Con N = 0, años = 0 o H ≤ 0 → 0.
    """
    if n <= 0 or years_analyzed <= 0 or horizon_days <= 0:
        return 0
    return min(float(n), years_analyzed * 365 / horizon_days)


def tail_diagnostics(z) -> TailResult:
    """Compara la distribución de z con una normal estándar.

    Se descartan los valores NaN o infinitos. Con una muestra vacía todos
    los estadísticos son None (nunca NaN).
    """
    z = np.asarray(z, dtype=float)
    z = z[np.isfinite(z)]
    n = int(z.size)
    if n == 0:
        return TailResult(0, None, None, None, None, None, None, {})

    std = _finite_or_none(np.std(z, ddof=1)) if n > 1 else None
    # Con datos constantes scipy avisa y devuelve NaN: lo convertimos en None.
    with np.errstate(all="ignore"):
        if n > 2 and np.ptp(z) > 0:
            skew_value = _finite_or_none(skew(z))
            kurt_value = _finite_or_none(kurtosis(z))
        else:
            skew_value = None
            kurt_value = None

    quantiles = {}
    for level in QUANTILE_LEVELS:
        quantiles[level] = (float(np.quantile(z, level)), float(norm.ppf(level)))

    return TailResult(
        n=n,
        mean=float(np.mean(z)),
        std=std,
        skew=skew_value,
        excess_kurtosis=kurt_value,
        frac_gt2=float(np.mean(np.abs(z) > 2)),
        frac_lt_m2=float(np.mean(z < -2)),
        quantiles=quantiles,
    )
