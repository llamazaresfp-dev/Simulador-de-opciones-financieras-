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
from datos.filters import (
    DEFAULT_RULES,
    EPS,
    LiquidityRules,
    clean_row,
    dedupe,
    filter_chain,
    is_expiry_in_window,
)
from datos.provider import MarketDataProvider
from datos.types import MarketSnapshot, OptionQuote

__all__ = [
    "DEFAULT_RULES",
    "EPS",
    "LiquidityRules",
    "clean_row",
    "dedupe",
    "filter_chain",
    "is_expiry_in_window",
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
