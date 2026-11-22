"""Traductor entre una estrategia y un archivo JSON (Etapa D, bloque 1).

Dos trabajos:

1. Convertir la estrategia del Constructor (las patas como diccionarios
   de la app, el mercado y las comisiones) en un documento JSON con
   versión de esquema (`strategy_to_dict`, `dumps_strategy`,
   `prepare_document`).
2. Hacer de "portero": `parse_strategy_json` revisa cualquier archivo
   (también uno ajeno o manipulado) y devuelve la estrategia o una lista
   de mensajes en español. NUNCA lanza excepciones y nunca corrige un
   valor en silencio: si algo está mal, el archivo se rechaza.

El mercado se guarda en unidades del motor (fracciones: vol 0.25 = 25 %).
Solo usa la biblioteca estándar y el motor `opciones`; nunca ejecuta
nada que venga del archivo.
"""

import json
import math
from dataclasses import dataclass
from datetime import date, datetime

from opciones import validation
from opciones.models import MIN_VOL, PRICING_MODELS, CommissionSettings, Leg, Market

SCHEMA_VERSION = 1
MAX_BYTES = 262144  # 256 KB
MAX_LEGS = 10
MAX_NAME_LEN = 60
MAX_TICKER_LEN = 20

VALID_KINDS = ("call", "put", "stock")
VALID_SIDES = (1, -1)
VALID_PREMIUM_SOURCES = (None, "mercado", "manual")

# Cotas de magnitud para archivos externos (DD-21). Un valor fuera de su
# cota se rechaza con un mensaje; nunca se recorta.
BOUNDS = {
    "spot": (0.01, 1e7),
    "strike": (0.01, 1e7),
    "quantity": (1e-6, 1e5),
    "price": (0.0, 1e6),
    "bid": (0.0, 1e6),
    "ask": (0.0, 1e6),
    "vol": (MIN_VOL, 5.0),
    "days": (0, 3650),
    "rate": (-0.5, 1.0),
    "q": (-0.5, 1.0),
    "per_contract": (0.0, 1e3),
    "index_surcharge": (0.0, 1e3),
}

MSG_NOT_BYTES = "El archivo no tiene un formato de bytes válido."
MSG_TOO_BIG = "El archivo es demasiado grande (máximo 256 KB)."
MSG_NOT_UTF8 = "El archivo no es texto UTF-8."
MSG_BAD_JSON = "El archivo no es un JSON válido."
MSG_NOT_OBJECT = "El archivo no contiene una estrategia (se esperaba un objeto JSON)."
MSG_NO_VERSION = "Falta la versión del formato («schema_version»)."
MSG_BAD_VERSION = "La versión del formato («schema_version») no es válida."
MSG_NEWER_VERSION = (
    "El archivo se creó con una versión más nueva de la app "
    "(versión del formato {version}); esta app solo lee la versión 1."
)
MSG_GENERIC = "No se pudo leer el archivo."
MSG_EMPTY_NAME = "El nombre está vacío."
MSG_LONG_NAME = "El nombre tiene más de 60 caracteres."
MSG_CONTROL_NAME = "El nombre contiene caracteres no permitidos (saltos de línea o de control)."
MSG_NO_LEGS = "La estrategia no tiene patas: añade al menos una."
MSG_TOO_MANY_LEGS = "La estrategia tiene más de 10 patas."
MSG_CANNOT_SAVE = "No se pudo preparar el documento de la estrategia."


@dataclass(frozen=True)
class SavedLeg:
    """Una pata tal como se guarda en el archivo (sin id ni IV de Yahoo).

    bid, ask y expiry solo tienen valor en las patas de mercado
    (premium_source == "mercado").
    """

    kind: str
    side: int
    quantity: float
    strike: float | None
    price: float
    premium_manual: bool
    premium_source: str | None
    bid: float | None
    ask: float | None
    expiry: str | None


@dataclass(frozen=True)
class SavedStrategy:
    """Una estrategia leída de un archivo y ya validada."""

    name: str
    saved_at: str
    ticker: str | None
    market: Market
    commissions: CommissionSettings
    legs: tuple[SavedLeg, ...]


# --- De la app al documento ---


def _plain_days(days):
    """Días como entero si es un número entero (45.0 -> 45)."""
    if isinstance(days, float) and days.is_integer():
        return int(days)
    return days


