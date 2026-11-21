"""Servicio de carga: junta precio, tipo, dividendos y cadenas filtradas.

Pasos de una carga (`load_with_notices`):
1. Spot, tipo libre de riesgo (r) y dividend yield (q) del proveedor.
   - Índice: q no se pide (q=None, q_source="indice") y se avisa (C10).
   - q ausente o con error: q=None, q_source="no_disponible" y aviso.
2. Vencimientos: solo los de la ventana 7–120 días (contados desde
   `today`, fecha de mercado en Nueva York), en orden ascendente.
3. Cadenas: se descargan TODAS las de la ventana (carga ansiosa), se
   limpian y se filtran por liquidez. Un vencimiento sin opciones
   líquidas no se ofrece.
   - Al PRIMER error de límite de solicitudes (429) se deja de pedir:
     no se insiste y se conserva lo ya descargado.
   - Otro error en una cadena: se salta ese vencimiento y se sigue.
   - En ambos casos la carga queda PARCIAL (`complete=False`) y se avisa
     con el conteo.
4. Se guarda en la caché (bloque 3c). Una carga parcial no pisa una
   copia guardada más completa: la caché lo decide y avisa.

El reloj es inyectable: `now` (datetime con zona, hora de la carga) y
`today` (fecha de mercado). Las pruebas siempre los fijan.

Los errores son DatosError con mensaje en español; `load_or_cache`
recurre a la caché cuando el proveedor falla.
"""

import math
import numbers
from datetime import date, datetime

from datos.cache import MARKET_TZ, market_today, read_snapshot, write_snapshot
from datos.errors import MSG_NO_LIQUID, DatosError, EmptyDataError, RateLimitError
from datos.filters import DEFAULT_RULES, clean_row, filter_chain, is_expiry_in_window
from datos.types import MarketSnapshot

# Avisos para el usuario (la app los muestra con st.caption/st.info).
MSG_Q_MISSING = "sin dividend yield disponible: q = 0, edítalo si hace falta"
MSG_Q_INDEX = "sin dividend yield para índices: edítalo, SPX ≈ 1,2 %"
MSG_RATE_LIMITED_PARTIAL = (
    "El proveedor limitó las solicitudes: se cargaron {loaded} de {total} vencimientos "
    "(faltan {missing}). Vuelve a cargar dentro de unos minutos para tener el resto."
)
MSG_CHAINS_FAILED = (
    "No se pudieron descargar {failed} de {total} vencimientos; se muestran los demás."
)
MSG_USING_CACHE = "Se muestran los {age}."
MSG_NO_CACHE = (
    "No hay datos guardados de este subyacente: introduce los valores a mano."
)


# --- Conversiones ---


def rate_from_percent(value) -> float:
    """^IRX llega en porcentaje: 4.12 -> 0.0412 (fracción)."""
    return value / 100


