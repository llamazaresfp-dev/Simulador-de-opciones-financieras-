"""Caché local del histórico diario: un JSON por ticker (Etapa C2).

Dónde: `.cache_datos/history/<ETIQUETA>.json` (la carpeta ya la ignora
git). La tasa ^IRX va en `history/IRX.json` (nunca `^IRX.json`).

Formato (`schema_version` 1):
    schema_version, ticker, fetched_at (fecha y hora con zona),
    requested_start (fecha ISO con la que se descargó, o null),
    dates, close, adj_close (listas de la misma longitud),
    dividends (lista de pares [fecha ISO, importe]).

Reglas:
- Escritura ATÓMICA (reutiliza `_atomic_write_json` de datos.cache).
- Lectura defensiva: si falta el archivo, está corrupto, es de otra
  versión o tiene campos mal formados -> None ("sin caché").
- Fresca (`is_fresh`): se descargó el mismo día de mercado que hoy, o su
  último dato ya llega a la última sesión cerrada (día hábil anterior a
  hoy; no se conocen los festivos).
- Cubre el tramo pedido (`covers`, IP-10): su primer dato es como mucho
  7 días posterior al inicio pedido, o se descargó pidiendo un inicio
  igual o anterior (fuente con menos historia de la pedida).
- `start_for_years` es el ÚNICO lugar donde se calcula el inicio del
  tramo: hoy − (años + 1) años naturales.

Este módulo no modifica datos/cache.py: solo importa sus ayudantes.
Solo usa la biblioteca estándar.
"""

import json
import math
import numbers
from datetime import date, datetime, timedelta
from pathlib import Path

from datos.cache import DEFAULT_CACHE_DIR, _atomic_write_json, _file_label, market_today
from datos.types import PriceHistory

# Versión del formato del archivo del histórico.
HISTORY_SCHEMA_VERSION = 1

# Subcarpeta del histórico dentro de la carpeta de caché.
HISTORY_DIR_NAME = "history"

# Días de tolerancia de `covers`: el primer dato puede caer algo después
# del inicio pedido (fin de semana, festivo).
COVER_TOLERANCE_DAYS = 7

MSG_HISTORY_WRITE_FAILED = "No se pudo guardar el histórico en disco: {error}"


# --- Ruta del archivo ---


def history_path(label, cache_dir=None) -> Path:
    """Ruta del histórico de una etiqueta: <cache_dir>/history/<ETIQUETA>.json.

    "^SPX" -> SPX.json, "^IRX" -> IRX.json. ValueError si la etiqueta no
    sirve como nombre de archivo (error de programación).
    """
    folder = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    return folder / HISTORY_DIR_NAME / f"{_file_label(label)}.json"


# --- Conversión de fechas ---


