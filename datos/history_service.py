"""Servicio del histórico: limpia, decide caché o descarga y trae la tasa.

Pasos de `load_history(provider, label, years)` (Etapa C2):
1. Tramo pedido: desde `start_for_years(hoy, years)` (años + 1 naturales,
   el año extra es el calentamiento) hasta mañana (fin exclusivo, como
   Yahoo).
2. Subyacente: si la caché está fresca Y cubre el tramo, se usa sin red.
   Si no, se descarga el tramo completo. Para SPX se prueba ^GSPC y, solo
   si viene vacío, ^SPX; un error de red o un 429 NO prueba el siguiente.
   Lo descargado se limpia (`clean_history`) y se guarda en la caché.
3. Tasa ^IRX: misma regla de caché y mismo tramo. Llega en porcentaje y
   se convierte aquí a fracción (4.12 -> 0.0412). Si falla, NO es fatal:
   se usa la tasa guardada si la hay o, si no, `rates = None` y aviso
   (la app usa entonces la tasa constante de la barra lateral).
4. Sin red: se usa la caché que haya (aunque sea vieja o no cubra) con un
   aviso de antigüedad; sin caché, DatosError en español.

El reloj es inyectable (`today`, `now`); las pruebas siempre lo fijan.
"""

import math
import numbers
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from datos.cache import MARKET_TZ, market_today
from datos.errors import DatosError, EmptyDataError
from datos.history_cache import covers, is_fresh, read_history, start_for_years, write_history
from datos.service import rate_from_percent
from datos.tickers import RATE_HISTORY_SYMBOL, history_symbols
from datos.types import PriceHistory

# Años que se pueden pedir (control "años" de la pestaña Backtest).
MIN_YEARS = 1
MAX_YEARS = 15

# Avisos para el usuario.
MSG_RATE_HISTORY_MISSING = (
    "No se pudo cargar el histórico de la tasa (^IRX): "
    "se usa la tasa constante de la barra lateral."
)
MSG_RATE_FROM_CACHE = "No se pudo actualizar la tasa (^IRX): se usa la tasa del {age}."
MSG_USING_HISTORY_CACHE = "Se usa el {age}."
MSG_NO_HISTORY_CACHE = "No hay histórico guardado de este subyacente."


@dataclass(frozen=True)
class HistoryLoad:
    """Resultado de cargar el histórico de un subyacente.

    - history: precios limpios del subyacente (ticker = etiqueta curada).
    - rates: histórico de ^IRX ya en FRACCIÓN, o None si no hay.
    - source: "live" (descargado ahora) o "cache" (leído del disco).
    - loaded_at: cuándo se descargó (con zona).
    - symbol: símbolo de Yahoo que respondió ("^GSPC"), None si es caché.
    - requested_start: inicio del tramo con el que se descargó (IP-11);
      None solo con una caché vieja que no guardaba el dato.
    """

    history: PriceHistory
    rates: PriceHistory | None
    source: str
    loaded_at: datetime
    symbol: str | None
    requested_start: date | None


# --- Limpieza ---


def _finite(value) -> float | None:
    """Número real finito (no bool), o None."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _valid_iso(value) -> str | None:
    """Texto ISO de una fecha válida, o None."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _valid_price(value, allow_non_positive) -> float | None:
    """Precio finito (y > 0 salvo permiso), o None."""
    number = _finite(value)
    if number is None or (number <= 0 and not allow_non_positive):
        return None
    return number


