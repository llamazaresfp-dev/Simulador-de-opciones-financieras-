"""Caché local de snapshots de mercado: un archivo JSON por ticker.

Para qué sirve: si Internet falla, la app puede mostrar lo último que
se cargó bien ("datos guardados de DD/MM HH:MM").

Reglas principales:
- Un archivo por etiqueta curada en `.cache_datos/` (raíz del repo,
  ignorada por git): `SPY.json`, `SPX.json` (nunca `^SPX.json`, el
  símbolo de Yahoo no se usa como nombre de archivo).
- Sin caducidad (sin TTL): la antigüedad se le muestra al usuario.
- Escritura ATÓMICA: primero se escribe un archivo temporal en la misma
  carpeta y luego `os.replace` lo cambia por el definitivo de un solo
  golpe. Así el archivo queda completo (el nuevo o el viejo), nunca a
  medias, aunque el programa se corte mientras escribe.
- Lectura defensiva: si falta el archivo, está corrupto o es de otra
  versión del formato (`schema_version`), se devuelve None ("sin
  caché"); nunca se lanza una excepción hacia la app.
- Al leer se REAPLICAN los filtros de liquidez y se RECALCULAN los días
  hasta el vencimiento desde el reloj inyectado (`today`), porque un
  vencimiento que era válido ayer puede haber salido hoy de la ventana.
- Regla parcial-vs-rico (C-V4): una carga COMPLETA (`complete=True`)
  siempre se guarda, aunque traiga menos vencimientos que la copia
  guardada (es normal: los vencimientos van saliendo de la ventana con
  los días). Una carga PARCIAL (`complete=False`, cortada por un 429 o
  con vencimientos fallidos) solo se guarda si es igual o más rica que
  la copia guardada; para compararlas, a las dos se les aplican HOY la
  ventana de vencimientos y los filtros de liquidez. Si es más pobre, se
  conserva la guardada y se devuelve un aviso.

Este módulo no importa el servicio: la caché va antes (C-V6).
Solo usa la biblioteca estándar.
"""

import json
import math
import numbers
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from datos.filters import DEFAULT_RULES, clean_row, filter_chain, is_expiry_in_window
from datos.types import MarketSnapshot

# Versión del formato del archivo. Si algún día cambia el formato, se
# sube este número y los archivos viejos pasan a leerse como "sin caché".
SCHEMA_VERSION = 1

# Carpeta por defecto: `.cache_datos/` en la raíz del repositorio,
# calculada desde la ruta de este archivo (datos/cache.py -> raíz).
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache_datos"

# Las fechas de mercado (hoy, días hasta el vencimiento) se cuentan en
# la hora de Nueva York, donde cotizan las opciones de EE. UU.
MARKET_TZ = ZoneInfo("America/New_York")

# Orígenes válidos de q (ver MarketSnapshot).
VALID_Q_SOURCES = ("yahoo", "indice", "no_disponible")

# Etiqueta segura para nombre de archivo: letras, números, punto, guion
# y guion bajo; no puede empezar por punto (evita archivos ocultos y "..").
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")

# Campos de cada cotización tal como se guardan (mismas claves que las
# filas crudas, para poder pasarlas otra vez por clean_row al leer).
_QUOTE_FIELDS = ("kind", "strike", "bid", "ask", "last", "oi", "volume", "iv_yahoo")

MSG_KEPT_RICHER = (
    "La carga nueva está incompleta y trae menos datos ({new_exp} vencimientos, {new_q} cotizaciones) "
    "que la copia guardada ({old_exp} vencimientos, {old_q} cotizaciones): "
    "se conserva la caché más completa."
)
MSG_WRITE_FAILED = "No se pudo guardar la caché en disco: {error}"


# --- Nombre y ruta del archivo ---


def _file_label(label) -> str:
    """Etiqueta curada -> nombre base del archivo ("^SPX" -> "SPX").

    Lanza ValueError si la etiqueta no es segura como nombre de archivo
    (vacía, con barras, "..", etc.): es un error de programación, porque
    la app solo usa la lista curada de tickers.
    """
    if not isinstance(label, str):
        raise ValueError(f"etiqueta de caché no válida: {label!r}")
    name = label.strip().lstrip("^")
    if not _SAFE_LABEL.match(name):
        raise ValueError(f"etiqueta de caché no válida: {label!r}")
    return name


def cache_path(label, cache_dir=None) -> Path:
    """Ruta del archivo de caché de una etiqueta: <cache_dir>/<ETIQUETA>.json."""
    folder = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    return folder / f"{_file_label(label)}.json"


# --- Reloj de mercado ---


