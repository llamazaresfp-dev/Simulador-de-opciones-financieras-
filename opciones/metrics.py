"""Métricas exactas al vencimiento: beneficio máx., pérdida máx. y breakevens.

Idea clave: al vencimiento el P&L es "lineal a tramos". Entre dos strikes
consecutivos cada opción vale 0 o (S − K) o (K − S), así que la suma es
una recta. Solo cambia de pendiente (o da un pequeño salto por la
comisión de cierre) justo en los strikes. Esos puntos son los "kinks".

En vez de reescribir fórmulas, MUESTREAMOS la misma función pnl_expiry
que dibuja el gráfico: dos puntos dentro de cada tramo bastan para
conocer su recta. Así gráfico y métricas tienen una única fuente de
verdad y las comisiones entran solas, sin duplicar lógica.

"Ilimitado": a la derecha del último strike el P&L es una recta que
sigue para siempre. Si sube, el beneficio no tiene techo
(profit_unlimited); si baja, la pérdida no tiene suelo (loss_unlimited).
En ese caso el valor numérico correspondiente es None. A la izquierda
no hay problema: el precio no puede bajar de 0.
"""

from dataclasses import dataclass, field

from opciones.models import CommissionSettings, Leg, Market
from opciones.payoff import pnl_expiry

# Pendiente por debajo de la cual consideramos un tramo "plano".
SLOPE_TOL = 1e-7
# P&L por debajo del cual (en valor absoluto) lo consideramos cero.
ZERO_TOL = 1e-7
# Dos breakevens más cerca que esto son el mismo punto.
DEDUPE_TOL = 1e-6


@dataclass
class Metrics:
    """Resultado de las métricas al vencimiento.

    - best_pnl: beneficio máximo (USD); None si es ilimitado.
    - worst_pnl: peor resultado (USD, negativo si es pérdida); None si
      la pérdida es ilimitada.
    - profit_unlimited / loss_unlimited: True si no hay techo / suelo.
    - breakevens: precios donde el P&L cruza el cero (ordenados).
    """

    best_pnl: float | None
    worst_pnl: float | None
    profit_unlimited: bool
    loss_unlimited: bool
    breakevens: list[float] = field(default_factory=list)


@dataclass
class _Piece:
    """Un tramo recto del P&L: P(S) = slope × S + intercept, para start < S < end.

    end es None en el último tramo (la cola que sigue hasta el infinito).
    """

    start: float
    end: float | None
    slope: float
    intercept: float

    def value_at(self, S: float) -> float:
        """Valor de la recta en S (límite lateral si S es un extremo)."""
        return self.slope * S + self.intercept

    def is_flat_zero(self) -> bool:
        """True si el tramo entero vale cero (P&L plano en 0)."""
        return abs(self.slope) < SLOPE_TOL and abs(self.value_at(self.start)) < ZERO_TOL


def _kinks(legs: list[Leg]) -> list[float]:
    """Puntos donde puede cambiar la recta: 0 y cada strike distinto, ordenados."""
    strikes = {float(leg.strike) for leg in legs if leg.kind != "stock" and leg.strike > 0}
    return [0.0] + sorted(strikes)


def _line_through(P, x1: float, x2: float) -> tuple[float, float]:
    """Pendiente e intersección de la recta que pasa por (x1, P(x1)) y (x2, P(x2))."""
    y1, y2 = P(x1), P(x2)
    slope = (y2 - y1) / (x2 - x1)
    return slope, y1 - slope * x1


def _pieces(P, kinks: list[float]) -> list[_Piece]:
    """Construye los tramos rectos muestreando P en dos puntos interiores.

    Usamos puntos INTERIORES (a un tercio y dos tercios del tramo) para
    no caer justo en un strike, donde la comisión de cierre da un salto.
    """
    pieces = []
    for a, b in zip(kinks[:-1], kinks[1:]):
        width = b - a
        slope, intercept = _line_through(P, a + width / 3, a + 2 * width / 3)
        pieces.append(_Piece(a, b, slope, intercept))
    # Cola derecha: más allá del último strike.
    last = kinks[-1]
    slope, intercept = _line_through(P, last + 1.0, last + 2.0)
    pieces.append(_Piece(last, None, slope, intercept))
    return pieces


def _piece_root(piece: _Piece) -> float | None:
    """Precio donde la recta del tramo vale 0, si cae dentro del tramo.

    Un tramo plano no tiene un cruce concreto (ni aunque valga 0).
    Aceptamos la raíz justo en un extremo: así no perdemos un cruce que
    ocurre exactamente en un strike.
    """
    if abs(piece.slope) < SLOPE_TOL:
        return None
    root = -piece.intercept / piece.slope
    margin = 1e-9 * (1.0 + abs(root))
    if root < piece.start - margin:
        return None
    if piece.end is not None and root > piece.end + margin:
        return None
    return min(max(root, piece.start), piece.end if piece.end is not None else root)


def _kink_is_breakeven(value: float, left: _Piece | None, right: _Piece) -> bool:
    """¿Es el kink un breakeven?

    - Si el P&L vale exactamente 0 en el kink (salvo que esté en medio
      de una meseta en cero, donde no hay un cruce concreto).
    - Si el P&L "salta" de un signo al otro justo en el kink (por la
      comisión de cierre): límite izquierdo y derecho de signo opuesto.
    """
    K = right.start
    if abs(value) < ZERO_TOL:
        inside_zero_plateau = right.is_flat_zero() and (left is None or left.is_flat_zero())
        return not inside_zero_plateau
    if left is None:
        return False
    return left.value_at(K) * right.value_at(K) < 0


def _dedupe(values: list[float]) -> list[float]:
    """Ordena y elimina breakevens repetidos (más cerca que DEDUPE_TOL)."""
    result = []
    for v in sorted(values):
        if not result or v - result[-1] > DEDUPE_TOL:
            result.append(v)
    return result


def compute_metrics(legs: list[Leg], market: Market, settings: CommissionSettings) -> Metrics:
    """Calcula beneficio máx., pérdida máx. y breakevens exactos al vencimiento."""

    def P(S: float) -> float:
        return pnl_expiry(legs, market, settings, S)

    kinks = _kinks(legs)
    pieces = _pieces(P, kinks)
    tail = pieces[-1]

    # Candidatos a máximo/mínimo: valores alcanzados en S = 0 y en cada
    # strike, más los límites laterales en los extremos de cada tramo
    # (con el salto de comisión el valor en K y sus vecinos difieren).
    candidates = [P(K) for K in kinks]
    for piece in pieces:
        candidates.append(piece.value_at(piece.start))
        if piece.end is not None:
            candidates.append(piece.value_at(piece.end))

    profit_unlimited = tail.slope > SLOPE_TOL
    loss_unlimited = tail.slope < -SLOPE_TOL
    best = None if profit_unlimited else float(max(candidates))
    worst = None if loss_unlimited else float(min(candidates))

    # Breakevens: raíces dentro de los tramos + kinks que cruzan el cero.
    breakevens = []
    for piece in pieces:
        root = _piece_root(piece)
        if root is not None:
            breakevens.append(root)
    for i, K in enumerate(kinks):
        left = pieces[i - 1] if i > 0 else None
        if _kink_is_breakeven(P(K), left, pieces[i]):
            breakevens.append(K)

    return Metrics(
        best_pnl=best,
        worst_pnl=worst,
        profit_unlimited=profit_unlimited,
        loss_unlimited=loss_unlimited,
        breakevens=_dedupe(breakevens),
    )
