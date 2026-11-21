"""Lista curada de tickers por tipo de subyacente (Etapa C1, AC-C1-1).

Solo se ofrecen estos tickers: todos tienen opciones líquidas. No hay
campo libre para escribir otro ticker.

- La etiqueta curada es lo que ve el usuario ("SPX") y el nombre del
  archivo de caché (SPX.json).
- El símbolo de Yahoo es lo que entiende el proveedor ("^SPX").
"""

# Opción del selector que significa "no cargar datos: escribo yo los valores".
MANUAL_ENTRY = "Entrada manual"

# Tickers curados por tipo de subyacente (mismos nombres que en app.py).
CURATED_TICKERS = {
    "Acción": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA"],
    "ETF": ["SPY", "QQQ", "IWM"],
    "Índice": ["SPX"],
}

# Etiquetas cuyo símbolo en Yahoo es distinto (los índices llevan "^").
YAHOO_SYMBOLS = {"SPX": "^SPX"}


def tickers_for(kind) -> list[str]:
    """Tickers curados de un tipo de subyacente (lista vacía si no existe)."""
    return list(CURATED_TICKERS.get(kind, []))


def ticker_options(kind) -> list[str]:
    """Opciones del selector de ticker: "Entrada manual" + los curados del tipo."""
    return [MANUAL_ENTRY] + tickers_for(kind)


def resolve_ticker(kind, name) -> str | None:
    """Símbolo de Yahoo de un ticker curado, o None.

    Devuelve None para "Entrada manual" y para cualquier ticker que no
    esté en la lista curada de ese tipo (así nunca se pide otro).
    """
    if name not in CURATED_TICKERS.get(kind, []):
        return None
    return YAHOO_SYMBOLS.get(name, name)