def clean_history(history, today, allow_non_positive=False) -> PriceHistory:
    """Limpia un histórico. Nunca lanza.

    - Descarta la fila de hoy (puede estar a medias con el mercado
      abierto) y las futuras; `today` es la fecha de mercado.
    - Descarta filas con fecha no válida o con `close`/`adj_close` NaN,
      no numéricos o <= 0 (`allow_non_positive=True` para la tasa, que
      puede valer 0).
    - De una fecha repetida se queda la primera fila.
    - Ordena por fecha ascendente.
    - Dividendos: solo importes > 0 con fecha válida anterior a hoy.
    """
    today_iso = market_today(today).isoformat()
    rows = {}
    for day, close, adj in zip(history.dates, history.close, history.adj_close):
        day = _valid_iso(day)
        close = _valid_price(close, allow_non_positive)
        adj = _valid_price(adj, allow_non_positive)
        if day is None or close is None or adj is None or day >= today_iso or day in rows:
            continue
        rows[day] = (close, adj)

    dividends = []
    for item in history.dividends:
        try:
            day, amount = item
        except (TypeError, ValueError):
            continue
        day = _valid_iso(day)
        amount = _finite(amount)
        if day is not None and amount is not None and amount > 0 and day < today_iso:
            dividends.append((day, amount))

    dates = sorted(rows)
    return replace(
        history,
        dates=tuple(dates),
        close=tuple(rows[day][0] for day in dates),
        adj_close=tuple(rows[day][1] for day in dates),
        dividends=tuple(sorted(dividends)),
    )


# --- Textos de antigüedad ---


def history_age_text(load, now=None) -> str:
    """Texto de antigüedad del histórico, con la hora local del sistema.

    - Descargado ahora: "histórico cargado a las HH:MM".
    - De la caché: "histórico guardado de DD/MM HH:MM" (o "guardado hoy a
      las HH:MM" si es del mismo día que `now`).
    """
    local = load.loaded_at.astimezone()
    if load.source != "cache":
        return f"histórico cargado a las {local.strftime('%H:%M')}"
    if now is not None and now.astimezone().date() == local.date():
        return f"histórico guardado hoy a las {local.strftime('%H:%M')}"
    return f"histórico guardado de {local.strftime('%d/%m %H:%M')}"


def _cache_age_text(fetched_at) -> str:
    """Antigüedad de un archivo de caché ("histórico guardado de DD/MM HH:MM")."""
    return f"histórico guardado de {fetched_at.astimezone().strftime('%d/%m %H:%M')}"


# --- Pasos de la carga ---


def _resolve_clock(today, now) -> tuple[date, datetime]:
    """Devuelve (fecha de mercado, hora de la carga)."""
    if now is None:
        now = datetime.now(MARKET_TZ)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("`now` debe llevar zona horaria")
    return market_today(today if today is not None else now), now


def _check_years(years) -> None:
    """`years` debe ser un entero entre MIN_YEARS y MAX_YEARS."""
    if isinstance(years, bool) or not isinstance(years, int) or not MIN_YEARS <= years <= MAX_YEARS:
        raise ValueError(f"años no válidos: {years!r} (entre {MIN_YEARS} y {MAX_YEARS})")


def _usable_cache(label, cache_dir, market_date, start):
    """Caché fresca que cubre el tramo, o None."""
    cached = read_history(label, cache_dir)
    if cached is None:
        return None
    history, fetched_at, requested_start = cached
    if is_fresh(fetched_at, history.dates[-1], market_date) and covers(
        history.dates[0], requested_start, start
    ):
        return cached
    return None


def _download(provider, symbol, start, end, market_date, allow_non_positive=False) -> PriceHistory:
    """Descarga y limpia un símbolo; EmptyDataError si no queda nada."""
    raw = provider.get_history(symbol, start, end)
    cleaned = clean_history(raw, market_date, allow_non_positive)
    if not cleaned.dates:
        raise EmptyDataError()
    return cleaned


def _download_underlying(provider, label, start, end, market_date) -> tuple[PriceHistory, str]:
    """Descarga el subyacente probando sus símbolos en orden.

    Solo una respuesta vacía pasa al siguiente símbolo; cualquier otro
    error (red, 429) se lanza sin probar más.
    """
    last_error = None
    for symbol in history_symbols(label):
        try:
            return _download(provider, symbol, start, end, market_date), symbol
        except EmptyDataError as error:
            last_error = error
    raise last_error