def _leg_to_dict(leg: dict) -> dict:
    """Pata de la app (diccionario) -> pata del documento.

    Se ignoran 'id' e 'iv_yahoo'. bid/ask/expiry solo en patas de mercado.
    Las acciones no llevan strike.
    """
    item = {
        "kind": leg["kind"],
        "side": leg["side"],
        "quantity": leg["quantity"],
    }
    if leg["kind"] != "stock":
        item["strike"] = leg["strike"]
    item["price"] = leg["price"]
    item["premium_manual"] = bool(leg.get("premium_manual", False))
    item["premium_source"] = leg.get("premium_source")
    if leg.get("premium_source") == "mercado":
        item["bid"] = leg.get("bid")
        item["ask"] = leg.get("ask")
        item["expiry"] = leg.get("expiry")
    return item


def strategy_to_dict(legs, market, commissions, name, saved_at, ticker=None) -> dict:
    """Construye el documento (esquema 1) a partir de los datos de la app.

    - legs: lista de diccionarios de patas, como en st.session_state["legs"].
    - market: Market del motor (fracciones).
    - commissions: CommissionSettings.
    - saved_at: texto ISO o datetime con zona horaria.
    """
    if isinstance(saved_at, datetime):
        saved_at = saved_at.isoformat(timespec="seconds")
    return {
        "schema_version": SCHEMA_VERSION,
        "name": name.strip() if isinstance(name, str) else name,
        "saved_at": saved_at,
        "ticker": ticker,
        "market": {
            "underlying": market.underlying,
            "spot": market.spot,
            "vol": market.vol,
            "days": _plain_days(market.days),
            "rate": market.rate,
            "q": market.q,
            "pricing_model": market.pricing_model,
        },
        "commissions": {
            "per_contract": commissions.per_contract,
            "index_surcharge": commissions.index_surcharge,
            "include_close": commissions.include_close,
        },
        "legs": [_leg_to_dict(leg) for leg in legs],
    }


def dumps_strategy(doc: dict) -> bytes:
    """Documento -> bytes UTF-8 (indentación 2, acentos tal cual, sin NaN)."""
    text = json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False)
    return text.encode("utf-8")


def _name_errors(name) -> list[str]:
    """Errores del nombre (lista vacía = válido)."""
    if not isinstance(name, str):
        return [MSG_EMPTY_NAME]
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        return [MSG_CONTROL_NAME]
    if not name.strip():
        return [MSG_EMPTY_NAME]
    if len(name.strip()) > MAX_NAME_LEN:
        return [MSG_LONG_NAME]
    return []


def prepare_document(legs, market, commissions, name, saved_at, ticker=None):
    """Prepara los bytes que se guardan Y se descargan (los mismos, DD-4).

    Devuelve (bytes, []) si todo es válido o (None, [mensajes]) si no.
    Comprueba el nombre, el número de patas, la validación del motor y,
    al final, que el documento se relee con parse_strategy_json (así lo
    guardado respeta las mismas cotas que un archivo externo).
    """
    try:
        errors = _name_errors(name)
        if not legs:
            errors.append(MSG_NO_LEGS)
        elif len(legs) > MAX_LEGS:
            errors.append(MSG_TOO_MANY_LEGS)
        if errors:
            return None, errors

        engine_legs = []
        for leg in legs:
            strike = None if leg["kind"] == "stock" else leg["strike"]
            engine_legs.append(Leg(leg["kind"], leg["side"], leg["quantity"], strike, leg["price"]))
        errors = validation.validate_market(market) + validation.validate_legs(engine_legs)
        if errors:
            return None, errors

        doc = strategy_to_dict(legs, market, commissions, name, saved_at, ticker)
        raw = dumps_strategy(doc)
    except Exception:
        return None, [MSG_CANNOT_SAVE]

    strategy, errors = parse_strategy_json(raw)
    if strategy is None:
        return None, errors
    return raw, []


# --- Del archivo a la estrategia (el portero) ---


def _reject_constant(text):
    """json.loads llama aquí con NaN, Infinity o -Infinity: no se aceptan."""
    raise ValueError(f"constante no permitida: {text}")


