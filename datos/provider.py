"""Interfaz ("enchufe") que cumple cualquier proveedor de datos de mercado.

Un Protocol solo describe qué métodos debe tener un proveedor; no
contiene código. Así el resto del paquete funciona igual con Yahoo o
con un proveedor falso para los tests.
"""

from datetime import date
from typing import Protocol, runtime_checkable

from datos.types import PriceHistory


@runtime_checkable
class MarketDataProvider(Protocol):
    """Métodos que debe ofrecer un proveedor de datos de mercado."""

    def get_spot(self, ticker: str) -> float:
        """Precio actual del subyacente (USD)."""
        ...

    def get_expirations(self, ticker: str) -> list[str]:
        """Vencimientos disponibles, como texto ISO "YYYY-MM-DD"."""
        ...

    def get_chain(self, ticker: str, expiry: str) -> list[dict]:
        """Filas crudas de la cadena de opciones de un vencimiento."""
        ...

    def get_rate(self) -> float:
        """Tipo de interés libre de riesgo (fracción, 0.0412 = 4,12 %)."""
        ...

    def get_dividend_yield(self, ticker: str) -> float | None:
        """Rentabilidad por dividendo (fracción) o None si no hay dato."""
        ...


@runtime_checkable
class HistoryProvider(Protocol):
    """Proveedor de histórico diario de precios (Etapa C2).

    Es una interfaz APARTE de MarketDataProvider: así el contrato de las
    opciones (C1) no cambia. Un proveedor puede cumplir las dos.
    """

    def get_history(self, symbol: str, start: date, end: date) -> PriceHistory:
        """Precios diarios de `symbol` entre `start` (incluido) y `end` (excluido).

        Lanza NetworkError, RateLimitError o EmptyDataError (sin datos).
        """
        ...
