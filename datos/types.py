"""Tipos de datos de mercado: una cotización de opción y una foto del mercado.

Son dataclasses inmutables (frozen): solo guardan datos. No importan
pandas ni yfinance; la conversión desde Yahoo vive en otro módulo.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OptionQuote:
    """Cotización de una opción en un vencimiento.

    - kind: "call" o "put".
    - strike, bid, ask: en USD.
    - last: último precio negociado; solo informativo (nunca es la prima).
    - oi: interés abierto (open interest), número de contratos.
    - volume: contratos negociados hoy.
    - iv_yahoo: volatilidad implícita que publica Yahoo (fracción), solo
      como referencia; None si no viene.
    """

    kind: str
    strike: float
    bid: float
    ask: float
    last: float | None
    oi: int
    volume: int
    iv_yahoo: float | None

    @property
    def mid(self) -> float:
        """Precio medio entre bid y ask: es la prima que usa la app."""
        return (self.bid + self.ask) / 2


@dataclass(frozen=True)
class MarketSnapshot:
    """Foto del mercado de un subyacente en un momento dado.

    - ticker: etiqueta curada (p. ej. "SPX", "AAPL").
    - loaded_at: fecha y hora de la carga, con zona horaria.
    - spot: precio del subyacente (USD).
    - rate: tipo de interés libre de riesgo (fracción, 0.0412 = 4,12 %).
    - q: rentabilidad por dividendo (fracción) o None (índice o no disponible).
    - q_source: "yahoo", "indice" o "no_disponible".
    - chains: vencimiento ISO "YYYY-MM-DD" -> lista de cotizaciones líquidas.
    - source: "live" (recién descargado) o "cache" (leído del disco).
    """

    ticker: str
    loaded_at: datetime
    spot: float
    rate: float
    q: float | None
    q_source: str
    chains: dict[str, list[OptionQuote]]
    source: str