def _to_fraction(rates_percent) -> PriceHistory:
    """Histórico de ^IRX en porcentaje -> en fracción (4.12 -> 0.0412)."""
    return replace(
        rates_percent,
        close=tuple(rate_from_percent(v) for v in rates_percent.close),
        adj_close=tuple(rate_from_percent(v) for v in rates_percent.adj_close),
    )


def _load_rates(provider, start, end, market_date, now, cache_dir, notices, online=True):
    """Histórico de la tasa en fracción, o None (con aviso). Nunca lanza DatosError."""
    if online:
        cached = _usable_cache(RATE_HISTORY_SYMBOL, cache_dir, market_date, start)
        if cached is not None:
            return _to_fraction(cached[0])
        try:
            rates = _download(provider, RATE_HISTORY_SYMBOL, start, end, market_date, True)
        except DatosError:
            pass
        else:
            _written, notice = write_history(rates, now, start, cache_dir)
            if notice:
                notices.append(notice)
            return _to_fraction(replace(rates, source="live", loaded_at=now))

    # Sin descarga: la tasa guardada, aunque sea vieja; si no, ninguna.
    cached = read_history(RATE_HISTORY_SYMBOL, cache_dir)
    if cached is None:
        notices.append(MSG_RATE_HISTORY_MISSING)
        return None
    if online:
        notices.append(MSG_RATE_FROM_CACHE.format(age=_cache_age_text(cached[1])))
    return _to_fraction(cached[0])


# --- API pública ---


def load_history(provider, label, years, today=None, now=None, cache_dir=None):
    """Carga el histórico de `label` para `years` años (+1 de calentamiento).

    Devuelve (HistoryLoad, avisos) o lanza DatosError (sin red y sin
    caché). `years` entero de 1 a 15 (si no, ValueError).
    - provider: un HistoryProvider (FakeProvider o YahooProvider).
    - label: etiqueta curada ("SPY", "SPX"); nombre del archivo de caché.
    - today / now: reloj inyectable; cache_dir: carpeta de la caché.
    """
    _check_years(years)
    market_date, now = _resolve_clock(today, now)
    start = start_for_years(market_date, years)
    end = market_date + timedelta(days=1)
    notices = []

    cached = _usable_cache(label, cache_dir, market_date, start)
    if cached is not None:
        history, fetched_at, requested_start = cached
        rates = _load_rates(provider, start, end, market_date, now, cache_dir, notices)
        load = HistoryLoad(history, rates, "cache", fetched_at, None, requested_start)
        return load, notices

    try:
        history, symbol = _download_underlying(provider, label, start, end, market_date)
    except DatosError as error:
        return _offline_load(label, error, start, end, market_date, now, cache_dir)

    history = replace(history, ticker=label, source="live", loaded_at=now)
    _written, notice = write_history(history, now, start, cache_dir)
    if notice:
        notices.append(notice)
    rates = _load_rates(provider, start, end, market_date, now, cache_dir, notices)
    return HistoryLoad(history, rates, "live", now, symbol, start), notices


def _offline_load(label, error, start, end, market_date, now, cache_dir):
    """Tras un fallo del proveedor: la caché que haya, o el error en español.

    No se hace ninguna solicitud más (tras un 429 no se insiste).
    """
    cached = read_history(label, cache_dir)
    if cached is None:
        raise type(error)(f"{error.message} {MSG_NO_HISTORY_CACHE}")
    history, fetched_at, requested_start = cached
    notices = [error.message, MSG_USING_HISTORY_CACHE.format(age=_cache_age_text(fetched_at))]
    rates = _load_rates(None, start, end, market_date, now, cache_dir, notices, online=False)
    load = HistoryLoad(history, rates, "cache", fetched_at, None, requested_start)
    return load, notices