def _format_number(value) -> str:
    """Número en formato español corto: 0.01 -> "0,01", 1e7 -> "10000000"."""
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _is_number(value) -> bool:
    """True si es int o float de verdad (no bool) y finito."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _check_number(container: dict, field: str, errors: list, prefix: str = "", integer: bool = False):
    """Lee un número obligatorio y comprueba tipo y cota. Devuelve el valor o None."""
    if field not in container:
        errors.append(f"{prefix}falta el campo «{field}».")
        return None
    value = container[field]
    if integer:
        valid_type = isinstance(value, int) and not isinstance(value, bool)
        type_text = "un número entero"
    else:
        valid_type = _is_number(value)
        type_text = "un número"
    if not valid_type:
        errors.append(f"{prefix}«{field}» debe ser {type_text}.")
        return None
    low, high = BOUNDS[field]
    if not low <= value <= high:
        errors.append(
            f"{prefix}«{field}» debe estar entre {_format_number(low)} y {_format_number(high)}."
        )
        return None
    return value


def _check_bool(container: dict, field: str, errors: list, prefix: str = ""):
    """Lee un booleano obligatorio (true/false). Devuelve el valor o None."""
    if field not in container:
        errors.append(f"{prefix}falta el campo «{field}».")
        return None
    value = container[field]
    if not isinstance(value, bool):
        errors.append(f"{prefix}«{field}» debe ser verdadero o falso.")
        return None
    return value


def _check_choice(container: dict, field: str, choices, errors: list, prefix: str = ""):
    """Lee un valor obligatorio que debe estar en una lista. Devuelve el valor o None."""
    if field not in container:
        errors.append(f"{prefix}falta el campo «{field}».")
        return None
    value = container[field]
    # Comparamos con == uno a uno: un valor raro (lista, dict) no da error de Python.
    if isinstance(value, bool) or not any(value == choice and type(value) is type(choice) for choice in choices):
        errors.append(f"{prefix}«{field}» tiene un valor no permitido.")
        return None
    return value


def _parse_saved_at(doc: dict, errors: list):
    """Fecha de guardado: texto ISO con zona horaria."""
    if "saved_at" not in doc:
        errors.append("Falta la fecha de guardado («saved_at»).")
        return None
    value = doc["saved_at"]
    try:
        moment = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        moment = None
    if moment is None or moment.tzinfo is None:
        errors.append("La fecha de guardado («saved_at») no es una fecha ISO con zona horaria.")
        return None
    return value


def _parse_ticker(doc: dict, errors: list):
    """Ticker informativo: texto corto o null (ausente = null)."""
    value = doc.get("ticker")
    if value is None:
        return None
    if (not isinstance(value, str) or len(value) > MAX_TICKER_LEN
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        errors.append("El ticker («ticker») debe ser un texto de como máximo 20 caracteres.")
    return value


def _parse_market(doc: dict, errors: list):
    """Sección 'market' -> Market (o None con errores)."""
    data = doc.get("market")
    if not isinstance(data, dict):
        errors.append("Falta el mercado («market») o no es un objeto.")
        return None
    prefix = "Mercado: "
    count = len(errors)
    underlying = _check_choice(data, "underlying", validation.VALID_UNDERLYINGS, errors, prefix)
    spot = _check_number(data, "spot", errors, prefix)
    vol = _check_number(data, "vol", errors, prefix)
    days = _check_number(data, "days", errors, prefix, integer=True)
    rate = _check_number(data, "rate", errors, prefix)
    q = _check_number(data, "q", errors, prefix)
    pricing_model = _check_choice(data, "pricing_model", PRICING_MODELS, errors, prefix)
    if len(errors) > count:
        return None
    return Market(underlying, spot, vol, days, rate, q, pricing_model)


def _parse_commissions(doc: dict, errors: list):
    """Sección 'commissions' -> CommissionSettings (o None con errores)."""
    data = doc.get("commissions")
    if not isinstance(data, dict):
        errors.append("Faltan las comisiones («commissions») o no son un objeto.")
        return None
    prefix = "Comisiones: "
    count = len(errors)
    per_contract = _check_number(data, "per_contract", errors, prefix)
    index_surcharge = _check_number(data, "index_surcharge", errors, prefix)
    include_close = _check_bool(data, "include_close", errors, prefix)
    if len(errors) > count:
        return None
    return CommissionSettings(per_contract, index_surcharge, include_close)


def _parse_optional_quote(data: dict, field: str, errors: list, prefix: str):
    """bid/ask de una pata de mercado: número acotado o null."""
    if data.get(field) is None:
        return None
    return _check_number(data, field, errors, prefix)


def _parse_expiry(data: dict, errors: list, prefix: str):
    """Vencimiento de una pata de mercado: fecha ISO (AAAA-MM-DD) o null."""
    value = data.get("expiry")
    if value is None:
        return None
    try:
        if isinstance(value, str):
            date.fromisoformat(value)
            return value
    except ValueError:
        pass
    errors.append(f"{prefix}«expiry» debe ser una fecha AAAA-MM-DD.")
    return None


def _parse_leg(data, number: int, errors: list):
    """Una pata del documento -> SavedLeg (o None con errores)."""
    prefix = f"Pata {number}: "
    if not isinstance(data, dict):
        errors.append(f"{prefix}no es un objeto.")
        return None
    count = len(errors)
    kind = _check_choice(data, "kind", VALID_KINDS, errors, prefix)
    side = _check_choice(data, "side", VALID_SIDES, errors, prefix)
    quantity = _check_number(data, "quantity", errors, prefix)

    strike = None
    if kind == "stock":
        if data.get("strike") is not None:
            errors.append(f"{prefix}una pata de acción no lleva «strike».")
    elif kind is not None:
        strike = _check_number(data, "strike", errors, prefix)

    price = _check_number(data, "price", errors, prefix)
    premium_manual = _check_bool(data, "premium_manual", errors, prefix)
    premium_source = _check_choice(data, "premium_source", VALID_PREMIUM_SOURCES, errors, prefix) \
        if "premium_source" in data else None

    bid = ask = expiry = None
    if premium_source == "mercado":
        bid = _parse_optional_quote(data, "bid", errors, prefix)
        ask = _parse_optional_quote(data, "ask", errors, prefix)
        expiry = _parse_expiry(data, errors, prefix)
    else:
        for field in ("bid", "ask", "expiry"):
            if data.get(field) is not None:
                errors.append(f"{prefix}«{field}» solo se permite en patas de mercado.")

    if len(errors) > count:
        return None
    return SavedLeg(kind, side, quantity, strike, price, premium_manual,
                    premium_source, bid, ask, expiry)


def _parse_version(doc: dict) -> list[str]:
    """Errores de la versión del formato (lista vacía = versión 1)."""
    if "schema_version" not in doc:
        return [MSG_NO_VERSION]
    version = doc["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        return [MSG_BAD_VERSION]
    if version > SCHEMA_VERSION:
        return [MSG_NEWER_VERSION.format(version=version)]
    if version != SCHEMA_VERSION:
        return [MSG_BAD_VERSION]
    return []


def _parse_document(doc) -> tuple[SavedStrategy | None, list[str]]:
    """Valida el objeto JSON ya leído (puede lanzar: lo envuelve el llamador)."""
    if not isinstance(doc, dict):
        return None, [MSG_NOT_OBJECT]
    errors = _parse_version(doc)
    if errors:
        return None, errors

    if "name" not in doc:
        errors.append("Falta el nombre («name»).")
        name = None
    else:
        name = doc["name"]
        errors += _name_errors(name)
    saved_at = _parse_saved_at(doc, errors)
    ticker = _parse_ticker(doc, errors)
    market = _parse_market(doc, errors)
    commissions = _parse_commissions(doc, errors)

    raw_legs = doc.get("legs")
    legs = []
    if not isinstance(raw_legs, list):
        errors.append("Faltan las patas («legs») o no son una lista.")
    elif not raw_legs:
        errors.append(MSG_NO_LEGS)
    elif len(raw_legs) > MAX_LEGS:
        errors.append(MSG_TOO_MANY_LEGS)
    else:
        for number, item in enumerate(raw_legs, start=1):
            legs.append(_parse_leg(item, number, errors))

    if errors:
        return None, errors

    # Los datos tienen tipos y cotas correctos: ahora la validación del motor.
    engine_legs = [saved_leg_to_engine(leg) for leg in legs]
    errors = validation.validate_market(market) + validation.validate_legs(engine_legs)
    if errors:
        return None, errors

    strategy = SavedStrategy(name.strip(), saved_at, ticker, market, commissions, tuple(legs))
    return strategy, []


def parse_strategy_json(data) -> tuple[SavedStrategy | None, list[str]]:
    """Revisa un archivo de estrategia. NUNCA lanza excepciones.

    Devuelve (SavedStrategy, []) si es válido o (None, [mensajes]) si no.
    El tamaño se comprueba ANTES de leer el JSON.
    """
    try:
        if not isinstance(data, (bytes, bytearray)):
            return None, [MSG_NOT_BYTES]
        if len(data) > MAX_BYTES:
            return None, [MSG_TOO_BIG]
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError:
            return None, [MSG_NOT_UTF8]
        try:
            doc = json.loads(text, parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            return None, [MSG_BAD_JSON]
        return _parse_document(doc)
    except Exception:
        # Último recurso: nada de lo que venga del archivo debe romper la app.
        return None, [MSG_GENERIC]


def saved_leg_to_engine(leg: SavedLeg) -> Leg:
    """Pata guardada -> Leg del motor (con la prima guardada)."""
    return Leg(leg.kind, leg.side, leg.quantity, leg.strike, leg.price)