def _finite(value) -> float | None:
    """Número real finito (no bool), o None."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _default_label(ticker) -> str:
    """Etiqueta curada por defecto: el ticker sin "^" ("^SPX" -> "SPX")."""
    return ticker.lstrip("^")


# --- Textos de antigüedad (AC-C1-9) ---


def live_age_text(loaded_at) -> str:
    """Texto de una carga en vivo, con la hora en la zona local del sistema."""
    hour = loaded_at.astimezone().strftime("%H:%M")
    return f"datos con ~15 min de retraso; cargados a las {hour}"


def cache_age_text(loaded_at) -> str:
    """Texto de datos leídos de la caché, con fecha y hora locales."""
    when = loaded_at.astimezone().strftime("%d/%m %H:%M")
    return f"datos guardados de {when}"


def age_text(snapshot) -> str:
    """Texto de antigüedad según el origen del snapshot (vivo o caché)."""
    if snapshot.source == "cache":
        return cache_age_text(snapshot.loaded_at)
    return live_age_text(snapshot.loaded_at)


# --- Pasos de la carga ---


def _resolve_clock(today, now) -> tuple[date, datetime]:
    """Devuelve (fecha de mercado, hora de la carga) con valores por defecto."""
    if now is None:
        now = datetime.now(MARKET_TZ)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("`now` debe llevar zona horaria")
    market_date = market_today(today if today is not None else now)
    return market_date, now


def _get_spot(provider, ticker) -> float:
    """Spot positivo y finito; si no, EmptyDataError."""
    spot = _finite(provider.get_spot(ticker))
    if spot is None or spot <= 0:
        raise EmptyDataError()
    return spot


def _get_rate(provider) -> float:
    """Tipo libre de riesgo (fracción) finito; si no, EmptyDataError."""
    rate = _finite(provider.get_rate())
    if rate is None:
        raise EmptyDataError()
    return rate


def _get_q(provider, ticker, is_index, notices) -> tuple[float | None, str]:
    """Devuelve (q, q_source) y añade el aviso que toque a `notices`."""
    if is_index:
        notices.append(MSG_Q_INDEX)
        return None, "indice"
    try:
        q = _finite(provider.get_dividend_yield(ticker))
    except DatosError:
        q = None
    if q is None or q < 0:
        notices.append(MSG_Q_MISSING)
        return None, "no_disponible"
    return q, "yahoo"


def _window_expiries(provider, ticker, market_date, rules) -> list[str]:
    """Vencimientos ISO dentro de la ventana, en orden ascendente.

    Sin vencimientos -> EmptyDataError (respuesta vacía).
    Ninguno en la ventana -> EmptyDataError con MSG_NO_LIQUID.
    """
    expirations = provider.get_expirations(ticker)
    if not expirations:
        raise EmptyDataError()
    in_window = []
    for expiry in expirations:
        try:
            days = (date.fromisoformat(expiry) - market_date).days
        except (TypeError, ValueError):
            continue
        if is_expiry_in_window(days, rules):
            in_window.append(expiry)
    if not in_window:
        raise EmptyDataError(MSG_NO_LIQUID)
    return sorted(set(in_window))


def _liquid_quotes(rows, spot, rules) -> list:
    """Filas crudas -> cotizaciones limpias y líquidas."""
    if not isinstance(rows, list):
        return []
    cleaned = [quote for quote in (clean_row(row) for row in rows) if quote is not None]
    return filter_chain(cleaned, spot, rules)


def _fetch_chains(provider, ticker, expiries, spot, rules, notices) -> tuple[dict, bool]:
    """Descarga las cadenas de `expiries`. Devuelve (cadenas, completa).

    - Primer RateLimitError: se para (no se piden más vencimientos).
    - Otro DatosError: se salta ese vencimiento.
    - Si no queda ninguna cadena líquida, lanza el error que corresponda.
    """
    chains = {}
    total = len(expiries)
    downloaded = 0
    failed = 0
    last_error = None
    rate_limited = False

    for expiry in expiries:
        try:
            rows = provider.get_chain(ticker, expiry)
        except RateLimitError as error:
            rate_limited = True
            last_error = error
            break
        except DatosError as error:
            failed += 1
            last_error = error
            continue
        downloaded += 1
        quotes = _liquid_quotes(rows, spot, rules)
        if quotes:
            chains[expiry] = quotes

    if not chains:
        if last_error is not None and (rate_limited or downloaded == 0):
            # Nada útil y la causa fue el límite o fallaron todas.
            raise last_error
        raise EmptyDataError(MSG_NO_LIQUID)

    if rate_limited:
        notices.append(
            MSG_RATE_LIMITED_PARTIAL.format(
                loaded=downloaded, total=total, missing=total - downloaded - failed
            )
        )
    if failed:
        notices.append(MSG_CHAINS_FAILED.format(failed=failed, total=total))
    complete = not rate_limited and failed == 0
    return chains, complete


# --- API pública ---


def load_with_notices(
    ticker,
    provider,
    today=None,
    now=None,
    cache_dir=None,
    rules=DEFAULT_RULES,
    label=None,
    is_index=None,
) -> tuple[MarketSnapshot, list[str]]:
    """Carga en vivo. Devuelve (snapshot, avisos) o lanza DatosError.

    - ticker: símbolo que entiende el proveedor ("SPY", "^SPX").
    - label: etiqueta curada para el snapshot y la caché; por defecto el
      ticker sin "^" ("^SPX" -> "SPX").
    - is_index: True para índices (q no se pide); por defecto, True si
      el ticker empieza por "^".
    - today / now: reloj inyectable (ver módulo).
    - cache_dir: carpeta de la caché (las pruebas usan tmp_path).
    - avisos: textos en español para el usuario (q ausente, nota C10,
      carga parcial, caché más completa conservada...).
    """
    market_date, now = _resolve_clock(today, now)
    if label is None:
        label = _default_label(ticker)
    if is_index is None:
        is_index = ticker.startswith("^")
    notices = []

    spot = _get_spot(provider, ticker)
    rate = _get_rate(provider)
    q, q_source = _get_q(provider, ticker, is_index, notices)
    expiries = _window_expiries(provider, ticker, market_date, rules)
    chains, complete = _fetch_chains(provider, ticker, expiries, spot, rules, notices)

    snapshot = MarketSnapshot(
        ticker=label,
        loaded_at=now,
        spot=spot,
        rate=rate,
        q=q,
        q_source=q_source,
        chains=chains,
        source="live",
        complete=complete,
    )
    _written, cache_notice = write_snapshot(snapshot, cache_dir, today=market_date, rules=rules)
    if cache_notice:
        notices.append(cache_notice)
    return snapshot, notices


def load_snapshot(
    ticker,
    provider,
    today=None,
    now=None,
    cache_dir=None,
    rules=DEFAULT_RULES,
    label=None,
    is_index=None,
) -> MarketSnapshot:
    """Igual que `load_with_notices`, pero devuelve solo el snapshot."""
    snapshot, _notices = load_with_notices(
        ticker, provider, today, now, cache_dir, rules, label, is_index
    )
    return snapshot


def load_or_cache(
    ticker,
    provider,
    today=None,
    now=None,
    cache_dir=None,
    rules=DEFAULT_RULES,
    label=None,
    is_index=None,
) -> tuple[MarketSnapshot | None, list[str]]:
    """Carga en vivo y, si el proveedor falla, recurre a la caché.

    Devuelve (snapshot, avisos):
    - Carga en vivo correcta: (snapshot "live", avisos de la carga).
    - Falla y hay caché: (snapshot "cache", [mensaje del error, "Se
      muestran los datos guardados de DD/MM HH:MM."]).
    - Falla y no hay caché: (None, [mensaje del error, MSG_NO_CACHE]).
    Nunca deja escapar un DatosError.
    """
    try:
        return load_with_notices(ticker, provider, today, now, cache_dir, rules, label, is_index)
    except DatosError as error:
        market_date, _now = _resolve_clock(today, now)
        if label is None:
            label = _default_label(ticker)
        cached = read_snapshot(label, cache_dir, today=market_date, rules=rules)
        if cached is None:
            return None, [error.message, MSG_NO_CACHE]
        return cached, [error.message, MSG_USING_CACHE.format(age=age_text(cached))]