def market_today(today=None) -> date:
    """Fecha de mercado (Nueva York).

    - None: la fecha actual en Nueva York.
    - date: se usa tal cual (ya es una fecha de mercado).
    - datetime con zona: se convierte a Nueva York y se toma la fecha.
    - datetime sin zona: ValueError (no se sabe de qué hora se habla).
    """
    if today is None:
        return datetime.now(MARKET_TZ).date()
    if isinstance(today, datetime):
        if today.tzinfo is None or today.utcoffset() is None:
            raise ValueError("el reloj debe llevar zona horaria")
        return today.astimezone(MARKET_TZ).date()
    if isinstance(today, date):
        return today
    raise ValueError(f"fecha de mercado no válida: {today!r}")


# --- Regla parcial-vs-rico ---


def richness(snapshot) -> tuple[int, int]:
    """Cuánto trae un snapshot: (nº de vencimientos, nº total de cotizaciones)."""
    chains = snapshot.chains
    return len(chains), sum(len(quotes) for quotes in chains.values())


def is_richer_or_equal(new, old) -> bool:
    """True si `new` trae al menos tanto como `old` en AMBAS medidas.

    Regla: new.vencimientos >= old.vencimientos Y new.cotizaciones >=
    old.cotizaciones. Si pierde en cualquiera de las dos, es más pobre
    (por ejemplo, una carga cortada por el límite de solicitudes) y no
    debe pisar la copia guardada.
    """
    return _not_poorer(richness(new), richness(old))


def _not_poorer(new_counts, old_counts) -> bool:
    """Compara dos (vencimientos, cotizaciones): ninguna medida baja."""
    return new_counts[0] >= old_counts[0] and new_counts[1] >= old_counts[1]


# --- Conversión a/desde JSON ---


def _quote_to_dict(quote) -> dict:
    """OptionQuote -> dict con las claves de una fila cruda."""
    return {field: getattr(quote, field) for field in _QUOTE_FIELDS}


def _snapshot_to_dict(snapshot) -> dict:
    """MarketSnapshot -> dict listo para json.dump."""
    loaded_at = snapshot.loaded_at
    if not isinstance(loaded_at, datetime) or loaded_at.utcoffset() is None:
        raise ValueError("loaded_at debe ser un datetime con zona horaria")
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": snapshot.ticker,
        "loaded_at": loaded_at.isoformat(),
        "spot": snapshot.spot,
        "rate": snapshot.rate,
        "q": snapshot.q,
        "q_source": snapshot.q_source,
        "complete": bool(snapshot.complete),
        "chains": {
            expiry: [_quote_to_dict(q) for q in quotes]
            for expiry, quotes in snapshot.chains.items()
        },
    }


def _finite_number(value) -> float | None:
    """Número real finito (no bool), o None."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _load_raw(path) -> dict | None:
    """Lee el archivo y comprueba la cabecera; None si no sirve.

    Devuelve el dict con los campos ya validados (salvo las filas de
    cotizaciones, que se validan con clean_row). Nunca lanza.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        # Falta el archivo, no se puede leer, no es UTF-8 o no es JSON.
        return None
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return None

    ticker = data.get("ticker")
    spot = _finite_number(data.get("spot"))
    rate = _finite_number(data.get("rate"))
    q_raw = data.get("q")
    q = None if q_raw is None else _finite_number(q_raw)
    q_source = data.get("q_source")
    chains = data.get("chains")
    # Archivos viejos sin el campo "complete": se tratan como completos.
    complete = data.get("complete", True)
    if (
        not isinstance(complete, bool)
        or not isinstance(ticker, str)
        or spot is None
        or spot <= 0
        or rate is None
        or (q_raw is not None and q is None)
        or q_source not in VALID_Q_SOURCES
        or not isinstance(chains, dict)
    ):
        return None
    try:
        loaded_at = datetime.fromisoformat(data.get("loaded_at"))
    except (TypeError, ValueError):
        return None
    if loaded_at.utcoffset() is None:
        return None
    return {
        "ticker": ticker,
        "loaded_at": loaded_at,
        "spot": spot,
        "rate": rate,
        "q": q,
        "q_source": q_source,
        "complete": complete,
        "chains": chains,
    }


def _filtered_chains(raw_chains, spot, market_date, rules) -> dict:
    """Vista "de hoy" de unas cadenas guardadas en forma de filas crudas.

    Quita los vencimientos que están fuera de la ventana en `market_date`
    y vuelve a limpiar (clean_row) y filtrar (filter_chain) las filas.
    Se usa al leer y también al comparar una carga parcial con la copia
    guardada, para que las dos se midan con la misma vara.
    """
    chains = {}
    for expiry in sorted(raw_chains):
        rows = raw_chains[expiry]
        days = _expiry_days(expiry, market_date)
        if days is None or not is_expiry_in_window(days, rules) or not isinstance(rows, list):
            continue
        cleaned = [q for q in (clean_row(row) for row in rows) if q is not None]
        liquid = filter_chain(cleaned, spot, rules)
        if liquid:
            chains[expiry] = liquid
    return chains


