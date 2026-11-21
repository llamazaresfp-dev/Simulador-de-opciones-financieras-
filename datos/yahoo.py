"""Adaptador de Yahoo Finance: el ÚNICO módulo que habla con yfinance.

Cumple la interfaz MarketDataProvider (ver provider.py):
- get_spot: precio del subyacente; se prefiere `fast_info` (más ligero)
  y, si no trae dato, `info["regularMarketPrice"]`.
- get_expirations: vencimientos ISO "YYYY-MM-DD".
- get_chain: tablas de pandas (calls y puts) -> lista de dicts con las
  claves que entiende `clean_row`: kind, strike, bid, ask, oi, last,
  volume, iv_yahoo. Los NaN se convierten en None.
- get_rate: ^IRX llega en porcentaje (4.12) -> fracción (0.0412).
- get_dividend_yield: `trailingAnnualDividendYield` (fracción), NO
  `dividendYield` (que llega en porcentaje).

`yfinance` se importa DENTRO del constructor: así `import datos` no carga
yfinance ni pandas (la app arranca rápido y los tests no lo necesitan).
Este módulo no importa pandas: solo usa los métodos de las tablas que
devuelve yfinance.

Todos los fallos se traducen a errores del paquete con mensaje en
español: límite de solicitudes (HTTP 429) -> RateLimitError; problemas
de conexión o timeout (curl_cffi, requests, sockets) -> NetworkError;
respuesta vacía o con formato inesperado -> EmptyDataError.
"""

import math
from pathlib import Path

from datos.errors import DatosError, EmptyDataError, NetworkError, RateLimitError
from datos.service import rate_from_percent

# Segundos máximos por solicitud HTTP (yfinance usa 30 por defecto).
DEFAULT_TIMEOUT = 10

# Carpeta de la caché de zonas horarias de yfinance (raíz del repo).
DEFAULT_TZ_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache_datos" / "yfinance"

# Símbolo de Yahoo del tipo a 13 semanas (en porcentaje).
RATE_SYMBOL = "^IRX"

# Columnas de yfinance -> claves de nuestras filas crudas.
CHAIN_COLUMNS = {
    "strike": "strike",
    "bid": "bid",
    "ask": "ask",
    "lastPrice": "last",
    "openInterest": "oi",
    "volume": "volume",
    "impliedVolatility": "iv_yahoo",
}

# Nombres de errores de yfinance que significan "no hay datos".
_EMPTY_ERROR_NAMES = {
    "YFTickerMissingError",
    "YFPricesMissingError",
    "YFTzMissingError",
    "YFEarningsDateMissing",
}

# Nombres de errores de red (curl_cffi, requests, urllib3...).
_NETWORK_ERROR_NAMES = {
    "ConnectionError",
    "ConnectTimeout",
    "ReadTimeout",
    "Timeout",
    "TimeoutError",
    "DNSError",
    "ProxyError",
    "SSLError",
    "ChunkedEncodingError",
    "RemoteDisconnected",
    "CurlError",
}


# --- Sesión HTTP con timeout ---


def build_session(timeout):
    """Crea la sesión HTTP para yfinance con un timeout fijo por solicitud.

    yfinance pide cada URL con `timeout=30`; esta sesión lo sustituye por
    `timeout` en TODAS las solicitudes (también las de cookie/crumb).
    Usa curl_cffi (como yfinance) y, si no está, requests.
    """
    try:
        from curl_cffi import requests as backend

        options = {"impersonate": "chrome"}
    except ImportError:
        import requests as backend

        options = {}

    class TimeoutSession(backend.Session):
        """Sesión que impone el timeout del adaptador."""

        def request(self, method, url, *args, **kwargs):
            kwargs["timeout"] = timeout
            return super().request(method, url, *args, **kwargs)

    return TimeoutSession(**options)


# --- Conversión de valores ---


