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
from datos.history_cache import (
    covers,
    history_path,
    is_fresh,
    read_history,
    start_for_years,
    write_history,
)
from datos.history_service import (
    HistoryLoad,
    clean_history,
    history_age_text,
    load_history,
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
from datos.provider import HistoryProvider, MarketDataProvider
from datos.service import (
    age_text,
    cache_age_text,
    live_age_text,
    load_or_cache,
    load_snapshot,
    load_with_notices,
    rate_from_percent,
)
from datos.tickers import (
    CURATED_TICKERS,
    HISTORY_SYMBOLS,
    MANUAL_ENTRY,
    RATE_HISTORY_SYMBOL,
    history_symbols,
    resolve_ticker,
    ticker_options,
    tickers_for,
)
from datos.types import MarketSnapshot, OptionQuote, PriceHistory

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
    "CURATED_TICKERS",
    "MANUAL_ENTRY",
    "resolve_ticker",
    "ticker_options",
    "tickers_for",
    # Etapa C2: histórico del subyacente.
    "HISTORY_SYMBOLS",
    "HistoryProvider",
    "PriceHistory",
    "RATE_HISTORY_SYMBOL",
    "history_symbols",
    "covers",
    "history_path",
    "is_fresh",
    "read_history",
    "start_for_years",
    "write_history",
    "HistoryLoad",
    "clean_history",
    "history_age_text",
    "load_history",
]