def _chains_richness(chains) -> tuple[int, int]:
    """(nº de vencimientos, nº total de cotizaciones) de unas cadenas."""
    return len(chains), sum(len(quotes) for quotes in chains.values())


# --- Escritura ---


def _atomic_write_json(path, data) -> None:
    """Escribe `data` en `path` de forma atómica.

    1. Se crea un archivo temporal EN LA MISMA CARPETA (mismo disco, para
       que el cambio de nombre sea atómico).
    2. Se escribe el JSON completo y se fuerza a disco (fsync).
    3. `os.replace` sustituye el archivo definitivo de un solo golpe.
    Si algo falla, se borra el temporal y el archivo viejo queda intacto.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            # allow_nan=False: un NaN no es JSON válido; mejor fallar aquí.
            json.dump(data, fh, ensure_ascii=False, indent=1, allow_nan=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise


def write_snapshot(snapshot, cache_dir=None, today=None, rules=DEFAULT_RULES) -> tuple[bool, str | None]:
    """Guarda un snapshot en la caché. Devuelve (escrito, aviso o None).

    - (True, None): se guardó.
    - (False, aviso): no se guardó, porque era una carga parcial más
      pobre que la copia guardada (regla parcial-vs-rico) o porque falló
      el disco. La app muestra el aviso; la carga en vivo sigue siendo
      válida.

    Regla parcial-vs-rico (C-V4, AC-C1-10):
    - Carga completa (`snapshot.complete` True): se guarda SIEMPRE y
      sustituye a lo que hubiera. Si mañana un vencimiento sale de la
      ventana, la carga completa trae uno menos y aun así es la buena.
    - Carga parcial (`complete` False): solo se guarda si, vistas las dos
      HOY (ventana de vencimientos y filtros de liquidez reaplicados en
      `today`), la nueva no pierde ni vencimientos ni cotizaciones frente
      a la guardada. Así, un vencimiento guardado que ya ha caducado no
      cuenta a favor de la copia vieja.

    `today`: fecha de mercado para esa comparación (date o datetime con
    zona). Si es None se usa la fecha de mercado de `snapshot.loaded_at`,
    el día de la propia carga. `rules`: reglas de liquidez a reaplicar.

    Lanza ValueError solo por errores de programación: etiqueta no válida
    o `loaded_at` sin zona horaria.
    """
    path = cache_path(snapshot.ticker, cache_dir)
    data = _snapshot_to_dict(snapshot)

    if not snapshot.complete:
        old = _load_raw(path)
        if old is not None:
            market_date = market_today(today if today is not None else snapshot.loaded_at)
            # Las dos se miden igual: mismas filas crudas, misma ventana de
            # hoy y mismos filtros que aplica la lectura.
            new_counts = _chains_richness(
                _filtered_chains(data["chains"], data["spot"], market_date, rules)
            )
            old_counts = _chains_richness(
                _filtered_chains(old["chains"], old["spot"], market_date, rules)
            )
            if not _not_poorer(new_counts, old_counts):
                notice = MSG_KEPT_RICHER.format(
                    new_exp=new_counts[0],
                    new_q=new_counts[1],
                    old_exp=old_counts[0],
                    old_q=old_counts[1],
                )
                return False, notice

    try:
        _atomic_write_json(path, data)
    except (OSError, ValueError) as error:
        return False, MSG_WRITE_FAILED.format(error=error)
    return True, None


# --- Lectura ---


def _expiry_days(expiry, today) -> int | None:
    """Días naturales desde `today` hasta el vencimiento ISO, o None."""
    try:
        return (date.fromisoformat(expiry) - today).days
    except (TypeError, ValueError):
        return None


def read_snapshot(label, cache_dir=None, today=None, rules=DEFAULT_RULES):
    """Lee la caché de una etiqueta. Devuelve MarketSnapshot o None.

    - None si no hay archivo, está corrupto, es de otro schema_version o
      no queda ningún vencimiento útil tras filtrar.
    - Las filas se limpian (clean_row) y se filtran (filter_chain con
      `rules`) otra vez; los vencimientos se recalculan desde `today`
      (fecha de mercado en Nueva York) y se quitan los que han salido de
      la ventana o se han quedado sin opciones líquidas.
    - El snapshot devuelto lleva source="cache".
    """
    raw = _load_raw(cache_path(label, cache_dir))
    if raw is None:
        return None
    market_date = market_today(today)

    chains = _filtered_chains(raw["chains"], raw["spot"], market_date, rules)
    if not chains:
        return None

    return MarketSnapshot(
        ticker=raw["ticker"],
        loaded_at=raw["loaded_at"],
        spot=raw["spot"],
        rate=raw["rate"],
        q=raw["q"],
        q_source=raw["q_source"],
        chains=chains,
        source="cache",
        complete=raw["complete"],
    )