def _plain_number(value) -> float | None:
    """Número de numpy/pandas -> float de Python; NaN, NA o texto -> None."""
    if value is None or isinstance(value, (bool, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value) -> float | None:
    """Número finito y > 0, o None."""
    number = _plain_number(value)
    if number is None or number <= 0:
        return None
    return number


def _read_fast_info(fast_info, key, attribute):
    """Lee `fast_info[key]` o, si no se puede, `fast_info.attribute`."""
    try:
        return fast_info[key]
    except (KeyError, TypeError, AttributeError, ValueError, IndexError):
        return getattr(fast_info, attribute, None)


def _frame_to_rows(frame, kind) -> list[dict]:
    """Una tabla de pandas (calls o puts) -> lista de filas crudas."""
    rows = []
    columns = [column for column in CHAIN_COLUMNS if column in frame.columns]
    for record in frame.to_dict("records"):
        row = {"kind": kind}
        for column in columns:
            row[CHAIN_COLUMNS[column]] = _plain_number(record.get(column))
        rows.append(row)
    return rows


# --- Traducción de errores ---


def _is_rate_limit(error) -> bool:
    """¿El error es un límite de solicitudes (HTTP 429)?"""
    if type(error).__name__ == "YFRateLimitError":
        return True
    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True
    text = str(error).lower()
    return "too many requests" in text or "rate limited" in text


def _is_network(error) -> bool:
    """¿El error es de conexión o de timeout?"""
    if isinstance(error, (OSError, TimeoutError, ConnectionError)):
        return True
    return any(cls.__name__ in _NETWORK_ERROR_NAMES for cls in type(error).__mro__)


def _is_empty(error) -> bool:
    """¿El error significa respuesta vacía o con formato inesperado?"""
    if type(error).__name__ in _EMPTY_ERROR_NAMES:
        return True
    return isinstance(error, (KeyError, IndexError, ValueError, TypeError, AttributeError))


def to_datos_error(error) -> DatosError:
    """Traduce cualquier error de yfinance/red a un DatosError en español."""
    if isinstance(error, DatosError):
        return error
    if _is_rate_limit(error):
        return RateLimitError()
    if _is_network(error):
        return NetworkError()
    if _is_empty(error):
        return EmptyDataError()
    # Error desconocido: se trata como fallo del proveedor (red).
    return NetworkError()


# --- Proveedor ---


class YahooProvider:
    """Proveedor de datos reales de Yahoo Finance (~15 min de retraso).

    Parámetros:
    - tz_cache_dir: carpeta de la caché de zonas horarias de yfinance; por
      defecto `<repo>/.cache_datos/yfinance`. Los tests pasan `tmp_path`.
    - timeout: segundos máximos por solicitud HTTP (por defecto 10).
    - yf_module: módulo yfinance a usar (los tests pasan uno falso).
    - session: sesión HTTP; por defecto una con el timeout impuesto.
    """

    def __init__(self, tz_cache_dir=None, timeout=DEFAULT_TIMEOUT, yf_module=None, session=None):
        if yf_module is None:
            import yfinance as yf_module  # solo aquí: `import datos` no lo carga
        self._yf = yf_module
        self.timeout = timeout
        self.tz_cache_dir = Path(tz_cache_dir) if tz_cache_dir is not None else DEFAULT_TZ_CACHE_DIR
        self.tz_cache_dir.mkdir(parents=True, exist_ok=True)
        self._yf.set_tz_cache_location(str(self.tz_cache_dir))
        self._session = session if session is not None else build_session(timeout)
        # Un objeto Ticker por símbolo: yfinance reutiliza lo ya descargado
        # (p. ej. la lista de vencimientos), así se hacen menos solicitudes.
        self._tickers = {}

    def _ticker(self, symbol):
        """Objeto Ticker de yfinance para `symbol` (se reutiliza)."""
        if symbol not in self._tickers:
            self._tickers[symbol] = self._yf.Ticker(symbol, session=self._session)
        return self._tickers[symbol]

    def _call(self, action):
        """Ejecuta `action()` y traduce cualquier error a DatosError."""
        try:
            return action()
        except Exception as error:  # except amplio: el adaptador nunca deja escapar otros errores
            translated = to_datos_error(error)
            if translated is error:
                raise
            raise translated from error

    # --- Interfaz MarketDataProvider ---

    def get_spot(self, ticker) -> float:
        """Precio actual: `fast_info` primero; si no hay dato, `info`."""

        def fetch():
            yf_ticker = self._ticker(ticker)
            price = _positive(_read_fast_info(yf_ticker.fast_info, "lastPrice", "last_price"))
            if price is None:
                price = _positive(yf_ticker.info.get("regularMarketPrice"))
            if price is None:
                raise EmptyDataError()
            return price

        return self._call(fetch)

    def get_expirations(self, ticker) -> list[str]:
        """Vencimientos disponibles como texto ISO "YYYY-MM-DD"."""
        return self._call(lambda: [str(expiry) for expiry in self._ticker(ticker).options])

    def get_chain(self, ticker, expiry) -> list[dict]:
        """Filas crudas (calls y puts) de un vencimiento."""

        def fetch():
            chain = self._ticker(ticker).option_chain(expiry)
            calls = getattr(chain, "calls", None)
            puts = getattr(chain, "puts", None)
            if calls is None and puts is None:
                raise EmptyDataError()
            rows = []
            if calls is not None:
                rows.extend(_frame_to_rows(calls, "call"))
            if puts is not None:
                rows.extend(_frame_to_rows(puts, "put"))
            return rows

        return self._call(fetch)

    def get_rate(self) -> float:
        """Tipo libre de riesgo: ^IRX (porcentaje) -> fracción."""

        def fetch():
            fast_info = self._ticker(RATE_SYMBOL).fast_info
            value = _plain_number(_read_fast_info(fast_info, "lastPrice", "last_price"))
            if value is None:
                raise EmptyDataError()
            return rate_from_percent(value)

        return self._call(fetch)

    def get_dividend_yield(self, ticker) -> float | None:
        """Dividend yield (fracción) desde `trailingAnnualDividendYield`.

        Sin dato (o dato inválido) -> None. Si `info` falla se lanza un
        DatosError; el servicio lo trata como "q no disponible" y avisa.
        """

        def fetch():
            info = self._ticker(ticker).info
            value = _plain_number(info.get("trailingAnnualDividendYield"))
            if value is None or value < 0:
                return None
            return value

        return self._call(fetch)
