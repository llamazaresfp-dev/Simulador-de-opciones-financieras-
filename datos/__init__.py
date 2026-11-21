"""Paquete datos/: datos de mercado en directo para el constructor.

Aquí solo se reexporta lo público. Este paquete NO importa yfinance,
pandas ni streamlit: el único módulo que usará yfinance es el
adaptador de Yahoo, y lo importará dentro de su constructor.
"""

from datos.errors import (
    MSG_EMPTY,
    MSG_NETWORK,
    MSG_NO_LIQUID,
    MSG_RATE_LIMIT,
    DatosError,
    EmptyDataError,
    NetworkError,
    RateLimitError,
)
from datos.provider import MarketDataProvider
from datos.types import MarketSnapshot, OptionQuote

__all__ = [
    "DatosError",
    "EmptyDataError",
    "MSG_EMPTY",
    "MSG_NETWORK",
    "MSG_NO_LIQUID",
    "MSG_RATE_LIMIT",
    "MarketDataProvider",
    "MarketSnapshot",
    "NetworkError",
    "OptionQuote",
    "RateLimitError",
]
