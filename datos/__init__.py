"""Paquete datos/: datos de mercado en directo para el constructor.

Aquí solo se reexporta lo público. Este paquete NO importa yfinance,
pandas ni streamlit: el único módulo que usará yfinance es el
adaptador de Yahoo, y lo importará dentro de su constructor.
"""

from datos.cache import (
    is_richer_or_equal,
    read_snapshot,
    richness,
    write_snapshot,
)
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
from datos.fake import FakeProvider
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
from datos.service import (
    age_text,
    cache_age_text,
    live_age_text,
    load_or_cache,
    load_snapshot,
    load_with_notices,
    rate_from_percent,
)
from datos.types import MarketSnapshot, OptionQuote

# yahoo.py importa yfinance solo dentro del constructor de YahooProvider,
# así que reexportarlo aquí no carga yfinance ni pandas.
from datos.yahoo import YahooProvider

__all__ = [
    "FakeProvider",
    "age_text",
    "cache_age_text",
    "live_age_text",
    "load_or_cache",
    "load_snapshot",
    "load_with_notices",
    "rate_from_percent",
    "is_richer_or_equal",
    "read_snapshot",
    "richness",
    "write_snapshot",
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
    "YahooProvider",
]