def _as_date(value) -> date:
    """Fecha desde un `date` o un texto ISO "YYYY-MM-DD"."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _iso_date_or_none(value) -> str | None:
    """Texto ISO de una fecha válida, o None si no lo es."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _finite_number(value) -> float | None:
    """Número real finito (no bool), o None."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


# --- Escritura ---


def write_history(history, fetched_at, requested_start, cache_dir=None) -> tuple[bool, str | None]:
    """Guarda un histórico en la caché. Devuelve (escrito, aviso o None).

    - history: PriceHistory; su `ticker` es la etiqueta del archivo
      ("SPX", "^IRX").
    - fetched_at: fecha y hora de la descarga, CON zona horaria (sin zona
      -> ValueError, es un error de programación).
    - requested_start: inicio del tramo pedido (date) o None.
    Si falla el disco devuelve (False, aviso) y el archivo viejo queda.
    """
    if not isinstance(fetched_at, datetime) or fetched_at.utcoffset() is None:
        raise ValueError("fetched_at debe ser un datetime con zona horaria")
    path = history_path(history.ticker, cache_dir)
    data = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "ticker": history.ticker,
        "fetched_at": fetched_at.isoformat(),
        "requested_start": None if requested_start is None else _as_date(requested_start).isoformat(),
        "dates": list(history.dates),
        "close": list(history.close),
        "adj_close": list(history.adj_close),
        "dividends": [[day, amount] for day, amount in history.dividends],
    }
    try:
        _atomic_write_json(path, data)
    except (OSError, ValueError) as error:
        return False, MSG_HISTORY_WRITE_FAILED.format(error=error)
    return True, None


# --- Lectura ---


def _read_numbers(values) -> list[float] | None:
    """Lista de números finitos, o None si algún valor no lo es."""
    if not isinstance(values, list):
        return None
    numbers_read = [_finite_number(value) for value in values]
    if any(number is None for number in numbers_read):
        return None
    return numbers_read


def _read_dates(values) -> list[str] | None:
    """Lista de fechas ISO válidas, o None si alguna no lo es."""
    if not isinstance(values, list):
        return None
    dates = [_iso_date_or_none(value) for value in values]
    if any(day is None for day in dates):
        return None
    return dates


def _read_dividends(values) -> list[tuple[str, float]] | None:
    """Lista de pares (fecha ISO, importe), o None si alguno está mal."""
    if not isinstance(values, list):
        return None
    dividends = []
    for item in values:
        if not isinstance(item, list) or len(item) != 2:
            return None
        day = _iso_date_or_none(item[0])
        amount = _finite_number(item[1])
        if day is None or amount is None:
            return None
        dividends.append((day, amount))
    return dividends


def _read_fetched_at(value) -> datetime | None:
    """Fecha y hora con zona, o None si falta, está mal o no tiene zona."""
    try:
        fetched_at = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if fetched_at.utcoffset() is None:
        return None
    return fetched_at


def read_history(label, cache_dir=None):
    """Lee el histórico guardado de una etiqueta.

    Devuelve (PriceHistory con source="cache", fetched_at, requested_start)
    o None si no hay archivo útil. `requested_start` es None en cachés
    viejas que no guardaban el campo. Nunca lanza (salvo etiqueta no
    válida, que es un error de programación).
    """
    try:
        with open(history_path(label, cache_dir), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != HISTORY_SCHEMA_VERSION:
        return None

    ticker = data.get("ticker")
    fetched_at = _read_fetched_at(data.get("fetched_at"))
    dates = _read_dates(data.get("dates"))
    close = _read_numbers(data.get("close"))
    adj_close = _read_numbers(data.get("adj_close"))
    dividends = _read_dividends(data.get("dividends"))
    raw_start = data.get("requested_start")
    requested_start = None
    if raw_start is not None:
        start_iso = _iso_date_or_none(raw_start)
        if start_iso is None:
            return None
        requested_start = date.fromisoformat(start_iso)

    if (
        not isinstance(ticker, str)
        or fetched_at is None
        or dates is None
        or close is None
        or adj_close is None
        or dividends is None
        or not dates
        or not len(dates) == len(close) == len(adj_close)
    ):
        return None

    history = PriceHistory(
        ticker=ticker,
        dates=tuple(dates),
        close=tuple(close),
        adj_close=tuple(adj_close),
        dividends=tuple(dividends),
        source="cache",
        loaded_at=fetched_at,
    )
    return history, fetched_at, requested_start


# --- Frescura y cobertura ---


def last_closed_session(today) -> date:
    """Último día hábil (lunes a viernes) ANTERIOR a la fecha de mercado `today`."""
    day = market_today(today) - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def is_fresh(fetched_at, last_date, today) -> bool:
    """¿Sirve la caché sin volver a descargar?

    Verdadero si se descargó el mismo día de mercado (Nueva York) que
    `today`, o si su último dato (`last_date`, fecha o texto ISO) ya llega
    a la última sesión cerrada (día hábil anterior a `today`).
    """
    market_date = market_today(today)
    if market_today(fetched_at) == market_date:
        return True
    return _as_date(last_date) >= last_closed_session(market_date)


def covers(first_date, requested_start, start, tolerance_days=COVER_TOLERANCE_DAYS) -> bool:
    """¿El histórico guardado cubre el tramo que empieza en `start`? (IP-10)

    - Sí, si su primer dato (`first_date`) no es posterior a
      `start + tolerance_days` días (inicio en fin de semana o festivo).
    - Sí, si se descargó pidiendo un inicio (`requested_start`) igual o
      anterior a `start`: la fuente no tiene más historia, y volver a
      descargar no traería nada nuevo.
    - `requested_start` None (caché vieja) se ignora.
    Fechas como `date` o texto ISO.
    """
    start = _as_date(start)
    if _as_date(first_date) <= start + timedelta(days=tolerance_days):
        return True
    return requested_start is not None and _as_date(requested_start) <= start


def start_for_years(today, years) -> date:
    """Inicio del tramo a descargar: hoy − (años + 1) años naturales.

    El año extra es el calentamiento (ventanas de volatilidad y de μ).
    Se usan años naturales (nunca "× 365 días"); el 29 de febrero pasa
    al 28 si el año de destino no es bisiesto.
    """
    market_date = market_today(today)
    year = market_date.year - (years + 1)
    try:
        return market_date.replace(year=year)
    except ValueError:
        return market_date.replace(year=year, day=28)
