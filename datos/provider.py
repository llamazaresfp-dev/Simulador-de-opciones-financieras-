"""Interfaz ("enchufe") que cumple cualquier proveedor de datos de mercado.

Un Protocol solo describe qué métodos debe tener un proveedor; no
contiene código. Así el resto del paquete funciona igual con Yahoo o
con un proveedor falso para los tests.
"""

from typing import Protocol, runtime_checkable


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
